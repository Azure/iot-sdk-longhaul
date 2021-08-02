# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import json
from thief_constants import Commands, Fields

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def pnp_model_id():
    return "dtmi:com:example:TemperatureController;2"


@pytest.fixture(scope="class")
def client_kwargs(pnp_model_id):
    return {"model_id": pnp_model_id}


@pytest.mark.describe("Device Client PNP Connection")
class TestPnpConnect(object):
    @pytest.mark.it("Can connect and disconnect with model_id set")
    async def test_connect(self, connected_client, pnp_model_id):
        client = connected_client

        assert client._mqtt_pipeline.pipeline_configuration.model_id == pnp_model_id

        assert client
        await client.connect()
        assert client.connected

        await client.disconnect()
        assert not client.connected

        await client.connect()
        assert client.connected

    @pytest.mark.it("Shows up as a PNP device in the service client")
    async def test_model_id_in_service_client(self, paired_client, pnp_model_id, message_factory):
        client = paired_client.client

        assert client._mqtt_pipeline.pipeline_configuration.model_id == pnp_model_id
        assert client.connected

        msg = message_factory({}, cmd=Commands.GET_PNP_PROPERTIES)
        await client.send_message(msg.message)

        await msg.running_op.event.wait()

        assert (
            json.loads(msg.running_op.result_message.data)[Fields.THIEF][
                Fields.PNP_PROPERTIES_CONTENTS
            ]["$metadata"]["$model"]
            == pnp_model_id
        )
