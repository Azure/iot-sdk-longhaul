# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import collections
import json
import time
import asyncio
from azure.iot.device import Message
from azure.iot.device.iothub.aio import IoTHubDeviceClient
from thief_constants import Fields, Commands, Const
import thief_secrets

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
    msg = Message(json.dumps(payload))
    msg.content_type = Const.JSON_CONTENT_TYPE
    msg.content_encoding = Const.JSON_CONTENT_ENCODING

    return msg


@pytest.fixture(scope="class")
def client_kwargs():
    return {}


@pytest.fixture(scope="class")
def brand_new_client(client_kwargs):
    return IoTHubDeviceClient.create_from_connection_string(
        thief_secrets.DEVICE_CONNECTION_STRING, **client_kwargs
    )


@pytest.fixture(scope="class")
async def connected_client(brand_new_client):
    await brand_new_client.connect()
    yield brand_new_client
    await brand_new_client.shutdown()


@pytest.fixture(scope="class")
async def c2d_waiter(event_loop, connected_client, running_operation_list, run_id):
    async def handle_c2d(msg):
        thief = json.loads(msg.data.decode()).get(Fields.THIEF, {})
        logger.info("Received {}".format(thief))

        if not thief:
            logger.warning("No thief object in payload")
            return

        if thief.get(Fields.RUN_ID) != run_id:
            logger.warning(
                "run_id does not match: expected={}, received={}".format(
                    run_id, thief.get(Fields.RUN_ID)
                )
            )
            return

        cmd = thief.get(Fields.CMD)
        if cmd not in [
            Commands.PAIR_RESPONSE,
            Commands.OPERATION_RESPONSE,
            Commands.METHOD_RESPONSE,
            Commands.C2D_RESPONSE,
        ]:
            logger.warning("unknown cmd: {}".format(cmd))
            return

        operation_ids = thief.get(Fields.OPERATION_IDS, [])
        if not operation_ids:
            operation_ids = [
                thief.get(Fields.OPERATION_ID),
            ]

        logger.info("Received {} message with {}".format(thief[Fields.CMD], operation_ids))

        for operation_id in operation_ids:
            running_op = running_operation_list.get(operation_id)
            if running_op:
                logger.info("setting event for message {}".format(operation_id))
                running_op.result_message = msg
                event_loop.call_soon_threadsafe(running_op.complete)
            else:
                logger.warning("Received unknown operationId: {}:".format(operation_id))

    connected_client.on_message_received = handle_c2d


@pytest.fixture(scope="class")
async def paired_client(
    connected_client, running_operation_list, c2d_waiter, run_id, requested_service_pool
):
    start_time = time.time()
    while time.time() - start_time <= PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS:
        running_op = running_operation_list.make_event_based_operation(event_module=asyncio)

        pairing_payload = {
            Fields.THIEF: {
                Fields.CMD: Commands.PAIR_WITH_SERVICE_APP,
                Fields.OPERATION_ID: running_op.id,
                Fields.REQUESTED_SERVICE_POOL: requested_service_pool,
            }
        }
        msg = create_message_from_dict(pairing_payload, None, run_id)
        await connected_client.send_message(msg)

        logger.info("Waiting for pairing response")
        try:
            await asyncio.wait_for(
                running_op.event.wait(), PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS
            )
        except asyncio.TimeoutError:
            pass
        else:
            logger.info("pairing response received")
            msg = json.loads(running_op.result_message.data.decode())
            return collections.namedtuple("ConnectedClient", "client service_instance_id")(
                connected_client, msg[Fields.THIEF][Fields.SERVICE_INSTANCE_ID]
            )

    raise Exception("Service app did not respond in time")


@pytest.fixture(scope="function")
async def client(paired_client):
    yield paired_client.client

    # clean up all old handlers from this test.
    # Do not clean up on_message_received.  That will break c2d_waiter and the pairing process
    if paired_client.client.on_twin_desired_properties_patch_received:
        paired_client.client.on_twin_desired_properties_patch_received = None
    if paired_client.client.on_method_request_received:
        paired_client.client.on_method_request_received = None

    try:
        if paired_client.client.on_writable_property_update_request_received:
            paired_client.client.on_writable_property_update_request_received = None
        if paired_client.client.on_command_request_received:
            paired_client.client.on_command_request_received = None
    except AttributeError:
        # PNP properties aren't in this build yet.
        pass


@pytest.fixture(scope="class")
def service_instance_id(paired_client):
    return paired_client.service_instance_id
