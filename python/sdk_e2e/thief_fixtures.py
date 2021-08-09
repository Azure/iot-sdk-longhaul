# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import asyncio
import uuid
from operation_tickets import OperationTicketList
import thief_secrets


@pytest.fixture(scope="module")
def operation_ticket_list():
    return OperationTicketList()


@pytest.fixture(scope="class")
def operation_ticket_factory(operation_ticket_list):
    def factory_function():
        return operation_ticket_list.make_event_based_operation_ticket(event_module=asyncio)

    return factory_function


@pytest.fixture(scope="function")
def operation_ticket(operation_ticket_factory):
    return operation_ticket_factory()


@pytest.fixture(scope="module")
def run_id():
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def requested_service_pool():
    return thief_secrets.REQUESTED_SERVICE_POOL
