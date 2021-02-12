# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
source /fetch-service-secrets.sh
python -u /service/service.py 2>&1 | tee /mnt/logs/svc-${THIEF_SERVICE_POOL}-${THIEF_SERVICE_INSTANCE_ID}.txt
