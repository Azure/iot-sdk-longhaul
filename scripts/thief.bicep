// Copyright (c) Microsoft. All rights reserved.
// Licensed under the MIT license. See LICENSE file in the project root for
// full license information.

param location string
param prefix string
param thief_runs_resource_group string
param thief_app_insights_instrumentation_key string
param thief_container_registry_host string
param thief_container_registry_password string
param thief_container_registry_shortname string
param thief_container_registry_user string
param user_principal_id string
param thief_shared_subscription_id string
param thief_shared_keyvault_name string
param thief_shared_resource_group string

resource thief_iot_hub 'Microsoft.Devices/IotHubs@2020-08-01' = {
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
var shared_access_key_name = '${listKeys(thief_iot_hub.id, '2020-04-01').value[0].keyName}'
var shared_access_key = '${listKeys(thief_iot_hub.id, '2020-04-01').value[0].primaryKey}'
var thief_iot_hub_connection_string = 'HostName=${thief_iot_hub.name}.azure-devices.net;SharedAccessKeyName=${shared_access_key_name};SharedAccessKey=${shared_access_key}'
var thief_eventhub_connection_string = 'Endpoint=${thief_iot_hub.properties.eventHubEndpoints.events.endpoint};SharedAccessKeyName=${shared_access_key_name};SharedAccessKey=${shared_access_key};EntityPath=${thief_iot_hub.properties.eventHubEndpoints.events.path}'

resource thief_dps 'Microsoft.Devices/provisioningServices@2020-03-01' = {
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
        connectionString: thief_iot_hub_connection_string
        location: location
      }
    ]
    allocationPolicy: 'Hashed'
  }
}

resource thief_key_vault 'Microsoft.KeyVault/vaults@2016-10-01' = {
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
        objectId: thief_container_identity.properties.principalId
        permissions: {
          secrets: [
            'get'
          ]
        }
      }
      {
        tenantId: subscription().tenantId
        objectId: user_principal_id
        permissions: {
          keys: [
            'get'
            'list'
            'update'
            'create'
            'import'
            'delete'
            'recover'
            'backup'
            'restore'
          ]
          secrets: [
            'get'
            'list'
            'set'
            'delete'
            'recover'
            'backup'
            'restore'
          ]
          certificates: [
            'get'
            'list'
            'update'
            'create'
            'import'
            'delete'
            'recover'
            'managecontacts'
            'manageissuers'
            'getissuers'
            'listissuers'
            'setissuers'
            'deleteissuers'
          ]
        }
      }
    ]
  }
}

resource thief_container_identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2018-11-30' = {
  name: 'thief-container-identity'
  location: location
}

resource secret_THIEF_APP_INSIGHTS_INSTRUMENTATION_KEY 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-APP-INSIGHTS-INSTRUMENTATION-KEY'
  properties: {
    value: thief_app_insights_instrumentation_key
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_CONTAINER_REGISTRY_HOST 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-CONTAINER-REGISTRY-HOST'
  properties: {
    value: thief_container_registry_host
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_CONTAINER_REGISTRY_PASSWORD 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-CONTAINER-REGISTRY-PASSWORD'
  properties: {
    value: thief_container_registry_password
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_CONTAINER_REGISTRY_SHORTNAME 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-CONTAINER-REGISTRY-SHORTNAME'
  properties: {
    value: thief_container_registry_shortname
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_CONTAINER_REGISTRY_USER 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-CONTAINER-REGISTRY-USER'
  properties: {
    value: thief_container_registry_user
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_DEVICE_GROUP_SYMMETRIC_KEY 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-DEVICE-GROUP-SYMMETRIC-KEY'
  properties: {
    value: 'Will be populated by deploy.sh'
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_DEVICE_ID_SCOPE 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-DEVICE-ID-SCOPE'
  properties: {
    value: thief_dps.properties.idScope
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_DEVICE_PROVISIONING_HOST 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-DEVICE-PROVISIONING-HOST'
  properties: {
    value: thief_dps.properties.deviceProvisioningHostName
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_EVENTHUB_CONNECTION_STRING 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-EVENTHUB-CONNECTION-STRING'
  properties: {
    value: thief_eventhub_connection_string
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_EVENTHUB_CONSUMER_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-EVENTHUB-CONSUMER-GROUP'
  properties: {
    value: '\$default'
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_IOTHUB_NAME 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-IOTHUB-NAME'
  properties: {
    value: '${thief_iot_hub.name}'
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_RESOURCE_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-RESOURCE-GROUP'
  properties: {
    value: resourceGroup().name
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_RUNS_RESOURCE_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-RUNS-RESOURCE-GROUP'
  properties: {
    value: thief_runs_resource_group
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_SERVICE_CONNECTION_STRING 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-SERVICE-CONNECTION-STRING'
  properties: {
    value: thief_iot_hub_connection_string
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_SUBSCRIPTION_ID 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-SUBSCRIPTION-ID'
  properties: {
    value: subscription().subscriptionId
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_USER_RESOURCE_ID 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-USER-RESOURCE-ID'
  properties: {
    value: resourceId('Microsoft.ManagedIdentity/userAssignedIdentities', thief_container_identity.name)
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_SHARED_SUBSCRIPTION_ID 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-SHARED-SUBSCRIPTION-ID'
  properties: {
    value: thief_shared_subscription_id
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_SHARED_KEYVAULT_NAME 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-SHARED-KEYVAULT-NAME'
  properties: {
    value: thief_shared_keyvault_name
    attributes: {
      enabled: true
    }
  }
}

resource secret_THIEF_SHARED_RESOURCE_GROUP 'Microsoft.KeyVault/vaults/secrets@2016-10-01' = {
  name: '${thief_key_vault.name}/THIEF-SHARED-RESOURCE-GROUP'
  properties: {
    value: thief_shared_resource_group
    attributes: {
      enabled: true
    }
  }
}


output thief_subscription_id string=subscription().subscriptionId
output thief_iothub_name string=thief_iot_hub.name
output thief_dps_instance_name string=thief_dps.name
output thief_keyvault_name string=thief_key_vault.name


