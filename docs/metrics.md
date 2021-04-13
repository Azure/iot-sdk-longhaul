# Metrics

Test metrics are sent to 3 different places:
1. reported properies
2. test telemetry message bodies
3. Azure Monitor

Not all metrics are sent to all destinations.

| group | reported properties | test telemetry | Azure Monitor |
| - | - | - | - |
| Session Metrics | X | X | - |
| Test Metrics | X | X | X |
| System Health Metrics | - | X | X |
| Latency Metrics | - | - | X |

## Metric name casing

When metrics are set in json (for reported properties and telemetry), the name is written using camelCase.
When metrics are pushed to Azure monitor, the name is written using PascalCase.

For example, the metric `receiveC2dCountReceived` is named:
* `receiveC2dCountReceived` with a lower case `r` when used in desired properties and telemetry, and
* `ReceiveC2dCountReceived` with an upper case `R` when used as an Azure Monitor metric name

## Session Metrics

Some session metrics are recorded at the beginning of the run and others are recorded throughout the run.
They record details on the progress of the current run.

```json
  {
    "reported": {
      "thief": {
        "sessionMetrics": {
          "exitReason": "Main thread raised <class KeyboardInterrupt>",
          "latestUpdateTimeUtc": "2020-12-14T21:14:57.447061",
          "runStartUtc": "2020-12-14T21:13:22.430280+00:00",
          "runState": "interrupted",
          "runTime": "0:01:35.016760"
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `runState` | string | State of the current run.  One of `waiting`, `running`, `failed`, `complete`, or `interrupted` |
| `runStartUtc` | string | DateTime in UTC for the start of the current run. |
| `runTime` | string | Elapsed time for current run |
| `latestUpdateTimeUtc` | string | DateTime in UTC for most recent update to thie structure. |
| `exitReason` | string | free-form string indicating reason for test to exit.  Most likely exception text or other error string.  Only valid for `failed`, `complete`, or `interrupted`. |

## Test Metrics

Test metrics are recorded throughout the run and they record statistics on the various test operations that are occuring.
Most or all of the test metrics overlap with metrics that are sent in telemetry and pushed to Azure Monitor.

```json
  {
    "reported": {
      "thief": {
        "testMetrics": {
          "receiveC2dCountMissing": 0,
          "receiveC2dCountReceived": 0,
          "reportedPropertiesCountAdded": 0,
          "reportedPropertiesCountAddedButNotVerifiedByServiceApp": 0,
          "reportedPropertiesCountRemoved": 0,
          "reportedPropertiesCountRemovedButNotVerifiedByServiceApp": 0,
          "sendMessageCountExceptions": 0,
          "sendMessageCountInBacklog": 0,
          "sendMessageCountNotReceivedByServiceApp": 0,
          "sendMessageCountSent": 0,
          "sendMessageCountUnacked": 0
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `receiveC2dCountMissing` | integer | Count of c2d messages sent by service app but not (yet) received by device app.  Only applies to test c2d messages. |
| `receiveC2dCountReceived` | integer | Count of c2d messges received by device app.  Only applies to test c2d messges |
| `reportedPropertiesCountAdded` | integer | Count of reported properties added,  Only applies to `testContent` properties. |
| `reportedPropertiesCountRemoved` | integer | Count of reported properties removed,  Only applies to `testContent` properties. |
| `reportedPropertiesCountTimedOut` | integer | Count of reported property operations (add + remove) which timed out.  Only applies to `testContent` properties. |
| `sendMessageCountSent` | integer | Count of test telemetry messages sent |
| `sendMessageCountUnacked` | integer |  Count of test telemetry messages where send API did not complete and did not fail.  (most likely dropped in transit.) |
| `sendMessageCountExceptions` | integer | Count of test telemetry operations which failed.  Failures could be caused by raised exceptions or by messages withoug a matching `serviceAck`. |
| `sendMessageCountInBacklog` | integer | Count of test telemetry messages currently queued in the  acklock.  Queued messages are scheduled to be sent, but not yet in transit. Not all test implementations queue in the client, so this metric may be meaningless in cases where queueing happens inside the SDK. |
| `sendMessageCountNotReceivedByServiceApp` | integer | Count of test telemetry messages which were sent, ack'ed by the transport (`PUBACK`), but not received by the service (no `serviceAck`) |
| `getTwinCountSucceeded` | integer | Count of getTwin operations which succeeded and returned the expected property values. |
| `getTwinCountTimedOut` | integer | Count of getTwin operations which did not return the expected property values within the timeout period. |
| `desiredPropertyPatchCountReceived` | integer | Count of desired properties patch operations which were received with the expected property values. |
| `desiredPropertyPatchCountTimedOut` | integer | Count of the desired property patch operations which were not received with the expected property values within the timeout period. |

## System Health Metrics

```json
  {
    "reported": {
      "thief": {
        "systemHealthMetrics": {
          "processBytesInAllHeaps": 2490519552,
          "processCpuPercent": 3.0,
          "processPrivateBytes": 27181056,
          "processWorkingSet": 41455616,
          "processWorkingSetPrivate": 27181056
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `processBytesInAllHeaps` | integer | Count of bytes for all _virtual_ memory used by the process. |
| `processCpuPercent` | float | CPU usage of the test process, as a percentage of total CPU available.  Using 100% of 1 core on a 4 core system would evaluate to 25%. |
| `processPrivateBytes` | integer | Amount of non-shared physical memory (in bytes) used by the process.  May be redundant and equal to `processWorkingSetPrivate`. |
| `processWorkingSet` | integer | All physical memory (in bytes) used by the process. |
| `processWorkingSetPrivate` | integer | Amount of non-shared physical memory (in bytes) used by the process. |

## Latency metrics
Latency metrics are only pushed to Azure Monotor.

| metric name | format | meaning |
| - | - | - |
| `LatencyQueueMessageToSendInMilliseconds` | float | Number of milliseconds between a message is queued to send and when it is actually sent. |
| `LatencySendMessageToServiceAckInSeconds` | float | Number of seconds between when a message is sent and when the corresponding `serviceAck` is received back from the service. |
| `LatencyAddReportedPropertyToServiceAckInSeconds` | float | Number of seconds between when a reported property is added and when the corresponding `serviceAck` is received back from the service. |
| `LatencyRemoveReportedPropertyToServiceAckInSeconds` | float | Number of seconds betweenwhen a reported property is removed and when the corresponding `serviceAck` is received back from the service. |
| `LatencyBetweenC2dInSeconds` | float | Number of seconds between consecutive c2d messages. |





