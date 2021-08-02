# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import asyncio
import pytest
import logging
from thief_constants import Fields, Commands

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


def validate_patch_reported(twin, patch):
    twin_prop = (
        twin.get(Fields.REPORTED, {})
        .get(Fields.THIEF, {})
        .get(Fields.TEST_CONTENT, {})
        .get(Fields.REPORTED_PROPERTY_TEST, {})
        .get(Fields.E2E_PROPERTY, {})
    )
    patch_prop = (
        patch.get(Fields.THIEF, {})
        .get(Fields.TEST_CONTENT, {})
        .get(Fields.REPORTED_PROPERTY_TEST, {})
        .get(Fields.E2E_PROPERTY, {})
    )
    assert twin_prop == patch_prop


# TODO: rename running_op to op_ticket?
# TODO: tests with drop_incoming and reject_incoming


async def clean_reported_properties(client):
    await client.patch_twin_reported_properties(
        {
            Fields.THIEF: {
                Fields.TEST_CONTENT: {Fields.REPORTED_PROPERTY_TEST: {Fields.E2E_PROPERTY: None}}
            }
        }
    )


@pytest.mark.describe("Device Client Reported Properties")
class TestReportedProperties(object):
    @pytest.mark.it("Can set a simple reported property")
    async def test_simple_patch(self, paired_client, running_op, reported_props):
        client = paired_client.client

        await client.patch_twin_reported_properties(reported_props)
        await running_op.event.wait()

        twin = await client.get_twin()
        validate_patch_reported(twin, reported_props)

        await clean_reported_properties(client)

    @pytest.mark.it("Connects the transport if necessary")
    async def test_connect_if_necessary(self, paired_client, running_op, reported_props):
        client = paired_client.client

        await client.disconnect()

        assert not client.connected
        await client.patch_twin_reported_properties(reported_props)
        assert client.connected
        await running_op.event.wait()

        twin = await client.get_twin()
        validate_patch_reported(twin, reported_props)

        await clean_reported_properties(client)

    @pytest.mark.it("Sends if connection drops before sending")
    async def test_sends_if_drop_before_sending(
        self, paired_client, running_op, reported_props, dropper
    ):
        client = paired_client.client

        assert client.connected
        dropper.drop_outgoing()

        send_task = asyncio.create_task(client.patch_twin_reported_properties(reported_props))
        while client.connected:
            await asyncio.sleep(1)

        assert not send_task.done()

        dropper.restore_all()
        while not client.connected:
            await asyncio.sleep(1)

        await send_task
        await running_op.event.wait()

        await clean_reported_properties(client)

    @pytest.mark.it("Sends if connection rejects send")
    async def test_sends_if_reject_before_sending(
        self, paired_client, running_op, reported_props, dropper
    ):
        client = paired_client.client

        assert client.connected
        dropper.reject_outgoing()

        send_task = asyncio.create_task(client.patch_twin_reported_properties(reported_props))
        while client.connected:
            await asyncio.sleep(1)

        assert not send_task.done()

        dropper.restore_all()
        while not client.connected:
            await asyncio.sleep(1)

        await send_task
        await running_op.event.wait()

        await clean_reported_properties(client)


@pytest.mark.describe("Device Client Desired Properties")
class TestDesiredProperties(object):
    @pytest.mark.it("Receives a patch for a simple desired property")
    async def test_simple_patch(self, paired_client, message_factory, random_content, event_loop):
        client = paired_client.client
        received_patch = None
        received = asyncio.Event()

        async def handle_on_patch_received(patch):
            nonlocal received_patch, received
            print("received {}".format(patch))
            received_patch = patch
            event_loop.call_soon_threadsafe(received.set)

        client.on_twin_desired_properties_patch_received = handle_on_patch_received

        await client.send_message(
            message_factory(
                {
                    Fields.THIEF: {
                        Fields.CMD: Commands.SET_DESIRED_PROPS,
                        Fields.DESIRED_PROPERTIES: {
                            Fields.THIEF: {Fields.RANDOM_CONTENT: random_content}
                        },
                    }
                }
            ).message
        )

        await asyncio.wait_for(received.wait(), 10)
        logger.info("got it")

        assert received_patch.get(Fields.THIEF, {}).get(Fields.RANDOM_CONTENT, {}) == random_content

        twin = await client.get_twin()
        assert (
            twin.get(Fields.DESIRED, {}).get(Fields.THIEF, {}).get(Fields.RANDOM_CONTENT, {})
            == random_content
        )


# TODO: etag tests, version tests