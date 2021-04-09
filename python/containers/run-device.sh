# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
source /fetch-device-secrets.sh
export THIEF_RUN_ID=$(uuidgen)
python -u /device/device.py 2>&1 | tee /mnt/logs/dev-${THIEF_DEVICE_ID}-${THIEF_RUN_ID}.txt
