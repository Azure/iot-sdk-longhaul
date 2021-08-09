# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import time
from thief_constants import Flags, Fields, Commands
from track2 import topic_builder

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)


@pytest.fixture
def test_message(message_wrapper):
    return message_wrapper(
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
    def test_send_message(self, client, test_message, c2d_subscription):
        time.sleep(2)
        client.publish(
            topic_builder.build_telemetry_publish_topic(message=test_message.message),
            test_message.message.get_payload(),
            qos=1,
        )
        test_message.operation_ticket.event.wait()

    @pytest.mark.it("sends if disconnected after sending and manually reconnected")
    def test_sends_if_disconencted(self, client, test_message, connection_status, auth, keep_alive):
        client.disconnect()
        connection_status.wait_for_disconnected()

        client.publish(
            topic_builder.build_telemetry_publish_topic(message=test_message.message),
            test_message.message.get_payload(),
            qos=1,
        )

        assert not test_message.operation_ticket.event.is_set()

        # TODO: this test fails badly if we add this sleep here.  It's not just that it fails,
        # it's also that paho is in a bad state, can't reconnect, can't restart loop.
        # Need to figure out how to handle this?  Remove everyting from pending list and fail
        # publish?
        # time.sleep(1)

        client.reconnect()
        connection_status.wait_for_connected()

        test_message.operation_ticket.event.wait()

    @pytest.mark.it("Sends if connection drops before sending")
    def test_sends_if_drop_before_sending(self, client, test_message, dropper, connection_status):
        assert connection_status.connected

        dropper.drop_outgoing()
        client.publish(
            topic_builder.build_telemetry_publish_topic(message=test_message.message),
            test_message.message.get_payload(),
            qos=1,
        )

        logger.info("Waiting for disconnection")
        connection_status.wait_for_disconnected()
        logger.info("disconnected")

        assert not test_message.operation_ticket.event.is_set()

        dropper.restore_all()
        logger.info("Waiting for reconnection")
        connection_status.wait_for_connected()

        test_message.operation_ticket.event.wait()
