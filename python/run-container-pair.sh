set -e

DEVICE_IMAGE=py36-linux-device-pypi-2.1.4
SERVICE_IMAGE=py38-linux-service-pypi-2.2.1
DATETIME_NOW=$(date "+%Y-%m-%d-%H-%M-%S")

DEVICE_ID=${USER}-${DATETIME_NOW}
SERVICE_CONTAINER_NAME=${DEVICE_ID}-service
DEVICE_CONTAINER_NAME=${DEVICE_ID}-device

echo "creating service client container"
az container create \
    --resource-group ${THIEF_RUNS_RESOURCE_GROUP} \
    --name ${SERVICE_CONTAINER_NAME} \
    --image ${THIEF_CONTAINER_REGISTRY_HOST}/${SERVICE_IMAGE} \
    --environment-variables "THIEF_DEVICE_ID=${DEVICE_ID}" \
    --registry-username ${THIEF_CONTAINER_REGISTRY_USER} \
    --registry-password ${THIEF_CONTAINER_REGISTRY_PASSWORD} \
    --restart-policy Never \
    --assign-identity ${THIEF_USER_RESOURCE_ID} 

echo "creating device client container"
az container create \
    --resource-group ${THIEF_RUNS_RESOURCE_GROUP} \
    --name ${DEVICE_CONTAINER_NAME} \
    --image ${THIEF_CONTAINER_REGISTRY_HOST}/${DEVICE_IMAGE} \
    --environment-variables "THIEF_DEVICE_ID=${DEVICE_ID}" \
    --registry-username ${THIEF_CONTAINER_REGISTRY_USER} \
    --registry-password ${THIEF_CONTAINER_REGISTRY_PASSWORD} \
    --restart-policy Never \
    --assign-identity ${THIEF_USER_RESOURCE_ID} 

echo SUCCESS
echo
echo To view device log:
echo az container logs --resource-group ${THIEF_RUNS_RESOURCE_GROUP} --name ${DEVICE_CONTAINER_NAME}
echo
echo az container logs --resource-group ${THIEF_RUNS_RESOURCE_GROUP} --name ${SERVICE_CONTAINER_NAME}
echo
echo To remove containers:
echo az container delete --resource-group ${THIEF_RUNS_RESOURCE_GROUP} --name ${DEVICE_CONTAINER_NAME} --yes  \&\& az container delete --resource-group ${THIEF_RUNS_RESOURCE_GROUP} --name ${SERVICE_CONTAINER_NAME} --yes 

