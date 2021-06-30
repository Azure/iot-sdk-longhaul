# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
script_dir=$(cd "$(dirname "$0")" && pwd)
python -u ${script_dir}/service/service.py 2>&1 | tee ~/temp/service.txt
