# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import asyncio
import pytest
import logging
from azure.iot.device.exceptions import ConnectionFailedError

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.mark.describe("Device Client")
class TestConnectDisconnect(object):
    @pytest.mark.it("Successfully pairs with thief service app")
    async def test_pairing(self, client, service_instance_id):
        assert client
        assert client.connected
        assert service_instance_id
        logger.info("paired")

    @pytest.mark.it("Can disconnect and reconnect")
    async def test_connect_disconnect(self, connected_client):
        client = connected_client

        assert client
        await client.connect()
        assert client.connected

        await client.disconnect()
        assert not client.connected

        await client.connect()
        assert client.connected

    # NOTE: perhaps this is more suited to a different test class?
    @pytest.mark.dropped_connection
    @pytest.mark.it("Raises ConnectionFailedError if connect attempt fails due to network")
    @pytest.mark.parametrize("network_failure_type", [
        pytest.param("drop", id="Network drops outgoing packets"),
        pytest.param("reject", id="Network rejects outgoing packets")
    ])
    async def test_connect_on_drop_outgoing(self, dropper, client, network_failure_type):
        # NOTE: perhaps this should be using a different client fixture
        await client.connect()
        assert client.connected
        await client.disconnect()
        assert not client.connected
        
        # Set network to fail connect
        if network_failure_type == "drop":
            dropper.drop_outgoing()
        else:
            dropper.reject_outgoing()

        # Attempt to connect
        with pytest.raises(ConnectionFailedError) as e_info:
            await client.connect()


        # Clean up (client is a class fixture and must be reconnected)
        dropper.restore_all()
        client.connect()


@pytest.mark.dropped_connection
@pytest.mark.describe("Device Client with dropped connection")
class TestConnectDisconnectDroppedConnection(object):
    @pytest.fixture(scope="class")
    def client_kwargs(self):
        return {"keep_alive": 5}

    @pytest.mark.it("disconnects when network drops all outgoing packets")
    async def test_disconnect_on_drop_outgoing(self, connected_client, dropper):
        client = connected_client

        await client.connect()
        assert client.connected
        dropper.drop_outgoing()

        while client.connected:
            await asyncio.sleep(1)

    @pytest.mark.it("disconnects when network rejects all outgoing packets")
    async def test_disconnect_on_reject_outgoing(self, connected_client, dropper):
        client = connected_client

        await client.connect()
        assert client.connected
        dropper.reject_outgoing()

        while client.connected:
            await asyncio.sleep(1)
