# Names and IDs

version .1

There are a number of names and IDs used in THIEF.  This table describes some of them:

| Identifier | format | Meaning |
| - | - | - |
| `servicePool` | string | Name of pool that a service app belongs to. |
| `requestedServicePool` | string | Name of pool that a device app would like to pair with. |
| `runId` | guid | Guid representing a single run of a device app.  Regenerated every time the device app launches. |
| `serviceInstanceId` | guid | Guid representing a single run of a service app.  Regenerated every time the service app launches. |
| `serviceAckId` | guid | Guid used to represent the ACK of a thief operation. |

## servicePool notes
* A service pool contains one or more running service apps.
* Each running service app belongs to exactly one pool.
* Service pools were added to support a fallback scenario where a device could detect a non-responsive service app and decide to pair with a different service app.
* Since service fallback isn't implemented, there currently no advantage to having more than one service app in any given pool.

## requestedServicePool notes
* A device specifies the name of a service pool that it would like to pair with.
* The device _must_ specify a requested service pool.
* Any service app in the requested pool can pair with the device app.
* A service app cannot pair with a device app that is requesting a different pool.
* If no service apps are available in the device's requested pool, the pairing fails.

## serviceAck notes
* When the device app needs the service app to verify some behavior, it includes a pingackId ID in the verification request.
* When the service app verifies the behavior, it sends a serviceAckResponse message to the decvice which includes the appropriate serviceAckId.

