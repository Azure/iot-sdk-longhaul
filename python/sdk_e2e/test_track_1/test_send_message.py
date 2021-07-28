# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import asyncio
import pytest
import logging
from thief_constants import Flags, Fields, Commands

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def test_message(message_factory):
    return message_factory(
        {
            Fields.THIEF: {
                Fields.CMD: Commands.SEND_OPERATION_RESPONSE,
                Fields.FLAGS: [Flags.RESPOND_IMMEDIATELY],
            }
        }
    )


@pytest.mark.describe("Device Client send_message method")
class TestSendMessage(object):
    @pytest.mark.it("Can send a simple message")
    async def test_send_message(self, paired_client, test_message):
        client = paired_client.client

        await client.send_message(test_message.message)
        await test_message.running_op.event.wait()

    @pytest.mark.it("Connects the transport if necessary")
    async def test_connect_if_necessary(self, paired_client, test_message):
        client = paired_client.client

        await client.disconnect()
        assert not client.connected

        await client.send_message(test_message.message)
        assert client.connected

        await test_message.running_op.event.wait()

    @pytest.mark.it("Sends if connection drops before sending")
    async def test_sends_if_drop_before_sending(self, paired_client, test_message, dropper):
        client = paired_client.client

        assert client.connected

        dropper.drop_outgoing()
        send_task = asyncio.create_task(client.send_message(test_message.message))

        while client.connected:
            await asyncio.sleep(1)

        assert not send_task.done()

        dropper.restore_all()
        while not client.connected:
            await asyncio.sleep(1)

        await send_task
        await test_message.running_op.event.wait()

    @pytest.mark.it("Sends if connection rejects send")
    async def test_sends_if_reject_before_sending(self, paired_client, test_message, dropper):
        client = paired_client.client

        assert client.connected

        dropper.reject_outgoing()
        send_task = asyncio.create_task(client.send_message(test_message.message))

        while client.connected:
            await asyncio.sleep(1)

        assert not send_task.done()

        dropper.restore_all()
        while not client.connected:
            await asyncio.sleep(1)

        await send_task
        await test_message.running_op.event.wait()
