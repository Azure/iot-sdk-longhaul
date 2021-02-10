# Azure Monitor tagging

All telemetry sent to Azure Monitor, whether traces, metrics, or spans, should follow this guide.

## Overloading of default dimensions

A few built-in Azure Monitor fields are overloaded:

| field | overload |
| - | - |
| `cloud_RoleName` | Either `device` or `service` |
| `cloud_RoleInstance` | `runId` for the process producing telemetry. |

## customDimensions used for all languages

```json
  {
    "sdkLanguageVersion": "3.8.2",
    "sdkLanguage": "python",
    "sdkVersion": "2.2.3",
    "deviceId": "bertk_test_device_4",
    "osType": "Linux",
    "poolId": "bertk_desktop_pool",
    "runId": "3c4d68ed-e8ac-422e-85c6-5937a92c1c43",
    "hub": "thief-hub-1.azure-devices.net",
    "transport": "MQTT"
  }
```

| field | format | device/service | meaning |
| - | - | - | - |
| `sdkLanguageVersion` | string | both | see same variable in [metrics.md](./metrics.md) |
| `sdkLanguage` | string | both | see same variable in [metrics.md](./metrics.md) |
| `sdkVersion` | string | both | see same variable in [metrics.md](./metrics.md) |
| `osType` | string | both | see same variable in [metrics.md](./metrics.md) |
| `poolId` | string | both | name of service pool being used |
| `hub` | string | both | name of hub being used for testing |
| `transport` | string | device | transport being used, if available One of `mqtt`, `mqttws`, `amqp`, or `amqpws` |
| `deviceId` | string | both. |  device ID being used. Some service logs don't contain this. |
| `runId` | string | both |  guid representing the run of the device app for this message. Some service logs don't contain this. |
| `serviceInstanceId` | string | service |  guid representing the run of the service app for this message. (service apps only). |

### Notes on deviceId and RunId
Some service app logs are device specific and contain `deviceId` and `runId` values.
Other service app logs are not device specific and do not contain `deviceId` and `runId` values.

## Automaticly populated fields for Python traces.

```json
  {
    "lineNumber": "291",
    "fileName": "service.py",
  }
```

| field | format | meaning |
| - | - | - |
| `level` | string | debug level for generated message |
| `module`| string | module generating message (without path and extension) |

## Fields for recording run details

| field | format | meaning |
| - | - | - |
| `runReason` | string | Reason the test is running.  Free-form string added to `StartingRun` events to explain why the run is happening.  |
| `exitReason` | string | Reason the test is exiting.  Free-form string added to `EndingRun` events to explain why the run stopped. |


## Metric names

Metrics sent to Azure Monitor are defined in [metrics.md](./metrics.md).

