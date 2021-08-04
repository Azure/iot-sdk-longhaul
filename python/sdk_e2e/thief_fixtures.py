# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import asyncio
import uuid
from running_operation_list import RunningOperationList
import thief_secrets


@pytest.fixture(scope="module")
def running_operation_list():
    return RunningOperationList()


@pytest.fixture(scope="class")
def op_factory(running_operation_list):
    def factory_function():
        return running_operation_list.make_event_based_operation(event_module=asyncio)

    return factory_function


@pytest.fixture(scope="function")
def running_op(op_factory):
    return op_factory()


@pytest.fixture(scope="module")
def run_id():
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def requested_service_pool():
    return thief_secrets.REQUESTED_SERVICE_POOL
