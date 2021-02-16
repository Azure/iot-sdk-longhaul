# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
set -e
script_dir=$(cd "$(dirname "$0")" && pwd)

function usage {
    echo "USAGE: ${0} [--platform platform] --langauge language_short_name --library library [--source library_source] --version library_version --pool service_pool [--device_id device_id] [--tag extra_tag] [--runid id] [--run_reason ] [--service_instance_id id]"
    echo "  ex: ${0} --language py37 --library device --source pypi --version 2.3.0 --pool pool_1"
    exit 1
}

source ${script_dir}/_parse_args "$@"

if [ "${LANGUAGE_SHORT_NAME}" == "" ]; then
    echo "ERROR: language_short_name is required"
    usage
fi
if [ "${LIBRARY}" == "" ]; then
    echo "ERROR: library is required"
    usage
fi
if [ ${LIBRARY_VERSION} == "" ]; then
    echo "ERROR: library_version is required"
    usage
fi
if [ ${SERVICE_POOL} == "" ]; then
    echo "ERROR: service_pool is required"
    usage
fi

case ${LIBRARY} in
    device)
        if [ "${DEVICE_ID}" == "" ]; then
            echo "ERROR: --device_id is required when library==device"
            usage
        fi
        if [ "${SERVICE_INSTANCE_ID}" != "" ]; then
            echo "ERROR: --service_instance_id is not valid when library==device"
            usage
        fi
        if [ "${RUN_ID}" == "" ]; then
            RUN_ID=$(uuidgen)
        fi
        CONTAINER_NAME=${DEVICE_ID}-device
        ;;
    service)
        if [ "${DEVICE_ID}" != "" ]; then
            echo "ERROR: --device_id must not used when library==service"
            usage
        fi
        if [ "${RUN_ID}" != "" ]; then
            echo "ERROR: --run_id is not valid when library==service"
            usage
        fi
        if [ "${RUN_REASON}" != "" ]; then
            echo "ERROR: --run_reason is not valid when library==service"
            usage
        fi
        if [ "${SERVICE_INSTANCE_ID}" == "" ]; then
            SERVICE_INSTANCE_ID=$(uuidgen)
        fi
        CONTAINER_NAME=${SERVICE_POOL}-service
        ;;
    *)
        echo "ERROR: library must be either 'device' or 'service'"
        usage
        ;;
esac

source ${script_dir}/_get_base_env ${PLATFORM} ${LANGUAGE_SHORT_NAME}

IMAGE=${LANGUAGE_SHORT_NAME}-${PLATFORM}-${LIBRARY}-${LIBRARY_SOURCE}-${LIBRARY_VERSION}
if [ "$EXTRA_TAG" != "" ]; then
    IMAGE="${IMAGE}:${EXTRA_TAG}"
fi

case ${LIBRARY} in
    device) 
        ENV=(\
            THIEF_DEVICE_ID=${DEVICE_ID} \
            THIEF_REQUESTED_SERVICE_POOL=${SERVICE_POOL} \
            THIEF_KEYVAULT_NAME=${THIEF_KEYVAULT_NAME} \
            THIEF_RUN_ID=${RUN_ID} \
            THIEF_RUN_REASON=\"${RUN_REASON}\" \
        )
        ;;
    service)
        ENV=(\
            THIEF_SERVICE_POOL=${SERVICE_POOL} \
            THIEF_KEYVAULT_NAME=${THIEF_KEYVAULT_NAME} \
            THIEF_SERVICE_INSTANCE_ID=${SERVICE_INSTANCE_ID} \
        )
        ;;
esac

echo "creating container using image ${IMAGE}"
echo "with name ${CONTAINER_NAME}"
echo env="${ENV[@]}"
az container create \
    --resource-group ${THIEF_RUNS_RESOURCE_GROUP} \
    --subscription ${THIEF_SUBSCRIPTION_ID} \
    --name ${CONTAINER_NAME} \
    --image ${THIEF_CONTAINER_REGISTRY_HOST}/${IMAGE} \
    --environment-variables "${ENV[@]}" \
    --registry-username ${THIEF_CONTAINER_REGISTRY_USER} \
    --registry-password ${THIEF_CONTAINER_REGISTRY_PASSWORD} \
    --restart-policy Never \
    --azure-file-volume-account-name ${THIEF_SHARED_LOG_STORAGE_ACCOUNT_NAME} \
    --azure-file-volume-account-key ${THIEF_SHARED_LOG_STORAGE_ACCOUNT_KEY} \
    --azure-file-volume-share-name ${THIEF_SHARED_LOG_STORAGE_SHARE_NAME} \
    --azure-file-volume-mount-path /mnt/logs/ \
    --assign-identity ${THIEF_USER_RESOURCE_ID} 

echo SUCCESS

