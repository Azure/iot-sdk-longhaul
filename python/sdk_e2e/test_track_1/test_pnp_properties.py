# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import json
import asyncio
import pprint
from thief_constants import Commands, Fields
from azure.iot.device.iothub import ClientPropertyCollection

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="class")
def client_kwargs(pnp_model_id):
    return {"model_id": pnp_model_id}


@pytest.mark.describe("Device Client PNP properties")
class TestPnpSetProperties(object):
    @pytest.mark.it(
        "Can set a root reported property value and retrieve it via the service get_digital_twin function"
    )
    async def test_set_reported_property(
        self, paired_client, message_factory, random_key, random_content
    ):
        client = paired_client.client
        assert client.connected

        patch = ClientPropertyCollection()
        patch.set_property(random_key, random_content)

        logger.info("Setting {} to {}".format(random_key, random_content))
        await client.update_client_properties(patch)

        while True:
            msg = message_factory({}, cmd=Commands.GET_DIGITAL_TWIN)
            await client.send_message(msg.message)

            await msg.running_op.event.wait()

            if (
                json.loads(msg.running_op.result_message.data)
                .get(Fields.THIEF, {})
                .get(Fields.DIGITAL_TWIN_CONTENTS, {})
                .get(random_key, None)
                == random_content
            ):
                return

            pprint.pprint(json.loads(msg.running_op.result_message.data))

            await asyncio.sleep(5)

    @pytest.mark.it("Can retrieve a root reported property via the get_client_properties function")
    async def test_get_reported_property(self, paired_client, random_key, random_content):
        client = paired_client.client
        assert client.connected

        patch = ClientPropertyCollection()
        patch.set_property(random_key, random_content)

        logger.info("Setting {} to {}".format(random_key, random_content))
        await client.update_client_properties(patch)

        properties = await client.get_client_properties()

        assert properties.reported_from_device.get_property(random_key) == random_content

    @pytest.mark.it("Can retrieve a root desired property via the get_client_properties function")
    async def test_receive_desired_property_patch(
        self, event_loop, paired_client, random_key, random_content, message_factory
    ):
        client = paired_client.client
        received_patch = None
        received = asyncio.Event()

        async def handle_on_patch_received(patch):
            nonlocal received_patch, received
            print("received {}".format(patch))
            received_patch = patch
            event_loop.call_soon_threadsafe(received.set)

        client.on_writable_property_update_request_received = handle_on_patch_received
        await asyncio.sleep(1)

        logger.info("Setting {} to {}".format(random_key, random_content))
        await client.send_message(
            message_factory(
                {
                    Fields.THIEF: {
                        Fields.CMD: Commands.UPDATE_DIGITAL_TWIN,
                        Fields.DIGITAL_TWIN_UPDATE_PATCH: [
                            {"op": "add", "path": "/" + random_key, "value": random_content}
                        ],
                    }
                }
            ).message
        )

        await asyncio.wait_for(received.wait(), 10)
        logger.info("got it")

        assert received_patch.get_property(random_key) == random_content

        properties = await client.get_client_properties()
        assert properties.writable_properties_requests.get_property(random_key) == random_content


# TODO: all tests on root properties also need to apply to component properties
# TODO: test for receiving desired and returning reported (with writable_property_response) values -- root and component
# TODO: test to verify __t: c gets set on sending and received when receiving
# TODO: tests for both simple and complex property values.  Not sure exactly what we can test here, but we should do _something_
# TODO: etag tests, version tests
