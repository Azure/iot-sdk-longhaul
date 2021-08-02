# !/bin/bash
# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

script_dir=$(cd "$(dirname "$0")" && pwd)
json_file="$(realpath ${script_dir}/..)/_thief_secrets.json"

subscription_id=$1
keyvault_name=$2

if [ "${subscription_id}" == "" ] || [ ${keyvault_name} == "" ]; then
    echo "Usage: $0 [subscription_id] [keyvault_name]"
    exit 1
fi

JSON="{}"

function add-json {
    json_name=$1
    value=$2
    JSON=$(echo "$JSON" | jq -c \
        --arg key   "$json_name" \
        --arg value "$value" \
        '. | .[$key]=$value')
}

function add-secret {
    json_name=$1
    kv_name=$2
    echo "Fetching ${json_name}"
    value=$(az keyvault secret show --subscription ${subscription_id} --vault-name ${keyvault_name} --name ${kv_name} | jq -r ".value")
    add-json $json_name "$value"

}

# This script is intended for developer workstations.  When these tests runs in the cloud,
# they use a different mechanism to get secrets.
#
# Since this is a developer workstation, set the device ID and run IDs so the developer runs
# all communicate with each other instead of accidentally pairing with service apps that are
# running in the cloud.
add-json keyvaultName "${keyvault_name}"
add-json subscriptionId "${subscription_id}"
add-json deviceId "${USER}_test_device"
add-json servicePool "${USER}_desktop_pool"
add-json requestedServicePool "${USER}_desktop_pool"

add-secret iothubConnectionString IOTHUB-CONNECTION-STRING
add-secret deviceProvisioningHost DEVICE-PROVISIONING-HOST
add-secret deviceIdScope DEVICE-ID-SCOPE
add-secret deviceGroupSymmetricKey DEVICE-GROUP-SYMMETRIC-KEY
add-secret eventhubConnectionString EVENTHUB-CONNECTION-STRING
add-secret eventhubConsumerGroup EVENTHUB-CONSUMER-GROUP
add-secret appInsightsInstrumentationKey APP-INSIGHTS-INSTRUMENTATION-KEY
add-secret resourceGroup RESOURCE-GROUP
add-secret iothubName IOTHUB-NAME
add-secret sharedKeyvaultName SHARED-KEYVAULT-NAME
add-secret sharedSubscriptionId SHARED-SUBSCRIPTION-ID
add-secret sharedResourceGroup SHARED-RESOURCE-GROUP



echo Done fetching secrets
echo ${JSON} | jq -S '.' > "${json_file}"
echo Secrets written to ${json_file}

