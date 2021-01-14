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
import pprint
from concurrent.futures import ThreadPoolExecutor
import dps
import queue
import app_base
from azure.iot.device import Message
import azure.iot.device.constant
from measurement import ThreadSafeCounter
import azure_monitor
from azure_monitor_metrics import MetricsReporter
from out_of_order_message_tracker import OutOfOrderMessageTracker
from thief_constants import (
    Const,
    Fields,
    Types,
    Events,
    MetricNames,
    DeviceSettings as Settings,
)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("paho").setLevel(level=logging.DEBUG)
logging.getLogger("thief").setLevel(level=logging.INFO)
logging.getLogger("azure.iot").setLevel(level=logging.INFO)

logger = logging.getLogger("thief.{}".format(__name__))

# TODO: exit service when device stops responding
# TODO: add code to receive rest of pingacks at end.  wait for delta since last to be > 20 seconds.
# TODO: add mid to debug logs as custom property, maybe service_ack id

# use os.environ[] for required environment variables
provisioning_host = os.environ["THIEF_DEVICE_PROVISIONING_HOST"]
id_scope = os.environ["THIEF_DEVICE_ID_SCOPE"]
group_symmetric_key = os.environ["THIEF_DEVICE_GROUP_SYMMETRIC_KEY"]
registration_id = os.environ["THIEF_DEVICE_ID"]
requested_service_pool = os.environ["THIEF_REQUESTED_SERVICE_POOL"]

run_id = str(uuid.uuid4())

# configure our traces and events to go to Azure Monitor
azure_monitor.add_logging_properties(
    client_type="device",
    run_id=run_id,
    sdk_version=azure.iot.device.constant.VERSION,
    transport="mqtt",
    pool_id=requested_service_pool,
)
event_logger = azure_monitor.get_event_logger()
azure_monitor.log_to_azure_monitor("thief")
azure_monitor.log_to_azure_monitor("azure")
azure_monitor.log_to_azure_monitor("paho")


class ServiceAckWaitInfo(object):
    def __init__(
        self,
        on_service_ack_received,
        service_ack_id,
        service_ack_type,
        queue_epochtime=None,
        send_epochtime=None,
        user_data=None,
    ):
        self.on_service_ack_received = on_service_ack_received
        self.service_ack_id = service_ack_id
        self.service_ack_type = service_ack_type
        self.queue_epochtime = queue_epochtime
        self.send_epochtime = send_epochtime
        self.user_data = user_data


class CustomPropertyNames(object):
    EVENT_DATE_TIME_UTC = "eventDateTimeUtc"
    SERVICE_ACK_ID = "serviceAckid"


class DeviceRunMetrics(object):
    """
    Object we use internally to keep track of how a the entire test is performing.
    """

    def __init__(self):
        self.run_start_utc = None
        self.run_state = app_base.WAITING
        self.exit_reason = None

        self.client_library_count_exceptions = ThreadSafeCounter()

        self.send_message_count_unacked = ThreadSafeCounter()
        self.send_message_count_sent = ThreadSafeCounter()
        self.send_message_count_received_by_service_app = ThreadSafeCounter()

        self.receive_c2d_count_received = ThreadSafeCounter()

        self.reported_properties_count_added = ThreadSafeCounter()
        self.reported_properties_count_added_not_verified = ThreadSafeCounter()
        self.reported_properties_count_removed = ThreadSafeCounter()
        self.reported_properties_count_removed_not_verified = ThreadSafeCounter()


"""
Object we use internally to keep track of how the entire test is configured.
Currently hardcoded. Later, this will come from desired properties.
"""
device_run_config = {
    Settings.THIEF_MAX_RUN_DURATION_IN_SECONDS: 0,
    Settings.THIEF_PROPERTY_UPDATE_INTERVAL_IN_SECONDS: 30,
    Settings.THIEF_WATCHDOG_FAILURE_INTERVAL_IN_SECONDS: 300,
    Settings.THIEF_ALLOWED_CLIENT_LIBRARY_EXCEPTION_COUNT: 10,
    Settings.PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS: 900,
    Settings.PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS: 30,
    Settings.SEND_MESSAGE_OPERATIONS_PER_SECOND: 1,
    Settings.SEND_MESSAGE_THREAD_COUNT: 10,
    Settings.SEND_MESSAGE_ALLOWED_FAILURE_COUNT: 1000,
    Settings.RECEIVE_C2D_INTERVAL_IN_SECONDS: 20,
    Settings.RECEIVE_C2D_ALLOWED_MISSING_MESSAGE_COUNT: 100,
    Settings.REPORTED_PROPERTIES_UPDATE_INTERVAL_IN_SECONDS: 10,
    Settings.REPORTED_PROPERTIES_UPDATE_ALLOWED_FAILURE_COUNT: 50,
}


