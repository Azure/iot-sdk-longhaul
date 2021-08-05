# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import collections
from thief_constants import Fields
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

logging.basicConfig(level=logging.INFO)
logging.getLogger("paho").setLevel(level=logging.DEBUG)
logging.getLogger("azure.iot").setLevel(level=logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)


@pytest.fixture(scope="class")
def message_factory(run_id, service_instance_id, op_factory):  # noqa: F811
    def wrapper_function(payload, cmd=None):
        running_op = op_factory()

        if Fields.THIEF not in payload:
            payload[Fields.THIEF] = {}
        payload[Fields.THIEF][Fields.OPERATION_ID] = running_op.id

        if cmd:
            payload[Fields.THIEF][Fields.CMD] = cmd

        message = create_message_from_dict(payload, service_instance_id, run_id)

        return collections.namedtuple("WrappedMessage", "message running_op")(message, running_op)

    return wrapper_function


@pytest.fixture(scope="class")
def reported_props_factory(run_id, service_instance_id, random_dict_factory):  # noqa: F811
    def factory_function(running_op):
        return {
            Fields.THIEF: {
                Fields.RUN_ID: run_id,
                Fields.SERVICE_INSTANCE_ID: service_instance_id,
                Fields.TEST_CONTENT: {
                    Fields.REPORTED_PROPERTY_TEST: {
                        Fields.E2E_PROPERTY: {
                            Fields.ADD_OPERATION_ID: running_op.id,
                            Fields.RANDOM_CONTENT: random_dict_factory(),
                        }
                    }
                },
            }
        }

    return factory_function


@pytest.fixture(scope="function")
def reported_props(reported_props_factory, running_op):
    return reported_props_factory(running_op)
