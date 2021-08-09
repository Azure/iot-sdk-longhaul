# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import json
import logging
from thief_constants import Fields, Commands

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def service_app(client, message_factory):
    class ServiceApp(object):
        async def set_desired_props(self, desired_props):
            await client.send_message(
                message_factory(
                    {
                        Fields.THIEF: {
                            Fields.CMD: Commands.SET_DESIRED_PROPS,
                            Fields.DESIRED_PROPERTIES: desired_props,
                        }
                    }
                ).message
            )

        async def invoke_method(self, method_name, method_payload):
            # invoke the method call
            invoke = message_factory(
                {
                    Fields.THIEF: {
                        Fields.CMD: Commands.INVOKE_METHOD,
                        Fields.METHOD_NAME: method_name,
                        Fields.METHOD_INVOKE_PAYLOAD: method_payload,
                    }
                }
            )
            await client.send_message(invoke.message)

            # wait for the response to come back via the service API call
            await invoke.op_ticket.event.wait()
            method_response = json.loads(invoke.op_ticket.result_message.data)[Fields.THIEF]

            return method_response

    return ServiceApp()


def make_desired_property_patch(component_name, property_name, property_value):
    logger.info("Setting {} to {}".format(property_name, property_value))
    if component_name:
        return {
            Fields.THIEF: {
                Fields.CMD: Commands.UPDATE_PNP_PROPERTIES,
                Fields.PNP_PROPERTIES_UPDATE_PATCH: [
                    {
                        "op": "add",
                        "path": "/{}".format(component_name),
                        "value": {property_name: property_value, "$metadata": {}},
                    }
                ],
            }
        }
    else:
        return {
            Fields.THIEF: {
                Fields.CMD: Commands.UPDATE_PNP_PROPERTIES,
                Fields.PNP_PROPERTIES_UPDATE_PATCH: [
                    {"op": "add", "path": "/{}".format(property_name), "value": property_value}
                ],
            }
        }


@pytest.fixture(scope="function")
def pnp_service_app(client, message_factory):
    class PnpServiceApp(object):
        async def invoke_pnp_command(self, pnp_command_name, pnp_component_name, request_payload):
            invoke = message_factory(
                {
                    Fields.THIEF: {
                        Fields.CMD: Commands.INVOKE_PNP_COMMAND,
                        Fields.COMMAND_NAME: pnp_command_name,
                        Fields.COMMAND_COMPONENT_NAME: pnp_component_name,
                        Fields.COMMAND_INVOKE_PAYLOAD: request_payload,
                    }
                }
            )
            await client.send_message(invoke.message)

            # wait for the response to come back via the service API call
            await invoke.op_ticket.event.wait()
            command_response = json.loads(invoke.op_ticket.result_message.data)[Fields.THIEF]

            return command_response

        async def get_pnp_properties(self):
            msg = message_factory({}, cmd=Commands.GET_PNP_PROPERTIES)
            await client.send_message(msg.message)
            await msg.op_ticket.event.wait()

            return (
                json.loads(msg.op_ticket.result_message.data)
                .get(Fields.THIEF, {})
                .get(Fields.PNP_PROPERTIES_CONTENTS, {})
            )

        async def update_pnp_properties(
            self, pnp_component_name, pnp_property_name, property_value
        ):
            patch = message_factory(
                make_desired_property_patch(pnp_component_name, pnp_property_name, property_value,)
            )
            logger.info("sending patch")
            await client.send_message(patch.message)

    return PnpServiceApp()
