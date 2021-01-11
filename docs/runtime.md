# Runtime organization and Device <--> Service app pairing

## Two apps for every test

Tests run with a device app paired together with a service app.
They work in concert to test the features, meaning both apps are required for the tests to run.
This is because some features are initiated by the device (like sending telemetry) and other features are initiated by the service (like sending C2D).

Sometimes the device app initiates actions and the service app responds.
Other times, the service app initiates actions and the device app responds.

For example, if a service app sends a C2D message to the device, the device app needs to verify that the C2D message was received.
Likewise, if a device app sends a telemetry message, the service app needs to verify that the message was received.

Even though the device app and the service app both initiate actions, the device app "controls" the test.
It does this by first choosing a service app to "pair" with and then by instructing the service app to initiate actions.
This "pairing" procedure and the various "instructing" procedures are well defined in other documents.

## Local, or remote, or both

The device app and the service app can be either:
* remote (running inside an Azure container), or
* local (running on a local box or in a VM)

They can also be mixed, with the devce app running locally and the service app running inside an Azure container, or vise-versa.

## A one-to-many relationship

Each device app:
* runs with one IoT Hub deivce ID
* pairs with a single service app
* decides _which_ service app to pair with
* controls the parameters of what's being tested
* controls the lifetime of the test

Each service app:
* runs with one IoT Hub connection string
* is able to pair with multiple device apps
* listens for "pairing requirests" from device apps and responds if it is availble for pairing.
- responds to paired device actions
* initiates actions for paired devices to respond to

## A "pool" of service apps

A "service app pool" is a group of one or more service apps that are available for pairing.
All apps in the pool share the same "service pool name", which is an arbitrary string which is used to pair device and service apps.

Right now, device apps and service apps pair based solely on this pool name.
In the future, this pairing might use a different heuristic, perhaps based on capabilities, but right now only the service pool name is used.

