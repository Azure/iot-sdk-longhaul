# THIEF environment variables

verion .1

## Coulmns

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
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_SUBSCRIPTION\_ID | - | - | X | keyvault | GUID | Azure subscription ID holding all THIEF resources | 
| THIEF\_ACTIVE\_DIRECTORY\_TENANT | - | - | X | keyvault | hostname | Azure active directory tenant.  Uesd to consturct portal URLs. |
| THIEF\_RESOURCE\_GROUP | - | - | X | keyvault | string | Name of resource group containing all THIEF resources |
| THIEF\_RUNS\_RESOURCE\_GROUP | - | - | X | keyvault | string |  Name of resource group containing all THIEF container instances |
| THIEF\_USER\_RESOURCE\_ID | - | - | X | keyvault | string | Azure resource ID for the managed identity that container instances run uner.  Used to get access to keyvault secrets from inside container instances |

## App Insights
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_APP\_INSIGHTS\_CONNECTION\_STRING | X | X | X | keyvault | connection string | Connection string used to push secrets into App Insights.  Starts wiuth `InstrumentationKey=`. |
| THIEF\_APP\_INSIGHTS\_NAME | - | - | X | keyvault | string | name of App Insights resouce |

## IoTHub Service
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_IOTHUB\_NAME | - | - | X |  keyvault | string | Name of IoT Hub instance being used for testing |
| THIEF\_SERVICE\_CONNECTION\_STRING | X | - | X | keyvault | connection string | service connection strong for the IoT Hub instance being used for testing |

## EventHub
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_EVENTHUB\_CONNECTION\_STRING | X | - | X | keyvault | connection string | connection string used to connect to eventhub instance which receives device telemetry |
| THIEF\_EVENTHUB\_CONSUMER\_GROUP | X | - | X | keyvault | connection string | consumer group to use when receiving device telemetry |

## DPS
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_DEVICE\_PROVISIONING\_HOST | - | X | X | keyvault | hostname | provisioning host |
| THIEF\_DEVICE\_GROUP\_SYMMETRIC\_KEY | - | X | X | keyvault | string | group symmetric key for provisioning test devices |
| THIEF\_DEVICE\_ID\_SCOPE | - | X | X | keyvault | string | DPS id scope for provisioning test devices |

## Azure Container Service
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_CONTAINER\_REGISTRY\_SHORTNAME | - | - | X | keyvault | string | name of container registry (without azurecr.io suffix) |
| THIEF\_CONTAINER\_REGISTRY\_USER | - | - | X | keyvault | string | user name for logging into container registry (used when pushing images) |
| THIEF\_CONTAINER\_REGISTRY\_HOST | - | - | X | keyvault | hostname | host for containerr registry (with azurecr.io suffix) |
| THIEF\_CONTAINER\_REGISTRY\_PASSWORD | - | - | X | keyvault | hostname | password for logging into container registry (used when pushing images) |

## Thief identities
| variable name | service | device | developer | source | format | meaning |
| - | - | - | - | - | - | - |
| THIEF\_DEVICE\_ID | - | X | X | manual | string | registration ID and device id for test device |
| THIEF\_SERVICE\_POOL | X | - | X | manual | string | name of service pool to use for service application |
| THIEF\_REQUESTED\_SERVICE\_POOL | - | X | X | manual | string | name of service pool to request for device application |
| THIEF\_DEVICE\_RUN\_ID | - | X | X | manual | string | option runId to use for _device_ executable.  If not specified, a guid will be generated |
| THIEF\_SERVICE\_RUN\_ID | X | - | X | manual | string | option runId to use for _service_ executable.  If not specified, a guid will be generated |
