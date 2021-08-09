# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import asyncio
import uuid
from running_operation_list import RunningOperationList
import thief_secrets


@pytest.fixture(scope="module")
def op_ticket_list():
    return RunningOperationList()


@pytest.fixture(scope="class")
def op_ticket_factory(op_ticket_list):
    def factory_function():
        return op_ticket_list.make_event_based_operation(event_module=asyncio)

    return factory_function


@pytest.fixture(scope="function")
def op_ticket(op_ticket_factory):
    return op_ticket_factory()


@pytest.fixture(scope="module")
def run_id():
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def requested_service_pool():
    return thief_secrets.REQUESTED_SERVICE_POOL
