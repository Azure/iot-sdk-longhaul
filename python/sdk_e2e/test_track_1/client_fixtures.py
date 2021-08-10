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
async def c2d_waiter(event_loop, connected_client, operation_ticket_list, run_id):
    async def handle_c2d(msg):
        body = json.loads(msg.data.decode())
        logger.info("Received {}".format(body))

        if not body:
            logger.warning("No payload")
            return

        if body.get(Fields.RUN_ID) != run_id:
            logger.warning(
                "run_id does not match: expected={}, received={}".format(
                    run_id, body.get(Fields.RUN_ID)
                )
            )
            return

        cmd = body.get(Fields.CMD)
        if cmd not in [
            Commands.PAIR_RESPONSE,
            Commands.OPERATION_RESPONSE,
            Commands.METHOD_RESPONSE,
            Commands.C2D_RESPONSE,
        ]:
            logger.warning("unknown cmd: {}".format(cmd))
            return

        operation_ids = body.get(Fields.OPERATION_IDS, [])
        if not operation_ids:
            operation_ids = [
                body.get(Fields.OPERATION_ID),
            ]

        logger.info("Received {} message with {}".format(body[Fields.CMD], operation_ids))

        for operation_id in operation_ids:
            operation_ticket = operation_ticket_list.get(operation_id)
            if operation_ticket:
                logger.info("setting event for message {}".format(operation_id))
                operation_ticket.result_message = msg
                event_loop.call_soon_threadsafe(operation_ticket.complete)
            else:
                logger.warning("Received unknown operationId: {}:".format(operation_id))

    connected_client.on_message_received = handle_c2d


@pytest.fixture(scope="class")
async def paired_client(
    connected_client, operation_ticket_list, c2d_waiter, run_id, requested_service_pool
):
    start_time = time.time()
    while time.time() - start_time <= PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS:
        operation_ticket = operation_ticket_list.make_event_based_operation_ticket(
            event_module=asyncio
        )

        pairing_payload = {
            Fields.CMD: Commands.PAIR_WITH_SERVICE_APP,
            Fields.OPERATION_ID: operation_ticket.id,
            Fields.REQUESTED_SERVICE_POOL: requested_service_pool,
            Fields.RUN_ID: run_id,
        }

        msg = Message(json.dumps(pairing_payload))
        msg.content_type = Const.JSON_CONTENT_TYPE
        msg.content_encoding = Const.JSON_CONTENT_ENCODING

        await connected_client.send_message(msg)

        logger.info("Waiting for pairing response")
        try:
            await asyncio.wait_for(
                operation_ticket.event.wait(), PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS
            )
        except asyncio.TimeoutError:
            pass
        else:
            logger.info("pairing response received")
            body = json.loads(operation_ticket.result_message.data.decode())
            return collections.namedtuple("ConnectedClient", "client service_instance_id")(
                connected_client, body[Fields.SERVICE_INSTANCE_ID]
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
