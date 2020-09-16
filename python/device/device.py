# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import logging
import os
import time
import uuid
import json
import datetime
import threading
from measurement import MeasureLatency
import dps
import common

from azure.iot.device import Message

logging.basicConfig(level=logging.ERROR)
# logging.getLogger("paho").setLevel(level=logging.DEBUG)

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)


provisioning_host = os.environ["THIEF_DEVICE_PROVISIONING_HOST"]
id_scope = os.environ["THIEF_DEVICE_ID_SCOPE"]
group_symmetric_key = os.environ["THIEF_DEVICE_GROUP_SYMMETRIC_KEY"]
registration_id = os.environ["THIEF_DEVICE_ID"]


class DeviceRunMetrics(common.RunMetrics):
    """
    Object we use internally to keep track of how a the entire test is performing.
    """

    def __init__(self):
        super(DeviceRunMetrics, self).__init__()
        self.d2c = common.OperationMetrics()


class DeviceRunConfig(common.RunConfig):
    """
    Object we use internally to keep track of how the entire test is configured.
    """

    def __init__(self):
        super(DeviceRunConfig, self).__init__()
        self.system_telemetry_send_interval_in_seconds = 0
        self.d2c = common.OperationConfig()


def make_new_d2c_payload(message_id):
    """
    Helper function to create a unique payload which can be sent up as d2c message
    """
    msg = {"messageId": message_id, "thiefPingback": True}
    return Message(json.dumps(msg))


def set_config(config):
    """
    Helper function which sets our configuration.  Right now, this is hardcoded.
    Later, this will come from desired properties.
    """
    config.system_telemetry_send_interval_in_seconds = 10
    config.max_run_duration_in_seconds = 7200
    config.d2c.operations_per_second = 3
    config.d2c.timeout_interval_in_seconds = 60
    config.d2c.failures_allowed = 0


