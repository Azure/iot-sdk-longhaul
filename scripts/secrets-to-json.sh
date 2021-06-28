# !/bin/bash
# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

script_dir=$(cd "$(dirname "$0")" && pwd)
json_file="$(realpath ${script_dir}/..)/_thief_secrets.json"

if [ "${THIEF_SUBSCRIPTION_ID}" == "" ]; then
    echo "THIEF_SUBSCRIPTION_ID variable needs to be set"
    exit 1
fi

if [ "${THIEF_KEYVAULT_NAME}" == "" ]; then
    THIEF_KEYVAULT_NAME="thief-kv"
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
    value=$(az keyvault secret show --subscription ${THIEF_SUBSCRIPTION_ID} --vault-name ${THIEF_KEYVAULT_NAME} --name ${kv_name} | jq -r ".value")
    add-json $json_name "$value"

}

# This script is intended for developer workstations.  When these tests runs in the cloud,
# they use a different mechanism to get secrets.
#
# Since this is a developer workstation, set the device ID and run IDs so the developer runs
# all communicate with each other instead of accidentally pairing with service apps that are
# running in the cloud.
add-json thiefKeyvaultName "${THIEF_KEYVAULT_NAME}"
add-json thiefSubscriptionId "${THIEF_SUBSCRIPTION_ID}"
add-json thiefDeviceId "${USER}_test_device"
add-json thiefServicePool "${USER}_desktop_pool"
add-json thiefRequestedServicePool "${USER}_desktop_pool"

add-secret thiefServiceConnectionString THIEF-SERVICE-CONNECTION-STRING
add-secret thiefDeviceProvisioningHost THIEF-DEVICE-PROVISIONING-HOST
add-secret thiefDeviceIdScope THIEF-DEVICE-ID-SCOPE
add-secret thiefDeviceGroupSymmetricKey THIEF-DEVICE-GROUP-SYMMETRIC-KEY
add-secret thiefEventhubConnectionString THIEF-EVENTHUB-CONNECTION-STRING
add-secret thiefEventhubConsumerGroup THIEF-EVENTHUB-CONSUMER-GROUP
add-secret thiefAppInsightsInstrumentationKey THIEF-APP-INSIGHTS-INSTRUMENTATION-KEY
add-secret thiefContainerRegistryHost THIEF-CONTAINER-REGISTRY-HOST
add-secret thiefContainerRegistryPassword THIEF-CONTAINER-REGISTRY-PASSWORD
add-secret thiefContainerRegistryUser THIEF-CONTAINER-REGISTRY-USER
add-secret thiefContainerRegistryShortname THIEF-CONTAINER-REGISTRY-SHORTNAME
add-secret thiefRunsResourceGroup THIEF-RUNS-RESOURCE-GROUP
add-secret thiefUserResourceId THIEF-USER-RESOURCE-ID
add-secret thiefResourceGroup THIEF-RESOURCE-GROUP
add-secret thiefIothubName THIEF-IOTHUB-NAME
add-secret thiefSharedKeyvaultName THIEF-SHARED-KEYVAULT-NAME
add-secret thiefSharedSubscriptionId THIEF-SHARED-SUBSCRIPTION-ID
add-secret thiefSharedResourceGroup THIEF-SHARED-RESOURCE-GROUP



echo Done fetching secrets
echo ${JSON} | jq -S '.' > "${json_file}"
echo Secrets written to ${json_file}

