# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import weakref
import threading
import uuid
import logging

logger = logging.getLogger("thief.{}".format(__name__))


class OperationBase(object):
    """
    Base class for running operations
    """

    def __del__(self):
        self.remove_from_owning_list(True)

    def remove_from_owning_list(self, in_dunder_del=False):
        """
        remove an operation fron the RunningOperationList which owns it.
        """
        owner = self.owner_weakref and self.owner_weakref()
        if owner:
            if in_dunder_del:
                logger.warning("Abandoning an incompleted operation: id={}".format(self.id))
            owner.remove(self.id)
            self.owner_weakref = None


class EventBasedOperation(OperationBase):
    """
    Running operation which sets an event when it is complete.
    """

    def __init__(self, owner):
        self.owner_weakref = weakref.ref(owner)
        self.id = str(uuid.uuid4())
        self.event = threading.Event()
        self.result_message = None

    def complete(self):
        """
        Mark a running operation as complete.  This sets the operation's event and removes
        the operation from the RunningOperationList which owns it.
        """
        if self.event:
            self.event.set()
            self.event = None
            self.remove_from_owning_list()
        else:
            logger.warning("Attempt to complete already completed operation: id={}".format(self.id))


class CallbackBasedOperation(OperationBase):
    """
    Running operation which calls a callback when it is complete.
    """

    def __init__(self, owner, callback, user_data):
        self.owner_weakref = weakref.ref(owner)
        self.id = str(uuid.uuid4())
        self.callback = callback
        self.user_data = user_data
        self.result_message = None

    def complete(self):
        """
        Mark a running operation as complete.  This calls the operation's callback and removes
        the operation from the RunningOperationList which owns it.
        """
        if self.callback:
            self.callback(self.id, self.user_data)
            self.callback = None
            self.remove_from_owning_list()
        else:
            logger.warning("Attempt to complete already completed operation: id={}".format(self.id))


class RunningOperationList(object):
    """
    Object which keeps tracks of operations which are running (in progress, not yet complete.)

    The "running operation" objects in this list have two properties which make them useful:
    1. They have an automatically-generated ID value (a guid) which can be passed as a operationId.
    2. They have a complete method, which can either set a `threading.Event` object or call a callback.

    Using these objects, we can have a guid (a `operationId`) which is like a "completion token".
    When the server returns the operationId, this list can use that guid to run some "on complete"
    code, which might be a callback, or might be a `threading.Event` object.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.list = {}

    def make_event_based_operation(self):
        """
        Make and return a running opreation object which fires an event when it is complete.
        """
        operation = EventBasedOperation(self)
        with self.lock:
            self.list[operation.id] = operation
        return operation

    def make_callback_based_operation(self, callback, user_data):
        """
        Make and return a running opreation object which calls a callback when it is complete.
        """
        operation = CallbackBasedOperation(self, callback, user_data)
        with self.lock:
            self.list[operation.id] = operation
        return operation

    def remove(self, id):
        """
        Remove an operation object from this list.  Returns the operation which removed or
        `None` if that operation is not in the list.
        """
        with self.lock:
            if id in self.list:
                operation = self.list[id]
                del self.list[id]
                return operation
            else:
                return None

    def get(self, id):
        """
        Get an operation object from this list.  Returns `None` if an operation with this
        id is not in the list.
        """
        with self.lock:
            return self.list.get(id, None)