class DeviceApp(common.BaseApp):
    """
    Main application object
    """

    def __init__(self):
        super(DeviceApp, self).__init__()
        self.client = None
        self.metrics = DeviceRunMetrics()
        self.config = DeviceRunConfig()
        self.d2c_set_lock = threading.Lock()
        self.d2c_confirmed = set()
        self.d2c_unconfirmed = set()
        self.last_heartbeat = time.time()

    def update_initial_properties(self):
        """
        Update reported properties at the start of a run
        """
        # toto: update these values
        props = {
            "runStart": str(datetime.datetime.now()),
            "runState": common.WAITING,
            "sdkLanguage": "python",
        }

        logger.debug("updating props: {}".format(props))
        self.client.patch_twin_reported_properties(props)

    def d2c_thread(self, config, metrics):
        """
        Thread to continuously send d2c messages throughout the longhaul run
        """

        def send_single_d2c_message():
            message_id = str(uuid.uuid4())
            data = make_new_d2c_payload(message_id)
            latency = MeasureLatency()

            try:
                metrics.inflight.increment()
                with latency:
                    self.client.send_message(data)
                metrics.latency.append(latency.get_latency())
                with self.d2c_set_lock:
                    self.d2c_unconfirmed.add(message_id)

            finally:
                metrics.inflight.decrement()

            return time.time()

        while not self.done:
            # submit a thread for the new event
            send_future = self.executor.submit(send_single_d2c_message)

            # timeout is based on when the task is submitted, not when it actually starts running
            send_future.timeout_time = time.time() + config.timeout_interval_in_seconds
            send_future.config = self.config.d2c
            send_future.metrics = self.metrics.d2c

            # add to thread-safe list of futures
            self.currently_running_operations.append(send_future)

            # sleep until we need to send again
            time.sleep(1 / config.operations_per_second)

    def send_telemetry_thread(self):
        """
        Thread to occasionally send telemetry containing information about how the test
        is progressing
        """
        done = False

        while not done:
            # setting this at the begining and checking at the end guarantees one last update
            # before the thread dies
            if self.done:
                done = True

            props = {
                "averageD2cRoundtripLatencyToGatewayInSeconds": self.metrics.d2c.latency.extract_average(),
                "d2cInFlightCount": self.metrics.d2c.inflight.get_count(),
                "d2cSuccessCount": self.metrics.d2c.succeeded.extract_count(),
                "d2cFailureCount": self.metrics.d2c.failed.extract_count(),
            }

            msg = Message(json.dumps(props))
            msg.content_type = "application/json"
            msg.content_encoding = "utf-8"
            logger.debug("Selnding telementry: {}".format(msg.data))
            self.client.send_message(msg)

            time.sleep(self.config.system_telemetry_send_interval_in_seconds)

    def update_properties_thread(self):
        """
        Thread which occasionally sends reported properties with information about how the
        test is progressing
        """
        done = False

        while not done:
            # setting this at the begining and checking at the end guarantees one last update
            # before the thread dies
            if self.done:
                done = True

            props = {
                "d2cTotalSuccessCount": self.metrics.d2c.total_succeeded.get_count(),
                "d2cTotalFailureCount": self.metrics.d2c.total_failed.get_count(),
                "runState": self.metrics.run_state,
            }
            if self.metrics.run_end:
                props["runEnd"] = self.metrics.run_end

            logger.debug("updating props: {}".format(props))
            self.client.patch_twin_reported_properties(props)

            time.sleep(self.config.system_telemetry_send_interval_in_seconds)

    def receive_message_thread(self):
        """
        Thread which continuously receives c2d messages throughout the test run.
        This will be soon renamed to be the c2d_dispatcher_thread.
        """
        while not self.done:
            msg = self.client.receive_message()

            obj = json.loads(msg.data.decode())
            if obj.get("thiefHeartbeat"):
                logger.debug("heartbeat received")
                self.last_heartbeat = time.time()
            elif obj.get("thiefPingbackResponse"):
                list = obj.get("messageIds")
                if list:
                    with self.d2c_set_lock:
                        for message_id in list:
                            self.d2c_confirmed.add(message_id)
                        remove = self.d2c_confirmed & self.d2c_unconfirmed
                        print("received {} items.  Removed {}".format(len(list), len(remove)))
                        self.metrics.d2c.verified.add(len(remove))
                        self.d2c_confirmed -= remove
                        self.d2c_unconfirmed -= remove

    def heartbeat_thread(self):
        """
        Thread which is responsible for sending heartbeat messages to the other side and
        also for making sure that heartbeat messages are received often enough
        """
        while not self.done:
            msg = Message(json.dumps({"thiefHeartbeat": True}))
            msg.content_type = "application/json"
            msg.content_encoding = "utf-8"
            logger.debug("sending heartbeat")
            self.client.send_message(msg)

            seconds_since_last_heartbeat = time.time() - self.last_heartbeat
            if seconds_since_last_heartbeat > (self.config.heartbeat_interval * 3):
                raise Exception(
                    "No heartbeat received for {} seconds".format(seconds_since_last_heartbeat)
                )

            time.sleep(self.config.heartbeat_interval)

    def run_device_loop(self):
        # collection of Future objects for all of the threads that are running continuously
        # these are stored in a local variable because no other thread procs should need this.
        loop_futures = []

        # Create our client and push initial properties
        self.client = dps.create_device_client_using_dps_group_key(
            provisioning_host=provisioning_host,
            registration_id=registration_id,
            id_scope=id_scope,
            group_symmetric_key=group_symmetric_key,
        )
        self.update_initial_properties()

        # Spin up our worker threads.
        loop_futures.append(
            self.executor.submit(self.d2c_thread, self.config.d2c, self.metrics.d2c)
        )
        loop_futures.append(self.executor.submit(self.send_telemetry_thread))
        loop_futures.append(self.executor.submit(self.update_properties_thread))
        loop_futures.append(self.executor.submit(self.receive_message_thread))
        loop_futures.append(self.executor.submit(self.heartbeat_thread))

        return self.run_longhaul_loop(loop_futures)

    def disconnect_all_clients(self):
        self.client.disconnect()

    def main(self):
        set_config(self.config)

        self.metrics.run_start = time.time()
        self.metrics.run_state = common.RUNNING

        return self.run_device_loop()


if __name__ == "__main__":
    DeviceApp().main()
