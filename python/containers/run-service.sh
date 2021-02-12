# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
source /fetch-service-secrets.sh
python -m pdb -c continue /service/service.py
echo "Python app is complete.  Exiting in 60 seconds"
sleep 60
