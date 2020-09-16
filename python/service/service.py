# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import logging
import common
import time
import os
import queue
import threading
import json
from azure.iot.hub import IoTHubRegistryManager
from azure.eventhub import EventHubConsumerClient

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

iothub_connection_string = os.environ["THIEF_SERVICE_CONNECTION_STRING"]
eventhub_connection_string = os.environ["THIEF_EVENTHUB_CONNECTION_STRING"]
eventhub_consumer_group = os.environ["THIEF_EVENTHUB_CONSUMER_GROUP"]
device_id = os.environ["THIEF_DEVICE_ID"]

logger.debug("service={}".format(iothub_connection_string))
logger.debug("eh={}".format(eventhub_connection_string))
logger.debug("group={}".format(eventhub_consumer_group))


class ServiceRunMetrics(common.RunMetrics):
    """
    Object we use internally to keep track of how a the entire test is performing.
    """

    def __init__(self):
        super(ServiceRunMetrics, self).__init__()


class ServiceRunConfig(common.RunConfig):
    """
    Object we use internally to keep track of how the entire test is configured.
    """

    def __init__(self):
        super(ServiceRunConfig, self).__init__()


def unpack_config(config):
    pass


def get_device_id_from_event(event):
    return event.message.annotations["iothub-connection-device-id".encode()].decode()


class ServiceApp(common.BaseApp):
    """
    Main application object
    """

    def __init__(self):
        super(ServiceApp, self).__init__()
        self.registry_manager = None
        self.eventhub_consumer_client = None
        self.metrics = ServiceRunMetrics()
        self.config = ServiceRunConfig()
        self.pingback_events = queue.Queue()
        self.pingback_events_lock = threading.Lock()
        self.last_heartbeat = time.time()

    def eventhub_listener_thread(self):
        """
        Thread to listen on eventhub for events which are targeted to our device_id
        """

        def on_error(partition_context, error):
            logger.debug("on_error: {}".format(error))

        def on_partition_initialize(partition_context):
            logger.debug("on_partition_initialize")

        def on_partition_close(partition_context, reason):
            logger.debug("on_partition_close: {}".format(reason))

        def on_event(partition_context, event):
            if get_device_id_from_event(event) == device_id:
                body = event.body_as_json()
                if "thiefHeartbeat" in body:
                    logger.debug("heartbeat received")
                    self.last_heartbeat = time.time()
                elif "thiefPingback" in body:
                    with self.pingback_events_lock:
                        self.pingback_events.put(event)

        logger.debug("starting receive")
        with self.eventhub_consumer_client:
            self.eventhub_consumer_client.receive(
                on_event,
                on_error=on_error,
                on_partition_initialize=on_partition_initialize,
                on_partition_close=on_partition_close,
            )

    def pingback_thread(self):
        """
        Thread which is responsible for returning pingback response message to the
        device client on the other side of the wall.
        """
        while not self.done:
            message_ids = []
            while True:
                try:
                    event = self.pingback_events.get_nowait()
                except queue.Empty:
                    break
                message_ids.append(event.body_as_json()["messageId"])

            if len(message_ids):
                print("pingback for {}".format(message_ids))

                message = json.dumps({"thiefPingbackResponse": True, "messageIds": message_ids})

                self.registry_manager.send_c2d_message(
                    device_id,
                    message,
                    {"contentType": "application/json", "contentEncoding": "utf-8"},
                )

            time.sleep(1)

    def heartbeat_thread(self):
        """
        Thread which is responsible for sending heartbeat messages to the other side and
        also for making sure that heartbeat messages are received often enough
        """
        while not self.done:
            message = json.dumps({"thiefHeartbeat": True})

            logger.debug("sending heartbeat")
            self.registry_manager.send_c2d_message(
                device_id, message, {"contentType": "application/json", "contentEncoding": "utf-8"},
            )

            seconds_since_last_heartbeat = time.time() - self.last_heartbeat
            if seconds_since_last_heartbeat > (self.config.heartbeat_interval * 3):
                raise Exception(
                    "No heartbeat received for {} seconds".format(seconds_since_last_heartbeat)
                )

            time.sleep(self.config.heartbeat_interval)

    def run_service_loop(self):
        # collection of Future objects for all of the threads that are running continuously
        # these are stored in a local variable because no other thread procs should need this.
        loop_futures = []

        unpack_config(self.config)

        self.registry_manager = IoTHubRegistryManager(iothub_connection_string)

        # Make sure our device exists before we continue.  Since the device app and this
        # app are both starting up around the same time, it's possible that the device app
        # hasn't used DPS to crate the device yet.  Give up after 60 seconds
        start_time = time.time()
        device = None
        while not device and (time.time() - start_time) < 60:
            try:
                device = self.registry_manager.get_device(device_id)
            except Exception as e:
                logger.info("get_device returned: {}".format(e))
                try:
                    if e.response.status_code == 404:
                        # a 404.  sleep and try again
                        logger.info("Sleeping for 10 seconds before trying again")
                        time.sleep(10)
                    else:
                        # not a 404.  Raise it.
                        raise e
                except AttributeError:
                    # an AttributeError means this wasn't an msrest error.  raise it.
                    raise e

        if not device:
            raise Exception("Device does not exist.  Cannot continue")

        self.eventhub_consumer_client = EventHubConsumerClient.from_connection_string(
            eventhub_connection_string, consumer_group=eventhub_consumer_group
        )

        loop_futures.append(self.executor.submit(self.eventhub_listener_thread))
        loop_futures.append(self.executor.submit(self.pingback_thread))
        loop_futures.append(self.executor.submit(self.heartbeat_thread))

        # Spin up our worker threads.
        return self.run_longhaul_loop(loop_futures)

    def disconnect_all_clients(self):
        if self.eventhub_consumer_client:
            self.eventhub_consumer_client.close()
            self.eventhub_consumer_client = None

    def trigger_thread_shutdown(self):
        super(ServiceApp, self).trigger_thread_shutdown()
        if self.eventhub_consumer_client:
            self.eventhub_consumer_client.close()
            self.eventhub_consumer_client = None

    def main(self):
        unpack_config(self.config)

        self.metrics.run_start = time.time()
        self.metrics.run_state = common.RUNNING

        return self.run_service_loop()


if __name__ == "__main__":
    ServiceApp().main()
