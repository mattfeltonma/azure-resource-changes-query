import json
import requests
import logging
import urllib
import difflib
import sys
import pprint

from argparse import ArgumentParser
from datetime import datetime
from time import sleep

# Third party modules
import msal
import pandas



# Fixed variables
scope = ['https://management.azure.com//.default']

# Resource changes and resource change details REST endpoints and API versions
resourceChangesUri = 'https://management.azure.com/providers/Microsoft.ResourceGraph/resourceChanges'
resourceChangesParams = {
    'api-version':'2018-09-01-preview'
}

resourceChangesDetailUri = 'https://management.azure.com/providers/Microsoft.ResourceGraph/resourceChangeDetails'
resourceChagnesDetailParams = {
    'api-version':'2018-09-01-preview'
}

# Reusable function to create a logging mechanism
def create_logger(logfile=None):

    # Create a logging handler that will write to stdout and optionally to a log file
    stdout_handler = logging.StreamHandler(sys.stdout)
    if logfile != None:
        file_handler = logging.FileHandler(filename=logfile)
        handlers = [file_handler, stdout_handler]
    else:
        handlers = [stdout_handler]

    # Configure logging mechanism
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers = handlers
    )

# Convert datetime to one compatible with API
def transform_datetime(datetime_str):
    userdatetime = datetime.strptime(datetime_str, '%Y-%m-%d')
    transf_time = userdatetime.strftime("%Y-%m-%dT%H:%M:%S")

    return transf_time

# Obtain access token using client credentials flow
def obtain_access_token(tenantname,scope,client_id, client_secret):
    logging.info("Attempting to obtain an access token...")
    result = None
    app = msal.ConfidentialClientApplication(
        client_id = client_id,
        client_credential = client_secret,
        authority='https://login.microsoftonline.com/' + tenantname
    )
    result = app.acquire_token_for_client(scope)

    if "access_token" in result:
        logging.info("Access token successfully acquired")
        return result
    else:
        logging.error("Authentication failure")
        logging.error("Error was: %s",result['error'])
        logging.error("Error description was: %s",result['error_description'])
        logging.error("Error correlation_id was: %s",result['correlation_id'])
        raise Exception("Unable obtaining access token")

# Reusable function to query Microsoft API
def query_resource_api(data,token,endpoint,params=None):
    headers = {'Content-Type':'application/json', \
    'Authorization':'Bearer {0}'.format(token['access_token'])}
    
    # Determine if optional query strings are being passed and if so pass them
    if params==None:
        r = requests.post(url=endpoint,headers=headers,data=json.dumps(data))
    else:
        r = requests.post(url=endpoint,headers=headers,data=json.dumps(data),params=params)
    if r.status_code == 200:
        return r

    # Address rate limiting by sleeping for 10 seconds
    elif r.status_code == 429:
        logging.info('Request was rate limited. Backing off for 10 seconds...')
        sleep(10)
        r = query_resource_api(data,token,endpoint,params)
        return r
    else:
        raise Exception('Request failed with ',r.status_code,' - ',r.text)

# Query resource graph for all of the changes for a specific resource type in a subscription
def query_resources(resource_type,subscription,token):
    
    # Convert data from column/rows to JSON
    def exportdata(data):

        # Create a list of column names
        column_names = []

        for column in data['columns']:
            column_names.append(column['name'])
        
        # Create a DataFrame using the Pandas module and export it as JSON
        dfobj = pandas.DataFrame(data['rows'], columns = column_names)
        return dfobj
    
    # Resource Graph REST endpoint for querying for resources and current API version
    resourceGraphEndpointUri = 'https://management.azure.com/providers/Microsoft.ResourceGraph/resources'
    resourceGraphEndpointUriParams = {
        'api-version':'2019-04-01'
    }

    # Construct resource query
    resource_query = 'where type =~ ' + '\'' + resource_type + '\' | project id'
    request_body = {
        'subscriptions': [
            subscription
        ],
        'query': resource_query,
    }

    # Issue query to resources endpoint
    resource_records = query_resource_api(
        data=request_body,
        token=token,
        endpoint = resourceGraphEndpointUri,
        params = resourceChangesParams
    )

    # Load response in as a dict
    json_results = json.loads(resource_records.text)

    # Send response to exportdata function to extract data from rows/columns and convert to JSON
    df_results = exportdata(json_results['data'])

    # Handle paging if multiple resources are returned
    while 'skipToken' in json_results:
        logging.info("Retrieving ") + str(json_results['count']) + " paged records.."
        request_body = {
            'subscriptions': [
                subscription
            ],
            'query': resource_query,
            'options': {
                '$skipToken':json_results['$skipToken']
            }
        }
        resource_records = query_resource_api(
            data=request_body,
            token=token,
            endpoint = resourceGraphEndpointUri,
            params = resourceChangesParams
        )
        json_results = json.loads(resource_records.text)
        df_results = df_results.append(export_data(json_results['data']))

    # Convert results to a dict    
    resources = df_results.to_dict('records')
    return resources

# Main function
def main():

    try:
        # Process parameters file
        parser = ArgumentParser()
        parser.add_argument('--parameterfile', type=str, help='JSON file with parameters')
        parser.add_argument('--logfile', type=str, default=None, help='Specify an optional log file')
        args = parser.parse_args()

        with open(args.parameterfile) as json_data:
            config = json.load(json_data)

        # Setup a logger and optionally a logging file if the user specified
        if args.logfile != None:
            create_logger(args.logfile)
        else:
            create_logger()

        # Obtain an access token to query Resource Graph API
        token = obtain_access_token(tenantname=config['tenantname'],scope=scope,client_id=config['client_id'],client_secret=config['client_secret'])

        # Query for a listing of resources in a given subscription of a given resource type
        resources = query_resources(config['resource_type'],config['subscription'],token)
        
        # Create a new dictionary to store the change records
        change_records = []

        # For each resource request the last X days of changes
        for resource in resources:
            
            resource_id = resource['id']
            # Construct query for changes
            query = {
                'resourceId': resource_id,
                'interval': {
                    'start': transform_datetime(config['start_time']),
                    'end': transform_datetime(config['end_time'])              
                }
            }
            # Get a listing of changes for the resource
            logging.info('Getting the list of changes for ' + resource_id + '...')
            changes = query_resource_api(data=query,token=token,endpoint=resourceChangesUri,params=resourceChangesParams)

            # Parse the changes 
            json_changes = json.loads(changes.text)
            for change in json_changes['changes']:
        
                # Get the change details and log error if change information can't be retrieved
                logging.info('Getting change details for ' + (change['changeId']) + '...')
                change_query = {
                    'resourceId': resource_id,
                    'changeId': (change['changeId'])
                }
                change_details = query_resource_api(data=change_query,token=token,endpoint=resourceChangesDetailUri,params=resourceChagnesDetailParams)

                # Fix an issue where the API double encodes the changeId value
                json_change_details = json.loads(change_details.text)
                json_change_details['changeId'] = json.loads(change['changeId'])

                # Add the change record to a list of JSON objects
                change_records.append(json_change_details)

        # Export the data to a file        
        logging.info('Writing results to a file...')
        with open(config['exportfilename'], 'a') as f:
            f.write(json.dumps(change_records))
    except Exception as e:
        logging.error('Execution error',exc_info=True)

if __name__ == "__main__":
    main()

