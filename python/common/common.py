# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import logging
import sys
import time
import six
import abc
from measurement import ThreadSafeCounter, ThreadSafeList
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger(__name__)

WAITING = "waiting"
RUNNING = "running"
FAILED = "failed"
COMPLETE = "complete"


class OperationMetrics(object):
    """
    Object we use internally to keep track of how a particular operation (such as D2C) is performing.
    """

    def __init__(self):
        self.inflight = ThreadSafeCounter()
        self.succeeded = ThreadSafeCounter()
        self.failed = ThreadSafeCounter()
        self.verified = ThreadSafeCounter()
        self.total_succeeded = ThreadSafeCounter()
        self.total_failed = ThreadSafeCounter()
        self.latency = ThreadSafeList()


class OperationConfig(object):
    """
    Object we use internally to keep track of how a particular operation (such as D2C) is is configured.
    """

    def __init__(self):
        self.operations_per_second = 0
        self.timeout_interval_in_seconds = 0
        self.failures_allowed = 0


class RunMetrics(object):
    """
    Object we use internally to keep track of how a the entire test is performing.
    """

    def __init__(self):
        self.run_start = None
        self.run_end = None
        self.run_state = WAITING


class RunConfig(object):
    """
    Object we use internally to keep track of how the entire test is configured.
    """

    def __init__(self):
        self.max_run_duration_in_seconds = 0
        self.heartbeat_interval = 10


@six.add_metaclass(abc.ABCMeta)
class BaseApp(object):
    """
    Base class for all client apps.  This will likely be refactored, and possibly eliminated,
    since much of this functionality needs to be moved to the soon-to-be-created ReaperThread.
    """

    def __init__(self):
        # We use the thread pool for many short-lived functions
        # make the pool big so it doesn't become a limiting factor.
        # we want to measure the SDK,  We don't want queueing to get in the way of our measurement.
        self.executor = ThreadPoolExecutor(max_workers=128)
        self.currently_running_operations = ThreadSafeList()
        self.done = False

    def run_longhaul_loop(self, loop_futures):
        """
        Make sure all threads keep running.  Every second, check for dead threads.
        """

        try:
            while True:
                # most work happens in other threads, so we sleep except for when we're
                # checking status
                time.sleep(1)

                # Make sure the loop threads are still running.  Force a failure if they fail.
                error = None
                for future in loop_futures:
                    if future.done():
                        self.done = True
                        error = Exception("Unexpected loop_futures exit")
                        try:
                            future.result()
                        except Exception as e:
                            logger.error("Error in future", exc_info=True)
                            error = e

                if error:
                    raise error

                # check for completed operations.  Count failures, but don't fail unless
                # we exceeed the limit
                for future in self.currently_running_operations.extract_list():
                    future_succeeded = False
                    future_failed = False
                    if future.done():
                        end_time = future.result()
                        if end_time > future.timeout_time:
                            future_failed = True
                        else:
                            future_succeeded = True
                    elif time.time() > future.timeout_time:
                        print("Timeout on running operation")
                        future_failed = True
                    else:
                        self.currently_running_operations.append(future)

                    if future_failed:
                        future.metrics.failed.increment()
                        future.metrics.total_failed.increment()
                        if future.metrics.failed.get_count() > future.config.failures_allowed:
                            raise Exception("Failure count exceeded")
                    elif future_succeeded:
                        future.metrics.succeeded.increment()
                        future.metrics.total_succeeded.increment()

        except Exception:
            logger.error("Error in main", exc_info=True)
            self.metrics.run_state = FAILED
        else:
            self.metrics.run_state = COMPLETE
        finally:
            logger.debug("setting done = True")
            self.done = True

            # finish all loop futures.  Ones that report test results will run one more time.
            self.trigger_thread_shutdown()
            futures_left = len(loop_futures)
            logger.debug("Waiting on {} futures".format(futures_left))
            for future in loop_futures:
                future.result()
                futures_left -= 1
                logger.debug("future.complete.{} futures left".format(futures_left))

            logger.debug("Done shutting down threads.  disconnecting")
            self.disconnect_all_clients()

        print("app is done")
        sys.exit(0 if self.metrics.run_state == COMPLETE else 1)

    @abc.abstractmethod
    def disconnect_all_clients(self):
        pass

    def trigger_thread_shutdown(self):
        pass
