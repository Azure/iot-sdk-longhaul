# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import weakref
import threading
import uuid


class Base(object):
    def __del__(self):
        owner = self.owner_weakref and self.owner_weakref()
        if owner:
            owner.remove(self.id)


class Event(Base):
    def __init__(self, owner):
        self.owner_weakref = weakref.ref(owner)
        self.id = str(uuid.uuid4())
        self.event = threading.Event()


class Callback(Base):
    def __init__(self, owner, callback, user_data):
        self.owner_weakref = weakref.ref(owner)
        self.id = str(uuid.uuid4())
        self.callback = callback
        self.user_data = user_data


class ServiceAckWaitList(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.list = {}

    def make_event(self):
        e = Event(self)
        with self.lock:
            self.list[e.id] = e
        return e

    def make_callback(self, callback, user_data):
        e = Callback(self, callback, user_data)
        with self.lock:
            self.list[e.id] = e
        return e

    def remove(self, id):
        with self.lock:
            if id in self.list:
                e = self.list[id]
                del self.list[id]
                return e
            else:
                return None

    def get(self, id):
        with self.lock:
            return self.list.get(id, None)
