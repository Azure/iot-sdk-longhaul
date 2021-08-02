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
THIEF_KEYVAULT_NAME = secrets.get("thiefKeyvaultName", None)

# Device ID used when running thief tests
THIEF_DEVICE_ID = secrets.get("thiefDeviceId", None)

# Name of service pool that a specific service app is running under
THIEF_SERVICE_POOL = secrets.get("thiefServicePool", None)

# Name of service pool that a specific device app would like to pair with.
THIEF_REQUESTED_SERVICE_POOL = secrets.get("thiefRequestedServicePool", None)

# ID for subscription that holds thief resources
THIEF_SUBSCRIPTION_ID = secrets.get("thiefSubscriptionId", None)

# Connection string for the iothub instance that thief is using for tests
THIEF_SERVICE_CONNECTION_STRING = secrets.get("thiefServiceConnectionString", None)

# Name of the provisioning host that thief is using for tests
THIEF_DEVICE_PROVISIONING_HOST = secrets.get("thiefDeviceProvisioningHost", None)

# IDScope for the provisioning host that thief is using for tests.
THIEF_DEVICE_ID_SCOPE = secrets.get("thiefDeviceIdScope", None)

# Symmetric Key for the provisioning device group that thief is using for tests.
THIEF_DEVICE_GROUP_SYMMETRIC_KEY = secrets.get("thiefDeviceGroupSymmetricKey", None)

# Connection string for the eventhub instance that thief is using
THIEF_EVENTHUB_CONNECTION_STRING = secrets.get("thiefEventhubConnectionString", None)

# Consumer group that thief is using when monitoring eventhub events
THIEF_EVENTHUB_CONSUMER_GROUP = secrets.get("thiefEventhubConsumerGroup", None)

# App Insights instrumentation key that thief is using for pushing metrics and log events
THIEF_APP_INSIGHTS_INSTRUMENTATION_KEY = secrets.get("thiefAppInsightsInstrumentationKey", None)

# Host for the ontainer regsitry that thief is using for images under test (DNS name)
THIEF_CONTAINER_REGISTRY_HOST = secrets.get("thiefContainerRegistryHost", None)

# Password to use when logging into thief container registry
THIEF_CONTAINTER_REGISTRY_PASSWORD = secrets.get("thiefContainerRegistryPassword", None)

# User name to use when logging into thief container registry
THIEF_CONTAINER_REGISTRY_USER = secrets.get("thiefContainerRegistryUser", None)

# Short name for thief container registry.  Pprobably the DNS name without the .azurecr.io suffix
THIEF_CONTAINER_REGISTRY_SHORTNAME = secrets.get("thiefContainerRegistryShortname", None)

# Resource group used for holding running thief containers
THIEF_RUNS_RESOURCE_GROUP = secrets.get("thiefRunsResourceGroup", None)

# Resource ID for the managed identity that thief uses for containers under test
THIEF_USER_RESOURCE_ID = secrets.get("thiefUserResourceId", None)

# Resource group used for holding thief resources
THIEF_RESOURCE_GROUP = secrets.get("thiefResourceGroup", None)

# Name of thief iothub.  Probably DNS name for the hub without the azure-devices.net suffix
THIEF_IOTHUB_NAME = secrets.get("thiefIothubName", None)

# Name of keyvault holding secrets for thief shared resources.
THIEF_SHARED_KEYVAULT_NAME = secrets.get("thiefSharedKeyvaultName", None)

# Subscription ID used for thief shared resources.
THIEF_SHARED_SUBSCRIPTION_ID = secrets.get("thiefSharedSubscriptionId", None)

# Resource group used for holding thief shared resources.
THIEF_SHARED_RESOURCE_GROUP = secrets.get("thiefSharedResourceGroup", None)

# Connection string for device under test
THIEF_DEVICE_CONNECTION_STRING = secrets.get("thiefDeviceConnectionString", None)

del secrets
del this_file_path
del json_file_path
