# THIEF environment variables

verion .1

## Columns

| column name | meaning |
| - | - |
| variable name | name of the environment variable |
| service | variable is available to service apps when running inside Azure container instances |
| device | variable is available to device apps when running inside Azure container instances |
| developer | variable is available to developers via fetch-secrets.sh |
| source | where the value comes from.  Either 'keyvault' for variables that come from keyvault, or 'manual' for variables that are manually set via some other route (script) |
| format | format of the variable |
| meaning | what the variable represents |

## Keyvault conventions
Since keyvault doesn't support underscores in secret names, keyvault secrets are names the same as the variable names, with underscores (\_) replaced with dashes (-)

e.g. The environment variable `THIEF_SUBSCRIPTION_ID` is stored as a keyvault seret named `THIEF-SUBSCRIPTION-ID`

## Azure resources

These variables are used for management of Azure resources used by THIEF.
See the [Azure resource usage](./azure-resources.md) document for details.

| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_SUBSCRIPTION_ID` | - | - | X | keyvault | GUID | Azure subscription ID holding all THIEF resources |
| `THIEF_RESOURCE_GROUP` | - | - | X | keyvault | string | Name of resource group containing all THIEF resources |
| `THIEF_RUNS_RESOURCE_GROUP` | - | - | X | keyvault | string |  Name of resource group containing all THIEF container instances |
| `THIEF_USER_RESOURCE_ID` | - | - | X | keyvault | string | Azure resource ID for the managed identity that container instances run under.  Used to get access to keyvault secrets from inside container instances |
| `THIEF_KEYVAULT_NAME` | - | - | X | manual | string | Keyvault name for THIEF secrets.  This variable, combined with `THIEF_SUBSCRIPTION_ID` is used to bootstrap all other variables. |
| `THIEF_SHARED_SUBSCRIPTION_ID` | - | - | X | keyvault | string | Subscription ID for Azure resources that are shared with all THIEF instances. |
| `THIEF_SHARED_KEYVAULT_NAME` | - | - | X | keyvault | string | Key vault name for resources shared with all THIEF instances. |
| `THIEF_SHARED_RESOURCE_GROUP` | - | - | X | keyvault | string | Name of resource group containing all shared THIEF resources. |

## App Insights
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_APP_INSIGHTS_INSTRUMENTATION_KEY` | X | X | X | keyvault | guid | Instrumentation key used to push secrets into App Insights. |

## IoTHub Service
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_IOTHUB_NAME` | X | - | X |  keyvault | string | Name of IoT Hub instance being used for testing |
| `THIEF_SERVICE_CONNECTION_STRING` | X | - | X | keyvault | connection string | service connection strong for the IoT Hub instance being used for testing |

## EventHub
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_EVENTHUB_CONNECTION_STRING` | X | - | X | keyvault | connection string | connection string used to connect to eventhub instance which receives device telemetry |
| `THIEF_EVENTHUB_CONSUMER_GROUP` | X | - | X | keyvault | connection string | consumer group to use when receiving device telemetry |

## DPS
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_DEVICE_PROVISIONING_HOST` | - | X | X | keyvault | hostname | provisioning host |
| `THIEF_DEVICE_GROUP_SYMMETRIC_KEY` | - | X | X | keyvault | string | group symmetric key for provisioning test devices |
| `THIEF_DEVICE_ID_SCOPE` | - | X | X | keyvault | string | DPS id scope for provisioning test devices |

## Azure Container Service
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_CONTAINER_REGISTRY_SHORTNAME` | - | - | X | keyvault | string | name of container registry (without azurecr.io suffix) |
| `THIEF_CONTAINER_REGISTRY_USER` | - | - | X | keyvault | string | user name for logging into container registry (used when pushing images) |
| `THIEF_CONTAINER_REGISTRY_HOST` | - | - | X | keyvault | hostname | host for containerr registry (with azurecr.io suffix) |
| `THIEF_CONTAINER_REGISTRY_PASSWORD` | - | - | X | keyvault | hostname | password for logging into container registry (used when pushing images) |

## Thief identities
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| `THIEF_DEVICE_ID` | - | X | X | manual | string | registration ID and device id for test device |
| `THIEF_SERVICE_POOL` | X | - | X | manual | string | name of service pool to use for service application |
| `THIEF_REQUESTED_SERVICE_POOL` | - | X | X | manual | string | name of service pool to request for device application |
