# pairing process

The pairing process is a handshake with 4 steps, all done with reported and desired properties:
1. A device app says "I need a partner" by setting its reported `serviceInstance` to `None`.
2. A service app says "I'm available" by setting the devices desired `serviceInstance` to the service app's `serviceInstance` guid.
3. The device app says "I choose you" by setting its reported `serviceInstance` to the `serviceInstance` guid of the chosen service

Once the device app sets its `serviceInstance` value, the pairing is complete.


## Step 1: device sets reported properties to start pairing.

The pairing stars with the device setting `properties/reported/thief/pairing/serviceInstance` to `None`.
This indicates that it doesn't have a paired service app and welcomes service apps to volunteer to pair by setting desired properties as described in step 2.

```json
  {
    "reported": {
      "thief": {
        "pairing": {
          "runId": "4d41c744-94bf-40ac-89bc-06f28b4dc9d2",
          "requestedServicePool": "bertk_desktop_pool",
          "serviceInstance": None
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `runId` | guid | Guid for the running device app instance.  re-generated each time the app launches |
| `requestedServicePool` | string | free-form name for the pool of service apps which are known to be valid.  This is the the only value that a service app uses to decide if it can pair with the device app |
| `serviceInstance` | guid | Guid of the selected service app. Since this step is starting the pairing process, this is set to `None` because no service app has been chosen yet. |

## Step 2: service sets desired properties to say that its available.

A service app can tell the device app that it's available for pairing by setting the `runId` and `serviceInstance` values as described below.

```json
  {
    "desired": {
      "thief": {
        "pairing": {
          "runId": "4d41c744-94bf-40ac-89bc-06f28b4dc9d2",
          "serviceInstance": "23ebf618-41e2-40d7-9964-a16ae9762a1c",
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `serviceInstance` | guid | Guid for the service app that wants to pair with the device app |
| `runId` | guid | Guid for the app that is being paired with. |

## Step 3: device sets reported properties to select service instance.

The device app selects a service instance by setting `properties/reported/thief/pairing/serviceInstance` to the service app's guid.

```json
  {
    "reported": {
      "thief": {
        "pairing": {
          "runId": "4d41c744-94bf-40ac-89bc-06f28b4dc9d2",
          "serviceInstance": "23ebf618-41e2-40d7-9964-a16ae9762a1c"
        }
      }
    }
  }
```

| field | format | meaning |
| - | - | - |
| `runId` | guid | Guid for the app that is being paired with. |
| `serviceInstance` | guid | Guid for the service app that was selected by the device app |


## Unpairing
When a device wishes to unpair with a service app, it can simply replace `properties/reported/thief/pairing/serviceInstance` with a new value or with `None`.
When the service app sees that this value has changed, it will consider the device to be "unpaird" and stop working with that device.


