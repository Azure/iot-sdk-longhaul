# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import asyncio
import pytest
import logging
from thief_constants import Fields

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


def validate_patch_reported(twin, patch):
    twin_prop = (
        twin.get(Fields.REPORTED, {})
        .get(Fields.TEST_CONTENT, {})
        .get(Fields.REPORTED_PROPERTY_TEST, {})
        .get(Fields.E2E_PROPERTY, {})
    )
    patch_prop = (
        patch.get(Fields.TEST_CONTENT, {})
        .get(Fields.REPORTED_PROPERTY_TEST, {})
        .get(Fields.E2E_PROPERTY, {})
    )
    assert twin_prop == patch_prop


# TODO: tests with drop_incoming and reject_incoming


async def clean_reported_properties(client):
    await client.patch_twin_reported_properties(
        {Fields.TEST_CONTENT: {Fields.REPORTED_PROPERTY_TEST: {Fields.E2E_PROPERTY: None}}}
    )


@pytest.mark.describe("Device Client Reported Properties")
class TestReportedProperties(object):
    @pytest.mark.it("Can set a simple reported property")
    async def test_simple_patch(self, client, operation_ticket, reported_props):

        await client.patch_twin_reported_properties(reported_props)
        await operation_ticket.event.wait()

        twin = await client.get_twin()
        validate_patch_reported(twin, reported_props)

        await clean_reported_properties(client)

    @pytest.mark.it("Connects the transport if necessary")
    async def test_connect_if_necessary(self, client, operation_ticket, reported_props):

        await client.disconnect()

        assert not client.connected
        await client.patch_twin_reported_properties(reported_props)
        assert client.connected
        await operation_ticket.event.wait()

        twin = await client.get_twin()
        validate_patch_reported(twin, reported_props)

        await clean_reported_properties(client)


@pytest.mark.dropped_connection
@pytest.mark.describe("Device Client Reported Properties with dropped connection")
class TestReportedPropertiesDroppedConnection(object):
    @pytest.fixture(scope="class")
    def client_kwargs(self):
        return {"keep_alive": 5}

    @pytest.mark.it("Sends if connection drops before sending")
    async def test_sends_if_drop_before_sending(
        self, client, operation_ticket, reported_props, dropper
    ):

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
        await operation_ticket.event.wait()

        await clean_reported_properties(client)

    @pytest.mark.it("Sends if connection rejects send")
    async def test_sends_if_reject_before_sending(
        self, client, operation_ticket, reported_props, dropper
    ):

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
        await operation_ticket.event.wait()

        await clean_reported_properties(client)


@pytest.mark.describe("Device Client Desired Properties")
class TestDesiredProperties(object):
    @pytest.mark.it("Receives a patch for a simple desired property")
    async def test_simple_patch(self, client, random_dict, event_loop, service_app):

        received_patch = None
        received = asyncio.Event()

        async def handle_on_patch_received(patch):
            nonlocal received_patch, received
            print("received {}".format(patch))
            received_patch = patch
            event_loop.call_soon_threadsafe(received.set)

        client.on_twin_desired_properties_patch_received = handle_on_patch_received

        await service_app.set_desired_props({Fields.RANDOM_CONTENT: random_dict})

        await asyncio.wait_for(received.wait(), 10)
        logger.info("got it")

        assert received_patch.get(Fields.RANDOM_CONTENT, {}) == random_dict

        twin = await client.get_twin()
        assert twin.get(Fields.DESIRED, {}).get(Fields.RANDOM_CONTENT, {}) == random_dict


# TODO: etag tests, version tests
