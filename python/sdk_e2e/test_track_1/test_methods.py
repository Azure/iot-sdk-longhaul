# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import logging
import asyncio
from thief_constants import Fields
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
    @pytest.mark.it("Can handle a simple direct method call")
    @pytest.mark.parametrize(
        "include_request_payload",
        [
            pytest.param(True, id="with request payload"),
            pytest.param(False, id="wihout request payload"),
        ],
    )
    @pytest.mark.parametrize(
        "include_response_payload",
        [
            pytest.param(True, id="with response payload"),
            pytest.param(False, id="wihout response payload"),
        ],
    )
    async def test_handle_method_call(
        self,
        client,
        random_dict_factory,
        event_loop,
        method_name,
        method_response_status,
        include_request_payload,
        include_response_payload,
        service_app,
    ):
        actual_request = None

        if include_request_payload:
            request_payload = random_dict_factory()
        else:
            request_payload = None

        if include_response_payload:
            response_payload = random_dict_factory()
        else:
            response_payload = None

        async def handle_on_method_request_received(request):
            nonlocal actual_request
            logger.info("Method request for {} received".format(request.name))
            actual_request = request
            logger.info("Sending response")
            await client.send_method_response(
                MethodResponse.create_from_method_request(
                    request, method_response_status, response_payload
                )
            )

        client.on_method_request_received = handle_on_method_request_received
        await asyncio.sleep(1)  # wait for subscribe, etc, to complete

        # invoke the method call
        method_response = await service_app.invoke_method(method_name, request_payload)

        # verify that the method request arrived correctly
        assert actual_request.name == method_name
        if request_payload:
            assert actual_request.payload == request_payload
        else:
            assert not actual_request.payload

        # and make sure the response came back successfully
        assert method_response[Fields.METHOD_RESPONSE_STATUS_CODE] == method_response_status
        assert method_response[Fields.METHOD_RESPONSE_PAYLOAD] == response_payload
