# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import threading


class ThreadSafeCounter(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.value = 0

    def set(self, value):
        with self.lock:
            self.value = value

    def add(self, value):
        with self.lock:
            self.value += value

    def increment(self):
        self.add(1)

    def decrement(self):
        self.add(-1)

    def get_count(self):
        with self.lock:
            return self.value

    def extract_count(self):
        with self.lock:
            value = self.value
            self.value = 0
            return value
