# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import concurrent.futures
import threading
import time
import logging
import traceback
import sys

logger = logging.getLogger(__name__)


class FutureThreadInfo(object):
    """
    Object that we can use to tie `Future` objects and `Thread` objects together.
    """

    def __init__(self):
        self.future = None
        self.thread = None
        self.started = threading.Event()
        self.start_time = None
        self.watchdog_time = None
        self.long_run_warning_reported = False
        self.executor = None
        self.name_at_death = None


# thread_local_storage is an object that looks like a global, but has a different
# value inside each thread.  We use this so we can have a different watchdog_time
# value in each thread.
thread_local_storage = threading.local()

# How many seconds can a thread go without calling `reset_watchdog` before a failure occurs.
DEFAULT_WATCHDOG_INTERVAL = 600


def reset_watchdog():
    # reset the watchdog_time value inside this thread's local storage
    thread_local_storage.future_thread_info.watchdog_reset_time = time.time()


class BetterThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """
    Class which improves on ThreadPoolExecutor by adding:
    1. Watchdog functionality for "long-lived" threads.
    2. Duration checks for "short-lived" threads.
    3. Various other functionailty that smells like it needs to be refactored.
    """

    def __init__(
        self,
        *args,
        watchdog_interval=DEFAULT_WATCHDOG_INTERVAL,
        long_thread_warning_interval=60,
        **kwargs
    ):
        super(BetterThreadPoolExecutor, self).__init__(*args, **kwargs)
        self.outstanding_futures = []
        self.outstanding_futures_lock = threading.Lock()
        self.watchdog_interval = watchdog_interval
        self.long_thread_warning_interval = long_thread_warning_interval
        self.cv = threading.Condition()

    def wait_for_thread_death_event(self, timeout=None):
        with self.cv:
            self.cv.wait(timeout)

    def trigger_thread_death_event(self):
        with self.cv:
            self.cv.notify_all()

    def wait(self, timeout=None):
        with self.outstanding_futures_lock:
            futures = [x.future for x in self.outstanding_futures]
        return concurrent.futures.wait(futures, timeout=timeout)

    def submit(self, fn, *args, critical=False, thread_name=None, **kwargs):
        def _thread_outer_proc(future_thread_info, *args, **kwargs):
            # Keep a pointer to our structure in TLS
            thread_local_storage.future_thread_info = future_thread_info

            future_thread_info.thread = threading.current_thread()
            future_thread_info.critical = critical
            future_thread_info.start_time = time.time()

            # Set our Event so calling code can know that we're ready to run
            future_thread_info.started.set()
            try:
                result = fn(*args, **kwargs)
            finally:
                future_thread_info.name_at_death = future_thread_info.thread.name
                if future_thread_info.long_run_warning_reported:
                    logger.warning(
                        "Long-running thread {} complete after {} seconds".format(
                            future_thread_info.thread.name,
                            time.time() - future_thread_info.start_time,
                        )
                    )
                future_thread_info.thread = None
                thread_local_storage.future_thread_info = None
                self.trigger_thread_death_event()
            return result

        future_thread_info = FutureThreadInfo()
        future_thread_info.executor = self

        # Start the thread.  Wait for `started` to be set so can know that
        # our internal accounting is all set up.  This closes a very small window.
        future = super(BetterThreadPoolExecutor, self).submit(
            _thread_outer_proc, future_thread_info, *args, **kwargs
        )
        future_thread_info.future = future
        future_thread_info.started.wait()

        if thread_name:
            future_thread_info.thread.name = thread_name
        else:
            future_thread_info.thread.name = fn.__name__

        with self.outstanding_futures_lock:
            self.outstanding_futures.append(future_thread_info)

        return future

    def check_watchdogs(self):

        first_exception = None

        with self.outstanding_futures_lock:
            for info in (x for x in self.outstanding_futures if x.thread):
                if info.watchdog_reset_time:
                    # Threads that use watchdog need to call reset_watchdog at a regular interval or else they fail
                    time_since_reset = time.time() - info.watchdog_reset_time
                    if time_since_reset > self.watchdog_interval:

                        logger.warning(
                            "Thread named {} with id {} has not responded in {} seconds".format(
                                info.thread.name, info.thread.ident, time_since_reset
                            )
                        )
                        frame = sys._current_frames().get(info.thread.ident, None)
                        logger.warning(traceback.format_stack(frame))

                        if info.critical:
                            logger.error("Thread {} watchdog failure".format(info.thread.name))
                            first_exception = first_exception or Exception(
                                "Thread {} watchdog failure".format(info.name)
                            )

                else:
                    # threads that don't use watchdog can only live so long before generating a warning.
                    # But, only generate one warning
                    if not info.long_run_warning_reported:
                        thread_life_time = time.time() - info.start_time
                        if thread_life_time > self.long_thread_warning_interval:

                            logger.warning(
                                "Long-running thread named {} with id {} has been alive for {} seconds".format(
                                    info.thread.name, info.thread.ident, thread_life_time
                                )
                            )
                            frame = sys._current_frames().get(info.thread.ident, None)
                            logger.warning(traceback.format_stack(frame))

                            if info.critical:
                                logger.error("Thread {} long-run failure".format(info.thread.name))
                                first_exception = first_exception or Exception(
                                    "Thread {} long-run failure".format(info.name)
                                )
                            info.long_run_warning_reported = True

            if first_exception:
                raise first_exception

    def check_for_failures(self, non_critical_exception_callback):

        with self.outstanding_futures_lock:
            old_list = self.outstanding_futures
            self.outstanding_futures = []
            completed_futures = []

            for info in old_list:
                if info.thread:
                    self.outstanding_futures.append(info)
                else:
                    completed_futures.append(info)

        first_exception = None
        for info in completed_futures:
            assert info.future.done()
            logger.info("---------------------------------DONE: {}".format(info.name_at_death))
            e = info.future.exception()
            if e:
                if info.critical:
                    logger.error(
                        "Critical error: thread {} failed with {}".format(info.name_at_death, e)
                    )
                    first_exception = first_exception or e
                else:
                    logger.error(
                        "Non-critical error: thread {} failed with {}".format(info.name_at_death, e)
                    )
                    if non_critical_exception_callback:
                        non_critical_exception_callback(e)

        if first_exception:
            raise first_exception