class DeviceApp(app_base.AppBase):
    """
    Main application object
    """

    def __init__(self):
        global device_run_config
        super(DeviceApp, self).__init__()

        self.executor = ThreadPoolExecutor(max_workers=128)
        self.done = threading.Event()
        self.client = None
        self.hub = None
        self.device_id = None
        self.metrics = DeviceRunMetrics()
        self.config = device_run_config
        self.service_instance = None
        # for service_acks
        self.service_ack_list_lock = threading.Lock()
        self.service_ack_wait_list = {}
        self.incoming_service_ack_response_queue = queue.Queue()
        # for telemetry
        self.outgoing_test_message_queue = queue.Queue()
        # for metrics
        self.reporter_lock = threading.Lock()
        self.reporter = MetricsReporter()
        self._configure_azure_monitor_metrics()
        # for pairing
        self.pairing_complete = False
        self.incoming_pairing_message_queue = queue.Queue()
        # for c2d
        self.out_of_order_message_tracker = OutOfOrderMessageTracker()
        self.incoming_test_c2d_message_queue = queue.Queue()

    def _configure_azure_monitor_metrics(self):
        # ---------------------
        # System Health metrics
        # ---------------------
        self.reporter.add_float_measurement(
            MetricNames.PROCESS_CPU_PERCENT, "Amount of CPU usage by the process", "percentage",
        )
        self.reporter.add_integer_measurement(
            MetricNames.PROCESS_WORKING_SET, "All physical memory used by the process", "bytes",
        )
        self.reporter.add_integer_measurement(
            MetricNames.PROCESS_BYTES_IN_ALL_HEAPS,
            "All virtual memory used by the process",
            "bytes",
        )
        self.reporter.add_integer_measurement(
            MetricNames.PROCESS_PRIVATE_BYTES,
            "Amount of non-shared physical memory used by the process",
            "bytes",
        )
        self.reporter.add_integer_measurement(
            MetricNames.PROCESS_WORKING_SET_PRIVATE,
            "Amount of non-shared physical memory used by the process",
            "bytes",
        )

        # ----------------
        # test app metrics
        # ----------------
        self.reporter.add_integer_measurement(
            MetricNames.CLIENT_LIBRARY_COUNT_EXCEPTIONS,
            "Number of exceptions raised by the client library or libraries",
            "exception(s)",
        )

        # --------------------
        # SendMesssage metrics
        # --------------------
        self.reporter.add_integer_measurement(
            MetricNames.SEND_MESSAGE_COUNT_SENT,
            "Count of messages sent and ack'd by the transport",
            "message(s)",
        )
        self.reporter.add_integer_measurement(
            MetricNames.SEND_MESSAGE_COUNT_IN_BACKLOG,
            "Count of messages waiting to be sent",
            "message(s)",
        )
        self.reporter.add_integer_measurement(
            MetricNames.SEND_MESSAGE_COUNT_UNACKED,
            "Count of messages sent to iothub but not ack'd by the transport",
            "message(s)",
        )
        self.reporter.add_integer_measurement(
            MetricNames.SEND_MESSAGE_COUNT_NOT_RECEIVED,
            "Count of messages sent to iothub and acked by the transport, but receipt not (yet) verified via service sdk",
            "message(s)",
        )

        # -------------------
        # Receive c2d metrics
        # -------------------
        self.reporter.add_integer_measurement(
            MetricNames.RECEIVE_C2D_COUNT_RECEIVED,
            "Count of c2d messages received from the service",
            "message(s)",
        )
        self.reporter.add_integer_measurement(
            MetricNames.RECEIVE_C2D_COUNT_MISSING,
            "Count of c2d messages sent my the service but not received",
            "message(s)",
        )

        # -------------------------
        # Reported property metrics
        # -------------------------
        self.reporter.add_integer_measurement(
            MetricNames.REPORTED_PROPERTIES_COUNT_ADDED,
            "Count of reported properties added",
            "patches with add operation(s)",
        )
        self.reporter.add_integer_measurement(
            "reportedPropertiesCountAddedButNotVerifiedByServiceApp",
            "Count of reported properties added, but the add was not verified by the service app",
            "patches with add operation(s)",
        )
        self.reporter.add_integer_measurement(
            MetricNames.REPORTED_PROPERTIES_REMOVED,
            "Count of reported properties removed",
            "patches with remove operation(s)",
        )
        self.reporter.add_integer_measurement(
            "reportedPropertiesCountRemovedButNotVerifiedbyServiceApp",
            "Count of reported properties removed, but the remove was not verified by the service app",
            "patches with remove operations(s)",
        )

        # ---------------
        # Latency metrics
        # ---------------
        self.reporter.add_float_measurement(
            MetricNames.LATENCY_QUEUE_MESSAGE_TO_SEND,
            "Number of milliseconds between queueing a message and actually sending it",
            "milliseconds",
        )
        self.reporter.add_float_measurement(
            MetricNames.LATENCY_SEND_MESSAGE_TO_SERVICE_ACK,
            "Number of seconds between sending a message and receiving the serviceAck back from the service app",
            "seconds",
        )
        self.reporter.add_float_measurement(
            MetricNames.LATENCY_ADD_REPORTED_PROPERTY_TO_SERVICE_ACK,
            "Number of seconds between setting a reported property and receiving the serviceAck back from the service app",
            "seconds",
        )
        self.reporter.add_float_measurement(
            MetricNames.LATENCY_REMOVE_REPORTED_PROPERTY_TO_SERVICE_ACK,
            "Number of seconds between clearing a reported property and receiving the serviceAck back from the service app",
            "seconds",
        )
        self.reporter.add_float_measurement(
            MetricNames.LATENCY_BETWEEN_C2D,
            "number of seconds between test c2d messages from the service",
            "seconds",
        )

    def get_session_metrics(self):
        """
        Return metrics which describe the session the tests are running in
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed_time = now - self.metrics.run_start_utc

        props = {
            "runStartUtc": self.metrics.run_start_utc.isoformat(),
            "latestUpdateTimeUtc": now.isoformat(),
            "elapsedTime": str(elapsed_time),
            "runState": str(self.metrics.run_state),
            "exitReason": self.metrics.exit_reason,
        }
        return props

    def get_test_metrics(self):
        """
        Return metrics which describe the progress of the  different features being tested
        """
        sent = self.metrics.send_message_count_sent.get_count()
        received_by_service_app = (
            self.metrics.send_message_count_received_by_service_app.get_count()
        )

        props = {
            MetricNames.CLIENT_LIBRARY_COUNT_EXCEPTIONS: self.metrics.client_library_count_exceptions.get_count(),
            MetricNames.SEND_MESSAGE_COUNT_SENT: sent,
            MetricNames.SEND_MESSAGE_COUNT_IN_BACKLOG: self.outgoing_test_message_queue.qsize(),
            MetricNames.SEND_MESSAGE_COUNT_UNACKED: self.metrics.send_message_count_unacked.get_count(),
            MetricNames.SEND_MESSAGE_COUNT_NOT_RECEIVED: sent - received_by_service_app,
            MetricNames.RECEIVE_C2D_COUNT_RECEIVED: self.metrics.receive_c2d_count_received.get_count(),
            MetricNames.RECEIVE_C2D_COUNT_MISSING: self.out_of_order_message_tracker.get_missing_count(),
            MetricNames.REPORTED_PROPERTIES_COUNT_ADDED: self.metrics.reported_properties_count_added.get_count(),
            MetricNames.REPORTED_PROPERTIES_COUNT_ADDED_NOT_VERIFIED: self.metrics.reported_properties_count_added_not_verified.get_count(),
            MetricNames.REPORTED_PROPERTIES_REMOVED: self.metrics.reported_properties_count_removed.get_count(),
            MetricNames.REPORTED_PROPERTIES_REMOVED_NOT_VERIFIED: self.metrics.reported_properties_count_removed_not_verified.get_count(),
        }
        return props

    def update_initial_reported_properties(self):
        """
        Update reported properties at the start of a run
        """

        # First remove all old props (in case of schema change).  Also clears out old results.
        props = {Fields.Reported.THIEF: None}
        self.client.patch_twin_reported_properties(props)

        props = {
            Fields.Reported.THIEF: {
                Fields.Reported.SYSTEM_PROPERTIES: self.get_system_properties(
                    azure.iot.device.constant.VERSION
                ),
                Fields.Reported.SESSION_METRICS: self.get_session_metrics(),
                Fields.Reported.TEST_METRICS: self.get_test_metrics(),
                Fields.Reported.CONFIG: self.config,
            }
        }
        self.client.patch_twin_reported_properties(props)

    def create_message_from_dict(self, props):
        """
        helper function to create a message from a dict object
        """

        # Note: we're changing the dictionary that the user passed in.
        # This isn't the best idea, but it works and it saves us from deep copies
        if self.service_instance:
            props[Fields.Telemetry.THIEF][Fields.Telemetry.SERVICE_INSTANCE] = self.service_instance
        props[Fields.Telemetry.THIEF][Fields.Telemetry.RUN_ID] = run_id

        # This function only creates the message.  The caller needs to queue it up for sending.
        msg = Message(json.dumps(props))
        msg.content_type = Const.JSON_CONTENT_TYPE
        msg.content_encoding = Const.JSON_CONTENT_ENCODING

        msg.custom_properties[CustomPropertyNames.EVENT_DATE_TIME_UTC] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()

        return msg

    def create_message_from_dict_with_service_ack(
        self, props, on_service_ack_received, user_data=None
    ):
        """
        helper function to create a message from a dict and add service_ack
        properties.
        """
        service_ack_id = str(uuid.uuid4())

        # Note: we're changing the dictionary that the user passed in.
        # This isn't the best idea, but it works and it saves us from deep copies
        assert props[Fields.Telemetry.THIEF].get(Fields.Telemetry.CMD, None) is None
        props[Fields.Telemetry.THIEF][Fields.Telemetry.CMD] = Types.Message.SERVICE_ACK_REQUEST
        props[Fields.Telemetry.THIEF][Fields.Telemetry.SERVICE_ACK_ID] = service_ack_id

        with self.service_ack_list_lock:
            self.service_ack_wait_list[service_ack_id] = ServiceAckWaitInfo(
                on_service_ack_received=on_service_ack_received,
                service_ack_id=service_ack_id,
                service_ack_type=Types.ServiceAck.TELEMETRY_SERVICE_ACK,
                queue_epochtime=time.time(),
                user_data=user_data,
            )

        logger.info("Requesting service_ack for serviceAckId = {}".format(service_ack_id))
        msg = self.create_message_from_dict(props)
        msg.custom_properties[CustomPropertyNames.SERVICE_ACK_ID] = service_ack_id
        return msg

    def pairing_thread(self, worker_thread_info):
        """
        "pair" with a service app. This is necessary because we can have a single
        service app responsible for multiple device apps.  The pairing process works
        like this:

        1. Device sets reported properties in `properties/reported/thief/pairing` which indicates
            that it doesn't have a service app (by settign `serviceRunId` = None).
        2. An available service sets `properties/desired/thief/pairing/serviceRunId` to the service
            app's `runId` value
        3. The device sets `properties/reported/thief/pairing/serviceRunId` to the serivce app's
            `runId` value.

        Once the device starts sending telemetry with `thief/serviceRunId` set to the service app's
            `runId` value, the pairing is complete.
        """

        pairing_start_epochtime = 0
        pairing_last_request_epochtime = 0

        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            try:
                msg = self.incoming_pairing_message_queue.get(timeout=1)
            except queue.Empty:
                msg = None

            send_pairing_request = False
            if not msg and not self.service_instance:
                if not pairing_start_epochtime:
                    self.pairing_complete = False
                    pairing_start_epochtime = time.time()
                    send_pairing_request = True
                elif (time.time() - pairing_start_epochtime) > self.config[
                    Settings.PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS
                ]:
                    # if we're trying to pair and we haven't seen a response yet, we may need to
                    # re-send our request (by setting the desired property again), or it may be
                    # time to fail the pairing operation
                    raise Exception(
                        "No resopnse to pairing requests after trying for {} seconds".format(
                            self.config[Settings.PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS]
                        )
                    )
                elif (time.time() - pairing_last_request_epochtime) > self.config[
                    Settings.PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS
                ]:
                    logger.info("Pairing response timeout.  Requesting again")
                    send_pairing_request = True

            if send_pairing_request:
                # Set our reported properties to start a pairing operation or to try again if no
                # service has responded yet.
                logger.info("Starting pairing operation")
                pairing_last_request_epochtime = time.time()
                props = {
                    Fields.Reported.THIEF: {
                        Fields.Reported.PAIRING: {
                            Fields.Reported.Pairing.REQUESTED_SERVICE_POOL: requested_service_pool,
                            Fields.Reported.Pairing.SERVICE_INSTANCE: None,
                            Fields.Reported.Pairing.RUN_ID: run_id,
                        }
                    }
                }
                logger.info("Updating pairing reported props: {}".format(pprint.pformat(props)))
                event_logger.info(Events.SENDING_PAIRING_REQUEST)
                self.client.patch_twin_reported_properties(props)

            elif msg:
                logger.info("Received pairing desired props: {}".format(pprint.pformat(msg)))
                event_logger.info(Events.RECEIVED_PAIRING_RESPONSE)

                pairing = msg.get(Fields.Desired.THIEF, {}).get(Fields.Desired.PAIRING, {})
                received_run_id = pairing.get(Fields.Desired.Pairing.RUN_ID, None)
                received_service_instance = pairing.get(
                    Fields.Desired.Pairing.SERVICE_INSTANCE, None
                )

                if self.service_instance:
                    # It's possible that a second service app tried to pair with us after we
                    # already chose someone else.  Ignore this
                    logger.info("Already paired.  Ignoring.")

                elif not received_run_id or not received_service_instance:
                    # Or maybe something is wrong with the desired properties.  Probably a
                    # service app that goes by different rules. Ignoring it is better than
                    # crashing.
                    logger.info("deviceRunId and/or serviceRunId missing.  Ignoring.")

                elif received_run_id != run_id:
                    # Another strange case.  A service app is trying to pair with our device_id,
                    # but the `run_id` is wong.
                    logger.info(
                        "runId mismatch.  Ignoring. (received {}, expected {})".format(
                            received_run_id, run_id
                        )
                    )

                else:
                    # It looks like a service app has decided to pair with us.  Set reported
                    # properties to "select" this service instance as our partner.
                    logger.info(
                        "Service app {} claimed this device instance".format(
                            received_service_instance
                        )
                    )
                    self.service_instance = received_service_instance
                    self.pairing_complete = True
                    pairing_start_epochtime = None
                    pairing_last_request_epochtime = None

                    props = {
                        Fields.Reported.THIEF: {
                            Fields.Reported.PAIRING: {
                                Fields.Reported.Pairing.SERVICE_INSTANCE: self.service_instance,
                                Fields.Reported.Pairing.RUN_ID: run_id,
                            }
                        }
                    }
                    logger.info("Updating pairing reported props: {}".format(pprint.pformat(props)))
                    event_logger.info(Events.PAIRING_COMPLETE)
                    self.client.patch_twin_reported_properties(props)

                    self.on_pairing_complete()

    def start_pairing(self):
        """
        trigger the pairing process
        """
        self.service_instance = None

    def is_pairing_complete(self):
        """
        return True if the pairing process is complete
        """
        return self.service_instance and self.pairing_complete

    def on_pairing_complete(self):
        """
        Called when pairing is complete
        """
        logger.info("Pairing is complete.  Starting c2d")
        self.start_c2d_message_sending()

    def send_message_thread(self, worker_thread_info):
        """
        Thread which reads the telemetry queue and sends the telemetry.  Since send_message is
        blocking, and we want to overlap send_messsage calls, we create multiple
        send_message_thread instances so we can send multiple messages at the same time.

        The number of send_message_thread instances is the number of overlapped sent operations
        we can have
        """
        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            try:
                msg = self.outgoing_test_message_queue.get(timeout=1)
            except queue.Empty:
                msg = None
            if msg:
                service_ack_id = msg.custom_properties.get(CustomPropertyNames.SERVICE_ACK_ID, "")
                if service_ack_id:
                    with self.service_ack_list_lock:
                        wait_info = self.service_ack_wait_list[service_ack_id]
                    wait_info.send_epochtime = time.time()

                try:
                    self.metrics.send_message_count_unacked.increment()
                    self.client.send_message(msg)
                except Exception as e:
                    self.metrics.client_library_count_exceptions.increment()
                    logger.error("send_message raised {}".format(e), exc_info=True)
                    if (
                        self.metrics.client_library_count_exceptions.get_count()
                        > self.config[Settings.THIEF_ALLOWED_CLIENT_LIBRARY_EXCEPTION_COUNT]
                    ):
                        raise Exception(
                            "Client library exception count ({}) too high.".format(
                                self.metrics.client_library_count_exceptions.get_count()
                            )
                        )
                else:
                    self.metrics.send_message_count_sent.increment()
                finally:
                    self.metrics.send_message_count_unacked.decrement()

    def send_metrics_to_azure_monitor(self, props):
        """
        Send metrics to azure monitor, based on the reported properties that we probably just
        sent to the hub
        """
        # we don't record session_metrics to azure monitor because they're all about time and
        # there's no value to pushing things like "current time" as metrics
        with self.reporter_lock:
            self.reporter.set_metrics_from_dict(props[Fields.Reported.SYSTEM_HEALTH_METRICS])
            self.reporter.set_metrics_from_dict(props[Fields.Reported.TEST_METRICS])
            self.reporter.record()

    def test_send_message_thread(self, worker_thread_info):
        """
        Thread to continuously send d2c messages throughout the longhaul run.  This thread doesn't
        actually send messages becauase send_message is blocking and we want to overlap our send
        operations.  Instead, this thread adds the messsage to a queue, and relies on a
        send_message_thread instance to actually send the message.
        """

        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            if self.is_pairing_complete():
                props = {
                    Fields.Reported.THIEF: {
                        Fields.Reported.SESSION_METRICS: self.get_session_metrics(),
                        Fields.Reported.TEST_METRICS: self.get_test_metrics(),
                        Fields.Reported.SYSTEM_HEALTH_METRICS: self.get_system_health_telemetry(),
                    }
                }

                # push these same metrics to Azure Monitor
                self.send_metrics_to_azure_monitor(props[Fields.Reported.THIEF])

                def on_service_ack_received(service_ack_id, user_data):
                    logger.info("Received serviceAck with serviceAckId = {}".format(service_ack_id))
                    self.metrics.send_message_count_received_by_service_app.increment()

                    with self.service_ack_list_lock:
                        wait_info = self.service_ack_wait_list[service_ack_id]

                    with self.reporter_lock:
                        self.reporter.set_metrics_from_dict(
                            {
                                MetricNames.LATENCY_QUEUE_MESSAGE_TO_SEND: (
                                    wait_info.send_epochtime - wait_info.queue_epochtime
                                )
                                * 1000,
                                MetricNames.LATENCY_SEND_MESSAGE_TO_SERVICE_ACK: time.time()
                                - wait_info.send_epochtime,
                            }
                        )
                        self.reporter.record()

                # This function only queues the message.  A send_message_thread instance will pick
                # it up and send it.
                msg = self.create_message_from_dict_with_service_ack(
                    props=props, on_service_ack_received=on_service_ack_received
                )
                self.outgoing_test_message_queue.put(msg)

                # check backlog size for failure
                if (
                    self.outgoing_test_message_queue.qsize()
                    > self.config[Settings.SEND_MESSAGE_ALLOWED_FAILURE_COUNT]
                ):
                    raise Exception(
                        "Send message queue size {} is too big".format(
                            self.outgoing_test_message_qsize()
                        )
                    )
                # check for count of messages that failed to send (no PUBACK)
                if (
                    self.metrics.send_message_count_unacked.get_count()
                    > self.config[Settings.SEND_MESSAGE_ALLOWED_FAILURE_COUNT]
                ):
                    raise Exception(
                        "Un-acked message count of {} is too big".format(
                            self.metrics.send_message_count_unacked.get_count()
                        )
                    )
                # check the count of messages that were sent but not received
                not_received = (
                    self.metrics.send_message_count_sent.get_count()
                    - self.metrics.send_message_count_received_by_service_app.get_count()
                )
                if not_received > self.config[Settings.SEND_MESSAGE_ALLOWED_FAILURE_COUNT]:
                    raise Exception(
                        "Un-received message count of {} is too big".format(not_received)
                    )

                # sleep until we need to send again
                self.done.wait(1 / self.config[Settings.SEND_MESSAGE_OPERATIONS_PER_SECOND])

            else:
                # pairing is not complete
                time.sleep(1)

    def update_thief_properties_thread(self, worker_thread_info):
        """
        Thread which occasionally sends reported properties with information about how the
        test is progressing
        """
        done = False

        while not done:
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            # setting this at the begining and checking at the end guarantees one last update
            # before the thread dies
            if self.done.isSet():
                done = True

            props = {
                Fields.Reported.THIEF: {
                    Fields.Reported.SESSION_METRICS: self.get_session_metrics(),
                    Fields.Reported.TEST_METRICS: self.get_test_metrics(),
                    # systemHealthMetrics don't go into reported properties
                }
            }

            logger.info("Updating thief props: {}".format(pprint.pformat(props)))
            self.client.patch_twin_reported_properties(props)

            self.done.wait(self.config[Settings.THIEF_PROPERTY_UPDATE_INTERVAL_IN_SECONDS])

    def wait_for_desired_properties_thread(self, worker_thread_info):
        """
        Thread which waits for desired property patches and puts them into
        queues for other threads to handle
        """
        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            props = self.client.receive_twin_desired_properties_patch(timeout=30)
            if props:
                # props that have the pairing structure go to `incoming_pairing_message_queue`
                if props.get(Fields.Desired.THIEF, {}).get(Fields.Desired.PAIRING, {}):
                    self.incoming_pairing_message_queue.put(props)

                # Other props get dropped.  Eventually we'll use this to test desired properties.
                # self.incoming_desired_property_patch_queue.put(props)

    def dispatch_incoming_message_thread(self, worker_thread_info):
        """
        Thread which continuously receives c2d messages throughout the test run.  This
        thread does minimal processing for each c2d.  If anything complex needs to happen as a
        result of a c2d message, this thread puts the message into a queue for some other thread
        to pick up.
        """
        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            msg = self.client.receive_message(timeout=30)

            if msg:
                obj = json.loads(msg.data.decode())
                thief = obj.get(Fields.Telemetry.THIEF)

                if (
                    thief
                    and thief[Fields.C2d.RUN_ID] == run_id
                    and thief[Fields.C2d.SERVICE_INSTANCE] == self.service_instance
                ):
                    # We only inspect messages that have `thief/deviceRunId` and `thief/serviceRunId` set to the expected values
                    cmd = thief[Fields.C2d.CMD]
                    if cmd == Types.Message.SERVICE_ACK_RESPONSE:
                        # If this is a service_ack response, we put it into `incoming_service_ack_response_queue`
                        # for another thread to handle.
                        logger.info(
                            "Received {} message with {}".format(
                                cmd, thief[Fields.C2d.SERVICE_ACKS]
                            )
                        )
                        self.incoming_service_ack_response_queue.put(msg)

                    elif cmd == Types.Message.TEST_C2D:
                        # If this is a test C2D messages, we put it into `incoming_test_c2d_message_queue`
                        # for another thread to handle.
                        logger.info(
                            "Received {} message with index {}".format(
                                cmd, thief[Fields.C2d.TEST_C2D_MESSAGE_INDEX]
                            )
                        )
                        self.incoming_test_c2d_message_queue.put(msg)

                    else:
                        logger.warning("Unknown command received: {}".format(obj))

                else:
                    logger.warning("C2D received, but it's not for us: {}".format(obj))

    def handle_service_ack_response_thread(self, worker_thread_info):
        """
        Thread which handles incoming service_ack responses.  This is where we go through the list
        of `serviceAckId` values that we received and call the appropriate callbacks to indicate that
        the service has responded.
        """

        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            try:
                msg = self.incoming_service_ack_response_queue.get(timeout=1)
            except queue.Empty:
                msg = None

            if msg:
                arrivals = []
                thief = json.loads(msg.data.decode())[Fields.Telemetry.THIEF]

                with self.service_ack_list_lock:
                    for service_ack_id in thief[Fields.C2d.SERVICE_ACKS]:

                        if service_ack_id in self.service_ack_wait_list:
                            # we've received a service_ack.  Don't call back here because we're holding
                            # service_ack_list_lock.  Instead, add to a list and call back when we're
                            # not holding the lock.
                            arrivals.append(self.service_ack_wait_list[service_ack_id])
                        else:
                            logger.warning(
                                "Received unkonwn serviceAckId: {}:".format(service_ack_id)
                            )

                for arrival in arrivals:
                    arrival.on_service_ack_received(arrival.service_ack_id, arrival.user_data)
                    # remove this from our list _after_ we call on_service_ack_received
                    with self.service_ack_list_lock:
                        if arrival.service_ack_id in self.service_ack_wait_list:
                            del self.service_ack_wait_list[arrival.service_ack_id]

    def start_c2d_message_sending(self):
        """
        set a reported property to start c2d messages flowing
        """
        # TODO: add a timeout here, make sure the messages are correct, and make sure messages actually flow

        props = {
            Fields.Reported.THIEF: {
                Fields.Reported.TEST_CONTROL: {
                    Fields.Reported.TestControl.C2D: {
                        Fields.Reported.TestControl.C2d.SEND: True,
                        Fields.Reported.TestControl.C2d.MESSAGE_INTERVAL_IN_SECONDS: self.config[
                            Settings.RECEIVE_C2D_INTERVAL_IN_SECONDS
                        ],
                    }
                }
            }
        }

        logger.info("Enabling C2D message testing: {}".format(props))
        self.client.patch_twin_reported_properties(props)

    def handle_incoming_test_c2d_messages_thread(self, worker_thread_info):
        """
        Thread which handles c2d messages that were sent by the service app for the purpose of
        testing c2d
        """
        last_message_epochtime = 0

        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            try:
                msg = self.incoming_test_c2d_message_queue.get(timeout=1)
            except queue.Empty:
                msg = None

            if msg:
                thief = json.loads(msg.data.decode())[Fields.C2d.THIEF]
                self.metrics.receive_c2d_count_received.increment()
                self.out_of_order_message_tracker.add_message(
                    thief.get(Fields.C2d.TEST_C2D_MESSAGE_INDEX)
                )

                now = time.time()
                if last_message_epochtime:
                    with self.reporter_lock:
                        self.reporter.set_metrics_from_dict(
                            {MetricNames.LATENCY_BETWEEN_C2D: now - last_message_epochtime}
                        )
                        self.reporter.record()
                last_message_epochtime = now

                if (
                    self.out_of_order_message_tracker.get_missing_count()
                    > self.config[Settings.RECEIVE_C2D_ALLOWED_MISSING_MESSAGE_COUNT]
                ):
                    raise Exception(
                        "Missing message count ({}) is too high".format(
                            self.out_of_order_message_tracker.get_missing_count()
                        )
                    )

    def test_reported_properties_threads(self, worker_thread_info):
        """
        Thread to test reported properties.  It does this by setting properties inside
        `properties/reported/thief/testContent/reportedPropertyTest`.  Each property has
        a `addServiceAckId` value and a `removeServiceAckId` value.  When  the service sees the
        property added, it sends the `addServiceAckId` to the device.  When the service sees the
        property removed, it sends the `removeServiceAckid` to the device. This way the device
        can add a property, verify that it was added, then remove it and verify that it was removed.
        """

        property_index = 1

        while not self.done.isSet():
            worker_thread_info.watchdog_epochtime = time.time()
            if self.is_paused():
                time.sleep(1)
                continue

            if self.is_pairing_complete():
                add_service_ack_id = str(uuid.uuid4())
                remove_service_ack_id = str(uuid.uuid4())

                property_name = "prop_{}".format(property_index)
                property_value = {
                    Fields.Reported.TestContent.ReportedPropertyTest.ADD_SERVICE_ACK_ID: add_service_ack_id,
                    Fields.Reported.TestContent.ReportedPropertyTest.REMOVE_SERVICE_ACK_ID: remove_service_ack_id,
                }

                def on_property_added(service_ack_id, user_data):
                    self.metrics.reported_properties_count_added_not_verified.decrement()
                    (prop_name, add_ack_id, remove_ack_id) = user_data
                    logger.info("Add of reported property {} verified by service".format(prop_name))

                    with self.service_ack_list_lock:
                        add_wait_info = self.service_ack_wait_list[add_ack_id]
                        self.service_ack_wait_list[remove_ack_id] = ServiceAckWaitInfo(
                            on_service_ack_received=on_property_removed,
                            service_ack_id=remove_ack_id,
                            send_epochtime=time.time(),
                            service_ack_type=Types.ServiceAck.REMOVE_REPORTED_PROPERTY_SERVICE_ACK,
                            user_data=user_data,
                        )

                    with self.reporter_lock:
                        self.reporter.set_metrics_from_dict(
                            {
                                MetricNames.LATENCY_ADD_REPORTED_PROPERTY_TO_SERVICE_ACK: time.time()
                                - add_wait_info.send_epochtime
                            }
                        )
                        self.reporter.record()

                    reported_properties = {
                        Fields.Reported.THIEF: {
                            Fields.Reported.TEST_CONTENT: {
                                Fields.Reported.TestContent.REPORTED_PROPERTY_TEST: {
                                    prop_name: None
                                }
                            }
                        }
                    }
                    logger.info("Removing test property {}".format(prop_name))
                    self.client.patch_twin_reported_properties(reported_properties)
                    self.metrics.reported_properties_count_removed.increment()
                    self.metrics.reported_properties_count_removed_not_verified.increment()

                def on_property_removed(service_ack_id, user_data):
                    self.metrics.reported_properties_count_removed_not_verified.decrement()
                    (prop_name, add_ack_id, remove_ack_id) = user_data
                    logger.info(
                        "Remove of reported property {} verified by service".format(prop_name)
                    )

                    with self.service_ack_list_lock:
                        remove_wait_info = self.service_ack_wait_list[remove_ack_id]
                    with self.reporter_lock:
                        self.reporter.set_metrics_from_dict(
                            {
                                MetricNames.LATENCY_REMOVE_REPORTED_PROPERTY_TO_SERVICE_ACK: time.time()
                                - remove_wait_info.send_epochtime
                            }
                        )
                        self.reporter.record()

                with self.service_ack_list_lock:
                    self.service_ack_wait_list[add_service_ack_id] = ServiceAckWaitInfo(
                        on_service_ack_received=on_property_added,
                        service_ack_id=add_service_ack_id,
                        send_epochtime=time.time(),
                        service_ack_type=Types.ServiceAck.ADD_REPORTED_PROPERTY_SERVICE_ACK,
                        user_data=(property_name, add_service_ack_id, remove_service_ack_id),
                    )

                reported_properties = {
                    Fields.Reported.THIEF: {
                        Fields.Reported.TEST_CONTENT: {
                            Fields.Reported.TestContent.REPORTED_PROPERTY_TEST: {
                                property_name: property_value
                            }
                        }
                    }
                }
                logger.info("Adding test property {}".format(property_name))
                self.client.patch_twin_reported_properties(reported_properties)
                self.metrics.reported_properties_count_added.increment()
                self.metrics.reported_properties_count_added_not_verified.increment()

                property_index += 1

                failure_count = (
                    self.metrics.reported_properties_count_added_not_verified.get_count()
                    + self.metrics.reported_properties_count_removed_not_verified.get_count()
                )
                if (
                    failure_count
                    > self.config[Settings.REPORTED_PROPERTIES_UPDATE_ALLOWED_FAILURE_COUNT]
                ):
                    raise Exception(
                        "Twin reported property add+remove failure count {} is too big".format(
                            failure_count
                        )
                    )

            time.sleep(self.config[Settings.REPORTED_PROPERTIES_UPDATE_INTERVAL_IN_SECONDS])

    def main(self):

        self.metrics.run_start_utc = datetime.datetime.now(datetime.timezone.utc)
        self.metrics.run_state = app_base.RUNNING
        logger.info("Starting at {}".format(self.metrics.run_start_utc))

        # Create our client and push initial properties
        self.client, self.hub, self.device_id = dps.create_device_client_using_dps_group_key(
            provisioning_host=provisioning_host,
            registration_id=registration_id,
            id_scope=id_scope,
            group_symmetric_key=group_symmetric_key,
        )
        azure_monitor.add_logging_properties(hub=self.hub, device_id=self.device_id)
        self.update_initial_reported_properties()

        event_logger.info(Events.STARTING_RUN)

        # pair with a service app instance
        self.start_pairing()

        # Make a list of threads to launch
        worker_thread_infos = [
            app_base.WorkerThreadInfo(
                self.dispatch_incoming_message_thread, "dispatch_incoming_message_thread"
            ),
            app_base.WorkerThreadInfo(
                self.update_thief_properties_thread, "update_thief_properties_thread"
            ),
            app_base.WorkerThreadInfo(
                self.wait_for_desired_properties_thread, "wait_for_desired_properties_thread"
            ),
            app_base.WorkerThreadInfo(
                self.handle_service_ack_response_thread, "handle_service_ack_response_thread"
            ),
            app_base.WorkerThreadInfo(self.test_send_message_thread, "test_send_message_thread"),
            app_base.WorkerThreadInfo(
                self.handle_incoming_test_c2d_messages_thread,
                "handle_incoming_test_c2d_messages_thread",
            ),
            app_base.WorkerThreadInfo(self.pairing_thread, "pairing_thread"),
            app_base.WorkerThreadInfo(
                self.test_reported_properties_threads, "test_reported_properties_threads"
            ),
        ]
        for i in range(0, self.config[Settings.SEND_MESSAGE_THREAD_COUNT]):
            worker_thread_infos.append(
                app_base.WorkerThreadInfo(
                    self.send_message_thread, "send_message_thread #{}".format(i),
                )
            )

        # TODO: add virtual function that can be used to wait for all messages to arrive after test is done

        self.run_threads(worker_thread_infos)

        logger.info("Exiting main at {}".format(datetime.datetime.utcnow()))
        event_logger.info(Events.ENDING_RUN)

    def disconnect(self):
        self.client.disconnect()


if __name__ == "__main__":
    try:
        DeviceApp().main()
    except Exception as e:
        logger.error("App shutdown exception: {}".format(str(e)), exc_info=True)
        raise
    finally:
        # Flush azure monitor telemetry
        logging.shutdown()
