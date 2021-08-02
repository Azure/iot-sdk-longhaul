// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for
// full license information.

param location string {
  metadata: {
    description: 'Azure region to deploy resources into (e.g. westus2, eastus, etc)'
  }
}
param prefix string {
  // maxLength=15 because "<prefix>-thief-kv" cannot be more than 24 characters
  minLength: 1
  maxLength: 15
  metadata: {
    description: 'Prefix string to add to all resource names.  For example, if prefix is "bob", then this will deploy resources with names that start with "bob"'
  }
}
param app_insights_instrumentation_key string {
  minLength: 36
  maxLength: 36
  metadata: {
    description: 'App Insights instrumentation key that we plan to use for monitoring.  Inherited from shared resources.'
  }
}
param user_principal_id string {
  minLength: 36
  maxLength: 36
  metadata: {
    description: 'Principal ID for the person making the deployment.  Used to give that permission access to the keyvault that we create'
  }
}
param shared_subscription_id string {
  minLength: 36
  maxLength: 36
  metadata: {
    description: 'Subscription ID containing all of our shared resources.  Inherited from shared resources.'
  }
}
param shared_keyvault_name string {
  minLength: 3
  maxLength: 24
  metadata: {
    description: 'Name of keyvault that contains all of our shared resources.  Inherited from shared resources.'
  }
}
param shared_resource_group string {
  minLength: 3
  maxLength: 90
  metadata: {
    description: 'Name of resource group that holds all of our shared resources.  Inherited from shared resources.'
  }
}

resource iothub 'Microsoft.Devices/IotHubs@2020-08-01' = {
  name: '${prefix}-thief-hub'
  location: location
  sku: {
    name: 'S2'
    capacity: 1
  }
  properties: {
    eventHubEndpoints: {
      events: {
        retentionTimeInDays: 1
        partitionCount: 4
      }
    }
    routing: {
      routes: [
        {
          name: 'twin-update-event'
          source: 'TwinChangeEvents'
          condition: 'true'
          endpointNames: [
            'events'
          ]
          isEnabled: true
        }
      ]
      fallbackRoute: {
        name: '$fallback'
        source: 'DeviceMessages'
        condition: 'true'
        endpointNames: [
          'events'
        ]
        isEnabled: true
      }
    }
  }
}
var shared_access_key_name = '${listKeys(iothub.id, '2020-04-01').value[0].keyName}'
var shared_access_key = '${listKeys(iothub.id, '2020-04-01').value[0].primaryKey}'
var iothub_connection_string = 'HostName=${iothub.name}.azure-devices.net;SharedAccessKeyName=${shared_access_key_name};SharedAccessKey=${shared_access_key}'
var eventhub_connection_string = 'Endpoint=${iothub.properties.eventHubEndpoints.events.endpoint};SharedAccessKeyName=${shared_access_key_name};SharedAccessKey=${shared_access_key};EntityPath=${iothub.properties.eventHubEndpoints.events.path}'

resource dps 'Microsoft.Devices/provisioningServices@2020-03-01' = {
  name: '${prefix}-thief-dps'
  location: location
  sku: {
    name: 'S1'
    capacity: 1
  }
  properties: {
    state: 'Active'
    provisioningState: 'Succeeded'
    iotHubs: [
      {
        connectionString: iothub_connection_string
        location: location
      }
    ]
    allocationPolicy: 'Hashed'
  }
}

resource key_vault 'Microsoft.KeyVault/vaults@2016-10-01' = {
  name: '${prefix}-thief-kv'
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: user_principal_id
        permissions: {
          keys: [
            'all'
          ]
          secrets: [
            'all'
          ]
          certificates: [
            'all'
          ]
        }
      }
    ]
  }
}

resource secret_APP_INSIGHTS_INSTRUMENTATION_KEY 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/APP-INSIGHTS-INSTRUMENTATION-KEY'
  properties: {
    value: app_insights_instrumentation_key
    attributes: {
      enabled: true
    }
  }
}

resource secret_DEVICE_GROUP_SYMMETRIC_KEY 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/DEVICE-GROUP-SYMMETRIC-KEY'
  properties: {
    value: 'Incomplete deployment. This value should be populated by create-thief-instance.sh'
    attributes: {
      enabled: true
    }
  }
}

resource secret_DEVICE_ID_SCOPE 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/DEVICE-ID-SCOPE'
  properties: {
    value: dps.properties.idScope
    attributes: {
      enabled: true
    }
  }
}

resource secret_DEVICE_PROVISIONING_HOST 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/DEVICE-PROVISIONING-HOST'
  properties: {
    value: dps.properties.deviceProvisioningHostName
    attributes: {
      enabled: true
    }
  }
}

resource secret_EVENTHUB_CONNECTION_STRING 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/EVENTHUB-CONNECTION-STRING'
  properties: {
    value: eventhub_connection_string
    attributes: {
      enabled: true
    }
  }
}

resource secret_EVENTHUB_CONSUMER_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/EVENTHUB-CONSUMER-GROUP'
  properties: {
    value: '\$default'
    attributes: {
      enabled: true
    }
  }
}

resource secret_IOTHUB_NAME 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/IOTHUB-NAME'
  properties: {
    value: '${iothub.name}'
    attributes: {
      enabled: true
    }
  }
}

resource secret_RESOURCE_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/RESOURCE-GROUP'
  properties: {
    value: resourceGroup().name
    attributes: {
      enabled: true
    }
  }
}

resource secret_IOTHUB_CONNECTION_STRING 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/IOTHUB-CONNECTION-STRING'
  properties: {
    value: iothub_connection_string
    attributes: {
      enabled: true
    }
  }
}

resource secret_SUBSCRIPTION_ID 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/SUBSCRIPTION-ID'
  properties: {
    value: subscription().subscriptionId
    attributes: {
      enabled: true
    }
  }
}

resource secret_SHARED_SUBSCRIPTION_ID 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/SHARED-SUBSCRIPTION-ID'
  properties: {
    value: shared_subscription_id
    attributes: {
      enabled: true
    }
  }
}

resource secret_SHARED_KEYVAULT_NAME 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/SHARED-KEYVAULT-NAME'
  properties: {
    value: shared_keyvault_name
    attributes: {
      enabled: true
    }
  }
}

resource secret_SHARED_RESOURCE_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${key_vault.name}/SHARED-RESOURCE-GROUP'
  properties: {
    value: shared_resource_group
    attributes: {
      enabled: true
    }
  }
}


output subscription_id string=subscription().subscriptionId
output iothub_name string=iothub.name
output dps_instance_name string=dps.name
output keyvault_name string=key_vault.name


