# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import copy
import collections
import json
from thief_constants import Fields, Const
from client_fixtures import (
    create_message_from_dict,
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
    def wrapper_function(original_payload, cmd=None):
        operation_ticket = operation_ticket_factory()

        payload = copy.deepcopy(original_payload)
        if Fields.THIEF not in payload:
            payload[Fields.THIEF] = {}

        thief = payload[Fields.THIEF]

        thief[Fields.OPERATION_ID] = operation_ticket.id
        thief[Fields.SERVICE_INSTANCE_ID] = service_instance_id
        thief[Fields.RUN_ID] = run_id
        if cmd:
            thief[Fields.CMD] = cmd

        message = Message(json.dumps(payload))
        message.content_type = Const.JSON_CONTENT_TYPE
        message.content_encoding = Const.JSON_CONTENT_ENCODING

        return collections.namedtuple("WrappedMessage", "message operation_ticket payload")(
            message, operation_ticket, payload
        )

    return wrapper_function


@pytest.fixture(scope="class")
def reported_props_factory(run_id, service_instance_id, random_dict_factory):  # noqa: F811
    def factory_function(operation_ticket):
        return {
            Fields.THIEF: {
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
        }

    return factory_function


@pytest.fixture(scope="function")
def reported_props(reported_props_factory, operation_ticket):
    return reported_props_factory(operation_ticket)
