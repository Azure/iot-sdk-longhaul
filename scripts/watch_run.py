# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import json
import time
import os
from pygments import highlight
from pygments.lexers import JsonLexer
from pygments.formatters import TerminalFormatter
import thief_secrets
from thief_constants import Fields
from azure.iot.hub import IoTHubRegistryManager

registry_manager = IoTHubRegistryManager.from_connection_string(
    thief_secrets.IOTHUB_CONNECTION_STRING
)

while True:
    os.system("cls" if os.name == "nt" else "clear")
    twin = registry_manager.get_twin(thief_secrets.DEVICE_ID)
    json_object = {
        Fields.SESSION_METRICS: twin.properties.reported.get(Fields.THIEF, {}).get(
            Fields.SESSION_METRICS, None
        ),
        Fields.TEST_METRICS: twin.properties.reported.get(Fields.THIEF, {}).get(
            Fields.TEST_METRICS, None
        ),
        Fields.SYSTEM_HEALTH_METRICS: twin.properties.reported.get(Fields.THIEF, {}).get(
            Fields.SYSTEM_HEALTH_METRICS, None
        ),
    }
    json_str = json.dumps(json_object, indent=4, sort_keys=True)
    print(highlight(json_str, JsonLexer(), TerminalFormatter()))
    time.sleep(10)
