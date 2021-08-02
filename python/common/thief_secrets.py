# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import os
import json
import logging

logger = logging.getLogger(__name__)

this_file_path = os.path.dirname(os.path.realpath(__file__))
json_file_path = os.path.realpath(os.path.join(this_file_path, "../../_thief_secrets.json"))

with open(json_file_path, "r") as f:
    secrets = json.load(f)
# Name of keyvault that stores thief secrets
KEYVAULT_NAME = secrets.get("keyvaultName", None)

# Device ID used when running thief tests
DEVICE_ID = secrets.get("deviceId", None)

# Name of service pool that a specific service app is running under
SERVICE_POOL = secrets.get("servicePool", None)

# Name of service pool that a specific device app would like to pair with.
REQUESTED_SERVICE_POOL = secrets.get("requestedServicePool", None)

# ID for subscription that holds thief resources
SUBSCRIPTION_ID = secrets.get("subscriptionId", None)

# Connection string for the iothub instance that thief is using for tests
IOTHUB_CONNECTION_STRING = secrets.get("iothubConnectionString", None)

# Name of the provisioning host that thief is using for tests
DEVICE_PROVISIONING_HOST = secrets.get("deviceProvisioningHost", None)

# IDScope for the provisioning host that thief is using for tests.
DEVICE_ID_SCOPE = secrets.get("deviceIdScope", None)

# Symmetric Key for the provisioning device group that thief is using for tests.
DEVICE_GROUP_SYMMETRIC_KEY = secrets.get("deviceGroupSymmetricKey", None)

# Connection string for the eventhub instance that thief is using
EVENTHUB_CONNECTION_STRING = secrets.get("eventhubConnectionString", None)

# Consumer group that thief is using when monitoring eventhub events
EVENTHUB_CONSUMER_GROUP = secrets.get("eventhubConsumerGroup", None)

# App Insights instrumentation key that thief is using for pushing metrics and log events
APP_INSIGHTS_INSTRUMENTATION_KEY = secrets.get("appInsightsInstrumentationKey", None)

# Resource group used for holding thief resources
RESOURCE_GROUP = secrets.get("resourceGroup", None)

# Name of thief iothub.  Probably DNS name for the hub without the azure-devices.net suffix
IOTHUB_NAME = secrets.get("iothubName", None)

# Name of keyvault holding secrets for thief shared resources.
SHARED_KEYVAULT_NAME = secrets.get("sharedKeyvaultName", None)

# Subscription ID used for thief shared resources.
SHARED_SUBSCRIPTION_ID = secrets.get("sharedSubscriptionId", None)

# Resource group used for holding thief shared resources.
SHARED_RESOURCE_GROUP = secrets.get("sharedResourceGroup", None)

# Connection string for device under test
DEVICE_CONNECTION_STRING = secrets.get("deviceConnectionString", None)

del secrets
del this_file_path
del json_file_path
