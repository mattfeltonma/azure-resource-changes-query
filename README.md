# Azure Resource Graph Query for Changes
This solution returns the last 14 days of changes to all resources of a given Azure Resource type.

## What problem does this solve?
Tracking changes to an enterprise's resources is critical for reasons such as monitoring for compliance compliance or identifying resources that changed prior to an outage.  Changes to Azure resources can be viewed in the portal using Azure Policy and [Azure Activity Log Change History](https://docs.microsoft.com/en-us/azure/azure-monitor/platform/activity-log-view#azure-portal).  In 2019, Microsoft made this information available for programmatic access via the Azure Resource Graph.  

This Python solution queries for changes made to a specific Azure resource type (such as microsoft.storage/storageaccounts) within a provided Azure subscription.  The Azure Resource Graph provides up to 14 days of changes for a resource.

## Requirements

### Python Runtime and Modules
* [Python 3.6](https://www.python.org/downloads/release/python-360/)
* [Pandas](https://pandas.pydata.org/)
* [Microsoft Authentication Library - MSAL](https://github.com/AzureAD/microsoft-authentication-library-for-python)

## Setup
To use this solution, a security prinicpal must be created in the Azure AD Tenant with appropriate permissions on the Azure Subscription and Azure Resource types.  Microsoft provides [instructions](https://docs.microsoft.com/en-us/azure/azure-resource-manager/resource-manager-api-authentication) on how to create that principal.  The reader role is sufficient to query for the resources and the resource chnages.

