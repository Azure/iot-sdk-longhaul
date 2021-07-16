# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
import pytest
import uuid
import logging
from running_operation_list import RunningOperationList
import thief_secrets
import drop

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)

drop.reconnect_all("mqtt")


@pytest.fixture(scope="module")
def running_operation_list():
    return RunningOperationList()


@pytest.fixture(scope="module")
def run_id():
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def requested_service_pool():
    return thief_secrets.THIEF_REQUESTED_SERVICE_POOL


@pytest.fixture(scope="module")
def transport():
    return "mqtt"


# TODO: set to 10 only when necessary
@pytest.fixture(scope="module")
def keep_alive():
    return 10


class Dropper(object):
    def __init__(self, transport):
        self.transport = transport

    def drop_outgoing(self):
        drop.disconnect_port("DROP", self.transport)

    def reject_outgoing(self):
        drop.disconnect_port("REJECT", self.transport)

    def restore_all(self):
        drop.reconnect_all(self.transport)


@pytest.fixture(scope="function")
async def dropper(transport):
    dropper = Dropper(transport)
    yield dropper
    logger.info("restoring all")
    dropper.restore_all()
