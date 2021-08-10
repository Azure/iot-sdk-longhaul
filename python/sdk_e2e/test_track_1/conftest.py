# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import copy
import collections
import json
from thief_constants import Fields, Const, Commands, Flags
from client_fixtures import (
    client_kwargs,
    brand_new_client,
    connected_client,
    c2d_waiter,
    paired_client,
    client,
    service_instance_id,
)
from service_app_fixtures import service_app, pnp_service_app
from azure.iot.device.iothub import Message

logging.basicConfig(level=logging.INFO)
logging.getLogger("paho").setLevel(level=logging.DEBUG)
logging.getLogger("azure.iot").setLevel(level=logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)


@pytest.fixture(scope="class")
def message_factory(run_id, service_instance_id, operation_ticket_factory):  # noqa: F811
    def wrapper_function(original_body, cmd=None):
        operation_ticket = operation_ticket_factory()

        body = copy.deepcopy(original_body)

        body[Fields.OPERATION_ID] = operation_ticket.id
        body[Fields.SERVICE_INSTANCE_ID] = service_instance_id
        body[Fields.RUN_ID] = run_id
        if cmd:
            body[Fields.CMD] = cmd

        message = Message(json.dumps(body))
        message.content_type = Const.JSON_CONTENT_TYPE
        message.content_encoding = Const.JSON_CONTENT_ENCODING

        return collections.namedtuple("WrappedMessage", "message operation_ticket body")(
            message, operation_ticket, body
        )

    return wrapper_function


@pytest.fixture
def test_message(message_factory):
    return message_factory(
        {Fields.CMD: Commands.SEND_OPERATION_RESPONSE, Fields.FLAGS: [Flags.RESPOND_IMMEDIATELY]}
    )


@pytest.fixture(scope="class")
def reported_props_factory(run_id, service_instance_id, random_dict_factory):  # noqa: F811
    def factory_function(operation_ticket):
        return {
            Fields.RUN_ID: run_id,
            Fields.SERVICE_INSTANCE_ID: service_instance_id,
            Fields.TEST_CONTENT: {
                Fields.REPORTED_PROPERTY_TEST: {
                    Fields.E2E_PROPERTY: {
                        Fields.ADD_OPERATION_ID: operation_ticket.id,
                        Fields.RANDOM_CONTENT: random_dict_factory(),
                    }
                }
            },
        }

    return factory_function


@pytest.fixture(scope="function")
def reported_props(reported_props_factory, operation_ticket):
    return reported_props_factory(operation_ticket)
