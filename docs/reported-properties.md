# Reported properties

## System Properties

System properties are set one time at the beginning of the run and used to record details on the environment that the device client is running in.

```json
  {
    "reported": {
      "thief": {
        "systemProperties": {
          "language": "python",
          "languageVersion": "3.8.2",
          "osRelease": "#34~18.04.2-Ubuntu SMP Thu Oct 10 10:36:02 UTC 2019",
          "osType": "Linux",
          "sdkGithubBranch": null,
          "sdkGithubCommit": null,
          "sdkGithubRepo": null,
          "sdkVersion": "2.4.0"
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `language` | string | Language name, one of `python`, `node`, `.NET`, `c`, or `java` |
| `languageVersion` | string | Version of the language, such as `3.7`, `8`, etc.  Format depends on `language`. |
| `osRelease` | string | Release version of the OS.  Format depends on `osType` |
| `osType` | string | one of `Windows` or `Linux`.  Others will be added as necessary.  |
| `sdkGithubRepo` | string | If testing against code cloned from GitHub, name of repo, such as `Azure/azure-iot-sdk-python`.  Excluded if testing against code installed from a package repository. |
| `sdkGithubBranch` | string | If testing against code cloned from Github, name of branch, such as `master` Excluded if testing against code installed from a package repository. |
| `sdkGithubCommit` | string | If testing against code cloned from GitHub, sha of commit, such as `731f8fe`.  Excluded if testing against code installed from a package repository. |
| `sdkVersion` | string | Version of the device sdk, such as `2.4.0`.  The exact format of this string depends on the langauge and is defined below |

`sdkVersion` is only required if the code is running against a released SDK.
`sdkGithubRepo`, `sdkGithubBranch`, and `sdkGithubCommit` are only required if the code is running against an unreleased SDK.

## `language` and `languageVersion` formats

The following rules apply to the langauge and langaugeVersion fields:

| `langauge` | `languageVersion` rules | examples |
| - | - |
| Python | For cpython, use the PEP 440 major.minor.micro version number, followed by "async" if using the asyncio API. | `3.8.2` and `3.8.2 async` |
| node | not yet defined | |
| .NET | not yet defined | |
| c | not yet defined ||
| java | not yet defined ||

## `osType` and `osRelease` formats

`osRelease` should follow the same rules as the DeviceClientType field from the user agent string.

For `osType` == `linux`, an appropriate `osRelease` string would be `Linux #34~18.04.2-Ubuntu SMP Thu Oct 10 10:36:02 UTC 2019;x86_64`


## Test Confiuration

Test configuration is set one time at the beginning of the run and used to record details on how the test is configured.

```json
  {
    "reported": {
      "thief": {
        "config": {
            "pairingRequestSendIntervalInSeconds": 30,
            "pairingRequestTimeoutIntervalInSeconds": 900,
            "receiveC2dAllowedMissingMessageCount": 100,
            "receiveC2dIntervalInSeconds": 20,
            "reportedPropertiesUpdateAllowedFailureCount": 50,
            "reportedPropertiesUpdateIntervalInSeconds": 10,
            "sendMessageAllowedFailureCount": 1000,
            "sendMessageOperationsPerSecond": 1,
            "thiefAllowedClientLibraryExceptionCount": 10,
            "thiefMaxRunDurationInSeconds": 0,
            "thiefWatchdogFailureIntervalInSeconds": 300
        }
      }
    }
  }
```

### pairing configuration

These numbers define operational parameters for the pairing process

| field | format | meaning |
| - | - | - |
| `pairingRequestSendIntervalInSeconds` | integer | When pairing, how many seconds to wait for a response before re-sending the pairing request |
| `pairingRequestTimeoutIntervalInSeconds` | integer | When pairing, how many seconds in total to attempt pairing before failing |

### general test configuration

These numbers define operational parameters for execution of the test harness.

| field | format | meaning |
| - | - | - |
| `thiefMaxRunDurationInSeconds` | integer | Number of seconds to run the test for.  0 to run indefinitely. |
| `thiefWatchdogFailureIntervalInSeconds` | integer | How often to check thread watchdogs.  If an individual thread is inactive for this many seconds, the test fails.  Exact definition of "inactive" is arbitrary and may depend on implementation. |
| `thiefAllowedClientLibraryExceptionCount` | integer | How many exceptions can be raised by the device client before the test fails? |

### c2d test configuration

These numbers define operational parameters for testing c2d.

| field | format | meaning |
| - | - | - |
| `receiveC2dIntervalInSeconds` | integer | When testing c2d, how many seconds to wait between c2d message.  This only applies to test c2d messages and does not apply to serverAck messages. |
| `receiveC2dMissingMessageAllowedFailureCount` | integer | When testing c2d, how many mesages are allowed to be "missing" before the test fails. |

### reported property test configuration

These numbers define operational parameters for testing reported properties.

| field | format | meaning |
| - | - | - |
| `reportedPropertiesUpateAllowedFailureCount` | integer | Count of reported property updates that are allowed to fail without causing a test-run failure |
| `reportedPropertiesUpdateIntervalInSeconds` | integer |  How often to update reported properties.  This only applies to properties under `testContent` and does not apply to things like `testMetrics` and `sessionMetrics and `testControl`. |

### telemetry test configuratoin

These numbers define operational parameters for testing telemetry.  The name `sendMessage` is used in this context even though the specific SDK may use a function with a different name such as `send_message` or `sendEventAsync`

| field | format | meaning |
| - | - | - |
| `sendMessageOperationsPerSecond` | integer | How many `sendMessage` operations should be run per second |
| `sendMessageAllowedFailureCount` | integer | How many incomplete `sendMessage` calls are allowed.  This includes calls that are queued, sent but not acked, and sent but not verified by the service. |
