# THIEF Azure resources

verion .1

## Organization

Azure resources used by THIEF are split into _instance_ and _shared_ resources.
* Instance resources are the things we're testing, such as IoT Hub and DPS instances.
* Shared resources are the things we use for reporting and coordination of tests.

This division is necessary because we want test isolation (instance resources) and also a global view of tests (shared resources).
* Test isolation means that one set of tests (say Python) cannot cause another set of tests (say .net) to fail by exhausing things like Hub resources.  For example, if a Python test causes C2D throttling, we don't want this to affect C# tests.
* A global view of tests means that we can have one dashboard showing all test runs with a single way to find all test results.

Instance and shared resources may be in different Azure subscriptions.
This is necessary to support developers running under their own subscriptions while still reporting to the global stores.

## Shared THIEF resources

All of these resources are under the subscription `THIEF_SHARED_SUBSCRIPTION_ID` in the `THIEF_SHARED_RESOURCE_GROUP` resource group.

`THIEF_SHARED_KEYVAULT_NAME` has a keyvault with secrets for all shared resources.
This kevault is used to seed the instance keyvault and many of the secrets in this keyvault are duplicated in the instance keyvault

`THIEF_APP_INSIGHTS_INSTRUMENTATION_KEY` is the entrypoint for the shared App Insights intance.

`THIEF_CONTAINER_REGISTRY_HOST` is the shared container registry.

There is also a shared Log Analytics workspace and a shared Azure Storage account, but these are not exposed to test scripts.

## Instance THIEF resources

All of these resources are under the subscription `THIEF_SUBSCRIPTION_ID` in the `THIEF_RESOURCE_GROUP` resource group.

`THIEF_KEYVAULT_NAME` is the keyvault that holds secrets for the thief instance which is being tested.

`THIEF_IOTHUB_NAME` is the Azure IoT Hub instance that is being tested.

`THIEF_DEVICE_PROVISIONING_HOST` is the DPS instance that is being tested.

Container instances for running tests use `THIEF_SUBSCRIPTION_ID` subscription, and go into the `THIEF_RUNS_RESOURCE_GROUP` resource group.

## Fetching secrets

Thief secrets are retrieved by setting `THIEF_SUBSCRIPTION_ID` and `THIEF_KEYVAULT_NAME` environment variables and then calling `scripts/fetch_secrets.sh`

## Creating a new THIEF instance

To create a new thief instance:
1. Set your environment variables for the shared resources by setting `THIEF_SUBSCRIPTION_ID` and `THIEF_KEYVAULT_NAME` to the shared values and calling `scripts/fetch_secrets.sh`
```
(longhaul) bertk@bertk-hp:~/repos/longhaul$ export THIEF_SUBSRIPTION_ID=<REDACTED> && export THIEF_KEYVAULT_NAME=<REDACTED> && source ./scripts/fetch-secrets.sh
```

2. Use `az account set --subsciption <foo>` to set the subsciption you want to use for your instance resources.  Use `az account list` if you need help finding the subscription id.
```
(longhaul) bertk@bertk-hp:~/repos$ az account set --subscription "<REDACTED>"
```

3. Call `scripts/create-thief-instance.sh`, passing in a resource prefix (such as your email address) to create the thief resources.
```
(longhaul) bertk@bertk-hp:~/repos/longhaul$ ./scripts/create-thief-instance.sh bertk7 --location westus2
```

4. When resource creation is complete, the `create-thief-instance` script will give you a copy/paste blob you can use to load instance secrets into your environment.
```
}
Deployment thief-24402 success
To activate this environment, run:
export THIEF_SUBSCRIPTION_ID="<REDACTED>" && \
export THIEF_KEYVAULT_NAME="bertk7-thief-kv" && \
source "/home/bertk/repos/longhaul/scripts/fetch-secrets.sh"
(longhaul) bertk@bertk-hp:~/repos/longhaul$
```

5. After you have your copy/paste blob from step 4, you don't need to worry about setting your environment for shared resources anymore.
The instance keyvault contains copies of all the shared secrets.

```
(longhaul) bertk@bertk-hp:~/repos/longhaul$ export THIEF_SUBSCRIPTION_ID="<REDACTED>" && \
> export THIEF_KEYVAULT_NAME="bertk7-thief-kv" && \
> source "/home/bertk/repos/longhaul/scripts/fetch-secrets.sh"
```



