# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import asyncio

# noqa: F401 defined in .flake8 file in root of repo

from drop_fixtures import dropper
from thief_fixtures import (
    op_ticket_list,
    op_ticket_factory,
    op_ticket,
    run_id,
    requested_service_pool,
)
from content_fixtures import (
    random_string_factory,
    random_string,
    random_dict_factory,
    random_dict,
    random_property_value,
)
from pnp_fixtures import (
    pnp_model_id,
    pnp_command_name,
    pnp_component_name,
    pnp_command_response_status,
    pnp_writable_property_name,
    pnp_read_only_property_name,
    pnp_ack_code,
    pnp_ack_description,
)


@pytest.fixture(scope="module")
def transport():
    return "mqtt"


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()
