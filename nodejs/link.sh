# !/bin/bash
# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
set -e 
script_dir=$(cd "$(dirname "$0")" && pwd)

NODE_SDK_ROOT=$1
if [ ! -f ${NODE_SDK_ROOT}/tslint.json ]; then
  echo Usage: $0 [node sdk root]
  echo ex: $0 /home/repos/node
  exit 1
fi

cd ${script_dir}/device
npm link \
    ${NODE_SDK_ROOT}/common/core \
    ${NODE_SDK_ROOT}/device/core\
    ${NODE_SDK_ROOT}/device/transport/mqtt \
    ${NODE_SDK_ROOT}/provisioning/device \
    ${NODE_SDK_ROOT}/provisioning/transport/mqtt \
    ${NODE_SDK_ROOT}security/symmetric
