# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import pprint
import json
from thief_constants import Fields, Flags, Commands, Const

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def client_kwargs(pnp_model_id):
    return {"model_id": pnp_model_id}


@pytest.mark.pnp
@pytest.mark.describe("Pnp Telemetry")
class TestPnpTelemetry(object):
    @pytest.mark.it("Can send a telemetry message")
    async def test_send_pnp_telemetry(self, client, message_factory, pnp_model_id):
        telemetry = message_factory(
            {
                Fields.CMD: Commands.SEND_OPERATION_RESPONSE,
                Fields.FLAGS: [Flags.RETURN_EVENTHUB_MESSAGE_CONTENTS],
            },
        )
        await client.send_telemetry(telemetry.body)
        await telemetry.operation_ticket.event.wait()

        response = json.loads(telemetry.operation_ticket.result_message.data)
        logger.info(pprint.pformat(response))

        eventhub_message_contents = response[Fields.EVENTHUB_MESSAGE_CONTENTS]
        assert eventhub_message_contents[Fields.EVENTHUB_MESSAGE_BODY] == telemetry.body

        system_props = eventhub_message_contents[Fields.EVENTHUB_SYSTEM_PROPERTIES]
        assert system_props[Fields.EVENTHUB_SYSPROP_DT_DATASCHEMA] == pnp_model_id
        assert system_props[Fields.EVENTHUB_SYSPROP_CONTENT_TYPE] == Const.JSON_CONTENT_TYPE
        assert system_props[Fields.EVENTHUB_SYSPROP_CONTENT_ENCODING] == Const.JSON_CONTENT_ENCODING
