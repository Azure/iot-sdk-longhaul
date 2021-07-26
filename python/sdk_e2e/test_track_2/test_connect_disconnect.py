# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)


@pytest.mark.describe("Device Client")
class TestConnectDisconnect(object):
    @pytest.mark.it("Successfully pairs with thief service app")
    def test_pairing(self, paired_client, connection_status):
        assert paired_client.mqtt_client
        assert connection_status.connected
        assert paired_client.service_instance_id
        logger.info("paired")

    @pytest.mark.it("Can disconnect and reconnect")
    def test_connect_disconnect(self, connected_mqtt_client, connection_status):
        client = connected_mqtt_client

        assert client
        client.reconnect()
        connection_status.wait_for_connected()
        assert connection_status.connected

        client.disconnect()
        connection_status.wait_for_disconnected()
        assert not connection_status.connected

        client.reconnect()
        connection_status.wait_for_connected()
        assert connection_status.connected

    @pytest.mark.it("disconnects when network drops all outgoing packets")
    def test_disconnect_on_drop_outgoing(self, connected_mqtt_client, dropper, connection_status):
        client = connected_mqtt_client

        client.reconnect()
        connection_status.wait_for_connected()
        assert connection_status.connected
        dropper.drop_outgoing()

        connection_status.wait_for_disconnected()
        assert not connection_status.connected

    @pytest.mark.it("disconnects when network rejects all outgoing packets")
    def test_disconnect_on_reject_outgoing(self, connected_mqtt_client, dropper, connection_status):
        client = connected_mqtt_client

        client.reconnect()
        connection_status.wait_for_connected()
        assert connection_status.connected
        dropper.reject_outgoing()

        connection_status.wait_for_disconnected()
        assert not connection_status.connected
