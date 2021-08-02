# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import asyncio
import json
from thief_constants import Fields, Commands
from azure.iot.device.iothub import CommandResponse

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def command_name():
    return "this_is_my_command_name"


@pytest.fixture
def component_name():
    return "this_is_my_component_name"


@pytest.fixture
def command_response_status():
    return 299


@pytest.mark.describe("Pnp Commands")
class TestPnpCommands(object):
    @pytest.mark.it("Can handle a simple command")
    @pytest.mark.parametrize(
        "include_request_payload",
        [
            pytest.param(True, id="with request payload"),
            pytest.param(False, id="without request payload"),
        ],
    )
    @pytest.mark.parametrize(
        "include_response_payload",
        [
            pytest.param(True, id="with response payload"),
            pytest.param(False, id="without response payload"),
        ],
    )
    @pytest.mark.parametrize(
        "include_component_name",
        [
            pytest.param(True, id="with component name"),
            pytest.param(False, id="without component name"),
        ],
    )
    async def test_handle_method_call(
        self,
        paired_client,
        message_factory,
        random_content_factory,
        event_loop,
        command_name,
        component_name,
        command_response_status,
        include_component_name,
        include_request_payload,
        include_response_payload,
    ):
        client = paired_client.client

        actual_request = None

        if include_request_payload:
            request_payload = random_content_factory()
        else:
            request_payload = ""

        if include_response_payload:
            response_payload = random_content_factory()
        else:
            response_payload = None

        async def handle_on_command_request_received(request):
            nonlocal actual_request
            logger.info(
                "command request for component {}, command {} received".format(
                    request.component_name, request.command_name
                )
            )
            actual_request = request
            logger.info("Sending response")
            await client.send_command_response(
                CommandResponse.create_from_command_request(
                    request, command_response_status, response_payload
                )
            )

        client.on_command_request_received = handle_on_command_request_received
        await asyncio.sleep(1)  # wait for subscribe, etc, to complete

        # invoke the method call
        invoke = message_factory(
            {
                Fields.THIEF: {
                    Fields.CMD: Commands.INVOKE_PNP_COMMAND,
                    Fields.COMMAND_NAME: command_name,
                    Fields.COMMAND_COMPONENT_NAME: component_name,
                    Fields.COMMAND_INVOKE_PAYLOAD: request_payload,
                }
            }
        )
        await client.send_message(invoke.message)

        # wait for the response to come back via the service API call
        await invoke.running_op.event.wait()
        command_response = json.loads(invoke.running_op.result_message.data)[Fields.THIEF]

        # verify that the method request arrived correctly
        assert actual_request.command_name == command_name
        assert actual_request.component_name == component_name

        if request_payload:
            assert actual_request.payload == request_payload
        else:
            assert not actual_request.payload

        # and make sure the response came back successfully
        # assert command_response[Fields.COMMAND_RESPONSE_STATUS_CODE] == command_response_status
        assert command_response[Fields.COMMAND_RESPONSE_PAYLOAD] == response_payload
