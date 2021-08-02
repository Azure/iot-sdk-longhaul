# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import asyncio
import json
from thief_constants import Fields, Commands
from azure.iot.device.iothub import MethodResponse

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def method_name():
    return "this_is_my_method_name"


@pytest.fixture
def method_response_status():
    return 299


@pytest.mark.describe("Device Client methods")
class TestMethods(object):
    @pytest.mark.it("Can handle a simple direct method call and return a successful result")
    async def test_handle_method_success(
        self,
        paired_client,
        message_factory,
        random_content_factory,
        event_loop,
        method_name,
        method_response_status,
    ):
        client = paired_client.client

        method_request = None
        request_payload = random_content_factory()
        response_payload = random_content_factory()

        async def handle_on_method_request_received(request):
            nonlocal method_request
            logger.info("Method request for {} received".format(request.name))
            method_request = request
            logger.info("Sending response")
            await client.send_method_response(
                MethodResponse.create_from_method_request(
                    request, method_response_status, response_payload
                )
            )

        client.on_method_request_received = handle_on_method_request_received
        await asyncio.sleep(1)  # wait for subscribe, etc, to compelte

        # invoke the method call
        invoke = message_factory(
            {
                Fields.THIEF: {
                    Fields.CMD: Commands.INVOKE_METHOD,
                    Fields.METHOD_NAME: method_name,
                    Fields.METHOD_INVOKE_PAYLOAD: request_payload,
                }
            }
        )
        await client.send_message(invoke.message)

        # wait for the response to come back via the service API call
        await invoke.running_op.event.wait()
        method_response = json.loads(invoke.running_op.result_message.data)[Fields.THIEF]

        # verify that the method request arrived correctly
        assert method_request.name == method_name
        assert method_request.payload == request_payload

        # and make sure the response came back successfully
        assert method_response[Fields.METHOD_RESPONSE_STATUS_CODE] == method_response_status
        assert method_response[Fields.METHOD_RESPONSE_PAYLOAD] == response_payload
