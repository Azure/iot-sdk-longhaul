# Copyright (c) Microsoft. All rights reserved.  # Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

# this is a temporary script that will hopefully disappear

set -e
script_dir=$(cd "$(dirname "$0")" && pwd)

LANGUAGE=py38
DEVICE_VERSION=2.5.0
SERVICE_VERSION=2.2.3
TAG=feb11b
POOL=${TAG}
RUN_REASON=""

${script_dir}/build-image.sh --language ${LANGUAGE} --library service --version ${SERVICE_VERSION} --tag ${TAG}
${script_dir}/build-image.sh --language ${LANGUAGE} --library device --version ${DEVICE_VERSION} --tag ${TAG}

${script_dir}/run-container.sh --language ${LANGUAGE} --library service --version ${SERVICE_VERSION} --tag ${TAG} --pool ${POOL}

DEVICE_ARGS=(\
    --language ${LANGUAGE} \
    --library device \
    --version ${DEVICE_VERSION} \
    --tag ${TAG} \
    --pool ${POOL} \
    --run_reason "${RUN_REASON}" \
    )
${script_dir}/run-container.sh --device_id ${POOL}-1 "${DEVICE_ARGS[@]}"
${script_dir}/run-container.sh --device_id ${POOL}-2 "${DEVICE_ARGS[@]}"
${script_dir}/run-container.sh --device_id ${POOL}-3 "${DEVICE_ARGS[@]}"

