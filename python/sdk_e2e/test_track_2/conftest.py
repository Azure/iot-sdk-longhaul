# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import json
import logging
import os
import time
import collections
import threading
from thief_constants import Fields, Commands, Const
from track2 import (
    SymmetricKeyAuth,
    ConnectionStatus,
    WaitableDict,
    IncomingMessageList,
    topic_builder,
    Message,
)
from paho.mqtt import client as mqtt
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logging.getLogger("paho").setLevel(level=logging.DEBUG)
logging.getLogger("azure.iot").setLevel(level=logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS = 180
PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS = 10


def create_message_from_dict(payload, service_instance_id, run_id):
    """
    helper function to create a message from a dict object
    """

    # Note: we're changing the dictionary that the user passed in.
    # This isn't the best idea, but it works and it saves us from deep copies
    if service_instance_id:
        payload[Fields.THIEF][Fields.SERVICE_INSTANCE_ID] = service_instance_id
    payload[Fields.THIEF][Fields.RUN_ID] = run_id

    # This function only creates the message.  The caller needs to queue it up for sending.
    msg = Message(payload)
    msg.content_type = Const.JSON_CONTENT_TYPE
    msg.content_encoding = Const.JSON_CONTENT_ENCODING

    return msg


@pytest.fixture(scope="module")
def auth():
    return SymmetricKeyAuth.create_from_connection_string(
        os.environ["IOTHUB_DEVICE_CONNECTION_STRING"]
    )


@pytest.fixture(scope="module")
def mqtt_client(auth):
    mqtt_client = mqtt.Client(auth.client_id, clean_session=False)
    mqtt_client.enable_logger()
    mqtt_client.username_pw_set(auth.username, auth.password)
    mqtt_client.tls_set_context(auth.create_tls_context())
    topic_builder.set_default_identity(auth.device_id)
    return mqtt_client


@pytest.fixture(scope="module")
def incoming_subacks(mqtt_client):
    incoming_subacks = WaitableDict()

    def handle_on_subscribe(mqtt_client, userdata, mid, granted_qos, properties=None):
        nonlocal incoming_subacks
        logger.info("Received SUBACK for mid {}".format(mid))
        incoming_subacks.add_item(mid, granted_qos)

    mqtt_client.on_subscribe = handle_on_subscribe
    return incoming_subacks


@pytest.fixture(scope="module")
def incoming_pubacks(mqtt_client):
    incoming_pubacks = WaitableDict()

    def handle_on_publish(mqtt_client, userdata, mid):
        nonlocal incoming_pubacks
        logger.info("Received PUBACK for mid {}".format(mid))
        incoming_pubacks.add_item(mid, mid)

    mqtt_client.on_publish = handle_on_publish
    return incoming_pubacks


@pytest.fixture(scope="module")
def incoming_message_list(mqtt_client):
    incoming_message_list = IncomingMessageList()

    def handle_on_message(mqtt_client, userdata, message):
        nonlocal incoming_message_list
        print("received message on {}".format(message.topic))
        incoming_message_list.add_item(message)

    mqtt_client.on_message = handle_on_message
    return incoming_message_list


@pytest.fixture(scope="module")
def connection_status(mqtt_client):
    connection_status = ConnectionStatus()

    def handle_on_connect(mqtt_client, userdata, flags, rc):
        logger.info("handle_on_connect called with rc={} ({})".format(rc, mqtt.connack_string(rc)))

        if rc == mqtt.MQTT_ERR_SUCCESS:
            connection_status.connected = True
        else:
            connection_status.connected = False

    def handle_on_disconnect(mqtt_client, usersdata, rc):
        logger.info("handle_on_disconnect called with rc={} ({})".format(rc, mqtt.error_string(rc)))
        connection_status.connected = False

    mqtt_client.on_connect = handle_on_connect
    mqtt_client.on_disconnect = handle_on_disconnect

    return connection_status


@pytest.fixture(scope="module")
def executor_shutdown_event():
    return threading.Event()


@pytest.fixture(scope="module")
def executor():
    executor = ThreadPoolExecutor()
    yield executor
    executor.shutdown()


@pytest.fixture(scope="module")
def connected_mqtt_client(mqtt_client, auth, connection_status, keep_alive):
    mqtt_client.loop_start()
    mqtt_client.connect(auth.hostname, auth.port, keepalive=keep_alive)
    connection_status.wait_for_connected()
    yield mqtt_client
    mqtt_client.disconnect()
    mqtt_client.loop_stop()


@pytest.fixture(scope="module")
def c2d_subscription(
    connected_mqtt_client,
    incoming_subacks,
    incoming_message_list,
    op_ticket_list,
    executor,
    executor_shutdown_event,
    run_id,
):
    rc, mid = connected_mqtt_client.subscribe(topic_builder.build_c2d_subscribe_topic(), 1)
    assert rc == mqtt.MQTT_ERR_SUCCESS
    # TODO: rename get_next_item to wait_something.  rename WaitableDict
    suback = incoming_subacks.get_next_item(mid, timeout=10)
    logger.info("Suback: {}".format(suback))
    assert suback

    def c2d_thread():
        while not executor_shutdown_event.is_set():
            msg = incoming_message_list.pop_next_c2d(timeout=1)
            logger.info("waiting - found = {}".format(msg))
            if msg:
                thief = json.loads(msg.payload.decode()).get(Fields.THIEF, {})
                logger.info("Received {}".format(thief))

                cmd = thief.get(Fields.CMD)
                operation_ids = thief.get(Fields.OPERATION_IDS, [])
                if not operation_ids:
                    operation_ids = [
                        thief.get(Fields.OPERATION_ID),
                    ]

                if not thief:
                    logger.warning("No thief object in payload")
                elif thief.get(Fields.RUN_ID) != run_id:
                    logger.warning(
                        "run_id does not match: expected={}, received={}".format(
                            run_id, thief.get(Fields.RUN_ID)
                        )
                    )
                elif cmd not in [
                    Commands.PAIR_RESPONSE,
                    Commands.OPERATION_RESPONSE,
                    Commands.METHOD_RESPONSE,
                    Commands.C2D_RESPONSE,
                ]:
                    logger.warning("unknown cmd: {}".format(cmd))
                else:
                    logger.info(
                        "Received {} message with {}".format(thief[Fields.CMD], operation_ids)
                    )

                    for operation_id in operation_ids:
                        op_ticket = op_ticket_list.get(operation_id)
                        if op_ticket:
                            logger.info("setting event for message {}".format(operation_id))
                            op_ticket.result_message = msg
                            op_ticket.complete()
                        else:
                            logger.warning("Received unknown operationId: {}:".format(operation_id))

    future = executor.submit(c2d_thread)
    logger.info("yielding c2d")
    yield
    executor_shutdown_event.set()
    future.result()


@pytest.fixture(scope="module")
def paired_client(
    connected_mqtt_client, op_ticket_list, c2d_subscription, run_id, requested_service_pool
):
    logger.info("Starting pairing")
    start_time = time.time()
    while time.time() - start_time <= PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS:
        op_ticket = op_ticket_list.make_event_based_operation()

        pairing_payload = {
            Fields.THIEF: {
                Fields.CMD: Commands.PAIR_WITH_SERVICE_APP,
                Fields.OPERATION_ID: op_ticket.id,
                Fields.REQUESTED_SERVICE_POOL: requested_service_pool,
            }
        }
        msg = create_message_from_dict(pairing_payload, None, run_id)
        logger.info(
            "Publish to : {}".format(topic_builder.build_telemetry_publish_topic(message=msg))
        )
        logger.info("Payload: {}".format(msg.get_payload()))
        connected_mqtt_client.publish(
            topic_builder.build_telemetry_publish_topic(message=msg), msg.get_payload()
        )

        logger.info("Waiting for pairing response")
        response = op_ticket.event.wait(timeout=PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS)
        if response:
            logger.info("pairing response received")
            msg = json.loads(op_ticket.result_message.payload.decode())
            return collections.namedtuple("ConnectedClient", "mqtt_client service_instance_id")(
                connected_mqtt_client, msg[Fields.THIEF][Fields.SERVICE_INSTANCE_ID]
            )

    assert False


@pytest.fixture(scope="function")
def client(paired_client, dropper, connection_status, auth, keep_alive):
    dropper.restore_all()
    if not connection_status.connected:
        paired_client.mqtt_client.reconnect()
    connection_status.wait_for_connected()
    return paired_client.mqtt_client


@pytest.fixture(scope="module")
def message_wrapper(op_ticket_list, run_id, paired_client, c2d_subscription):
    def wrapper_function(payload, cmd=None):
        op_ticket = op_ticket_list.make_event_based_operation()

        if Fields.THIEF not in payload:
            payload[Fields.THIEF] = {}
        payload[Fields.THIEF][Fields.OPERATION_ID] = op_ticket.id

        if cmd:
            payload[Fields.THIEF][Fields.CMD] = cmd

        message = create_message_from_dict(payload, paired_client.service_instance_id, run_id)

        return collections.namedtuple("WrappedMessage", "message op_ticket")(message, op_ticket)

    return wrapper_function
