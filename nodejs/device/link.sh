# !/bin/bash
# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
set -e 

NODE_ROOT=$1
echo if [ ! -f ${NODE_ROOT}/tslint.json ]
if [ ! -f ${NODE_ROOT}/tslint.json ]; then
  echo Usage: $0 [node_root]
  echo ex: $0 /home/repos/node
  exit 1
fi

npm link ${NODE_ROOT}/common/core ${NODE_ROOT}/device/core ${NODE_ROOT}/device/transport/mqtt ${NODE_ROOT}/provisioning/device ${NODE_ROOT}/provisioning/transport/mqtt ${NODE_ROOT}security/symmetric
