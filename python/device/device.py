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
import sys
import collections
import platform
import random
from executor import BetterThreadPoolExecutor, reset_watchdog, dump_active_stacks
import dps
import queue
import faulthandler
import gc
from azure.iot.device import Message, MethodResponse
import azure.iot.device.constant
from measurement import ThreadSafeCounter
from system_health_telemetry import SystemHealthTelemetry
import azure_monitor
from azure_monitor_metrics import MetricsReporter
from thief_constants import (
    Const,
    Fields,
    Commands,
    Events,
    Metrics,
    Settings,
    CustomDimensions,
    MethodNames,
    RunStates,
    SystemProperties,
)
from running_operation_list import RunningOperationList

faulthandler.enable()

# use os.environ[] for required environment variables
provisioning_host = os.environ["THIEF_DEVICE_PROVISIONING_HOST"]
id_scope = os.environ["THIEF_DEVICE_ID_SCOPE"]
group_symmetric_key = os.environ["THIEF_DEVICE_GROUP_SYMMETRIC_KEY"]
registration_id = os.environ["THIEF_DEVICE_ID"]
requested_service_pool = os.environ["THIEF_REQUESTED_SERVICE_POOL"]

# Optional environment variables.
# run_reason can be an environment variable or is can be passed on the command line.
run_reason = os.getenv("THIEF_RUN_REASON")
# run_id can be an environment variable or it can be automatically generated
run_id = os.getenv("THIEF_RUN_ID")
if not run_id:
    run_id = str(uuid.uuid4())

# set default logging which will only go to the console

logging.basicConfig(level=logging.WARNING)
# logging.getLogger("paho").setLevel(level=logging.DEBUG)
logging.getLogger("thief").setLevel(level=logging.INFO)
# logging.getLogger("azure.iot").setLevel(level=logging.INFO)
logger = logging.getLogger("thief.{}".format(__name__))

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


TestMethod = collections.namedtuple(
    "TestMethod", "method_name expected_status_code include_payload"
)


class ThiefFatalException(Exception):
    pass


def _get_os_release_based_on_user_agent_standard():
    return "({python_runtime};{os_type} {os_release};{architecture})".format(
        python_runtime=platform.python_version(),
        os_type=platform.system(),
        os_release=platform.version(),
        architecture=platform.machine(),
    )


def custom_props(extra_props):
    """
    helper function for adding customDimensions to logger calls at execution time
    """
    return {"custom_dimensions": extra_props}


class CustomPropertyNames(object):
    EVENT_DATE_TIME_UTC = "eventDateTimeUtc"
    SERVICE_ACK_ID = "serviceAckid"


class DeviceRunMetrics(object):
    """
    Object we use internally to keep track of how a the entire test is performing.
    """

    def __init__(self):
        self.run_start_utc = None
        self.run_state = RunStates.WAITING
        self.exit_reason = None

        self.exception_count = ThreadSafeCounter()

        self.send_message_count_sent = ThreadSafeCounter()
        self.send_message_count_verified = ThreadSafeCounter()
        self.send_message_count_timed_out = ThreadSafeCounter()
        self.receive_c2d_count_received = ThreadSafeCounter()
        self.receive_c2d_count_timed_out = ThreadSafeCounter()

        self.reported_properties_count_added = ThreadSafeCounter()
        self.reported_properties_count_removed = ThreadSafeCounter()
        self.reported_properties_count_timed_out = ThreadSafeCounter()

        self.get_twin_count_succeeded = ThreadSafeCounter()
        self.get_twin_count_timed_out = ThreadSafeCounter()

        self.desired_property_patch_count_received = ThreadSafeCounter()
        self.desired_property_patch_count_timed_out = ThreadSafeCounter()

        self.method_invoke_count_request_received = ThreadSafeCounter()
        self.method_invoke_count_request_timed_out = ThreadSafeCounter()


"""
Object we use internally to keep track of how the entire test is configured.
Currently hardcoded. Later, this will come from desired properties.
"""
device_run_config = {
    Settings.MAX_RUN_DURATION_IN_SECONDS: 2 * 60,
    Settings.ALLOWED_EXCEPTION_COUNT: 10,
    Settings.INTER_TEST_DELAY_INTERVAL_IN_SECONDS: 1,
    Settings.OPERATION_TIMEOUT_IN_SECONDS: 60,
    Settings.OPERATION_TIMEOUT_ALLOWED_FAILURE_COUNT: 10,
    Settings.PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS: 900,
    Settings.PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS: 30,
    Settings.SEND_MESSAGE_OPERATIONS_PER_SECOND: 10,
    Settings.MQTT_KEEP_ALIVE_INTERVAL: 20,
    Settings.SAS_TOKEN_RENEWAL_INTERVAL: 600,
    Settings.MAX_TEST_SEND_THREADS: 128,
    Settings.MAX_TEST_RECEIVE_THREADS: 10,
}


class DeviceApp(object):
    """
    Main application object
    """

    def __init__(self):
        global device_run_config
        super(DeviceApp, self).__init__()

        self.config = device_run_config
        self.outgoing_executor = BetterThreadPoolExecutor(
            max_workers=self.config[Settings.MAX_TEST_SEND_THREADS]
        )
        self.incoming_executor = BetterThreadPoolExecutor(
            max_workers=self.config[Settings.MAX_TEST_RECEIVE_THREADS]
        )
        self.done = threading.Event()
        self.client = None
        self.hub = None
        self.device_id = None
        self.metrics = DeviceRunMetrics()
        self.service_instance_id = None
        self.system_health_telemetry = SystemHealthTelemetry()
        # for service_acks
        self.running_operation_list = RunningOperationList()
        # for metrics
        self.reporter_lock = threading.Lock()
        self.reporter = MetricsReporter()
        self._configure_azure_monitor_metrics()
        # for pairing
        self.incoming_pairing_message_queue = queue.Queue()
        # for twin
        self.reported_property_index = 1
        self.incoming_desired_property_patch_queue = queue.Queue()

    def _configure_azure_monitor_metrics(self):
        # ---------------------
        # System Health metrics
        # ---------------------
        self.reporter.add_float_measurement(
            Metrics.PROCESS_CPU_PERCENT,
            "CPU use for the device app, as a percentage of all cores",
            "percentage",
        )
        self.reporter.add_integer_measurement(
            Metrics.PROCESS_WORKING_SET_BYTES,
            "Working set for the device app, includes shared and private, read-only and writeable memory",
            "bytes",
        )
        self.reporter.add_integer_measurement(
            Metrics.PROCESS_WORKING_SET_PRIVATE_BYTES,
            "Amount of private data used by the process",
            "bytes",
        )
        self.reporter.add_integer_measurement(
            Metrics.PROCESS_GARBAGE_COLLECTION_OBJECTS,
            "Number of active objects being managed by the garbage collector",
            "objects",
        )
        self.reporter.add_integer_measurement(
            Metrics.PROCESS_SDK_THREADS,
            "number of threads being used by the current SDK",
            "threads",
        )
        self.reporter.add_integer_measurement(
            Metrics.TEST_APP_ACTIVE_RECEIVE_THREADS,
            "number of active threads in the test app receive threadpool",
            "threads",
        )
        self.reporter.add_integer_measurement(
            Metrics.TEST_APP_ACTIVE_SEND_THREADS,
            "number of active threads in the test app send threadpool",
            "threads",
        )

        # ----------------
        # test app metrics
        # ----------------
        self.reporter.add_integer_measurement(
            Metrics.EXCEPTION_COUNT,
            "Number of (non-fatal) exceptions raised by the client library or test code",
            "exception count",
        )

        # --------------------
        # SendMesssage metrics
        # --------------------
        self.reporter.add_integer_measurement(
            Metrics.SEND_MESSAGE_COUNT_SENT, "Number of telemetry messages sent", "messages",
        )
        self.reporter.add_integer_measurement(
            Metrics.SEND_MESSAGE_COUNT_VERIFIED,
            "Number of telemetry messages sent and verified by the service",
            "messages",
        )
        self.reporter.add_integer_measurement(
            Metrics.SEND_MESSAGE_COUNT_TIMED_OUT,
            "Number of telemetry messages that timed out with no response from the service",
            "messages",
        )

        # -------------------
        # Receive c2d metrics
        # -------------------
        self.reporter.add_integer_measurement(
            Metrics.RECEIVE_C2D_COUNT_RECEIVED, "Number of c2d messages received", "messages",
        )
        self.reporter.add_integer_measurement(
            Metrics.RECEIVE_C2D_COUNT_TIMED_OUT,
            "Number of c2d messages not received in time",
            "messages",
        )

        # -------------------------
        # Reported property metrics
        # -------------------------
        self.reporter.add_integer_measurement(
            Metrics.REPORTED_PROPERTIES_COUNT_ADDED,
            "Number of reported properties which have been added",
            "patches",
        )
        self.reporter.add_integer_measurement(
            Metrics.REPORTED_PROPERTIES_COUNT_REMOVED,
            "Number of reported properties which have been removed",
            "patches",
        )
        self.reporter.add_integer_measurement(
            Metrics.REPORTED_PROPERTIES_COUNT_TIMED_OUT,
            "Number of reported property add & remove operations that timed out",
            "patches",
        )

        # ----------------
        # Get-twin metrics
        # ----------------
        self.reporter.add_integer_measurement(
            Metrics.GET_TWIN_COUNT_SUCCEEDED,
            "Number of times get_twin successfully verified a property update",
            "calls",
        )
        self.reporter.add_integer_measurement(
            Metrics.GET_TWIN_COUNT_TIMED_OUT,
            "Number of times get_twin was unable to verify a property update",
            "calls",
        )

        # ------------------------------
        # desired property patch metrics
        # ------------------------------
        self.reporter.add_integer_measurement(
            Metrics.DESIRED_PROPERTY_PATCH_COUNT_RECEIVED,
            "Count of desired property patches that were successfully received",
            "patches",
        )
        self.reporter.add_integer_measurement(
            Metrics.DESIRED_PROPERTY_PATCH_COUNT_TIMED_OUT,
            "Count of desired property patches that were not received",
            "patches",
        )

        # ---------------------
        # method invoke metrics
        # ---------------------
        self.reporter.add_integer_measurement(
            Metrics.METHOD_INVOKE_COUNT_REQUEST_RECEIVED,
            "Number of method invoke requests received",
            "invokes",
        )
        self.reporter.add_integer_measurement(
            Metrics.METHOD_INVOKE_COUNT_REQUEST_TIMED_OUT,
            "Number of method invoke requests timed out",
            "invokes",
        )

        # ---------------
        # Latency metrics
        # ---------------
        self.reporter.add_float_measurement(
            Metrics.LATENCY_QUEUE_MESSAGE_TO_SEND,
            "Number of milliseconds between queueing a telemetry message and actually sending it",
            "milliseconds",
        )

    def get_session_metrics(self):
        """
        Return metrics which describe the session the tests are running in
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed_time = now - self.metrics.run_start_utc

        props = {
            Fields.RUN_START_UTC: self.metrics.run_start_utc.isoformat(),
            Fields.LATEST_UPDATE_TIME_UTC: now.isoformat(),
            Fields.ELAPSED_TIME: str(elapsed_time),
            Fields.RUN_STATE: str(self.metrics.run_state),
            Fields.EXIT_REASON: self.metrics.exit_reason,
        }
        return props

    def get_test_metrics(self):
        """
        Return metrics which describe the progress of the  different features being tested
        """

        props = {
            Metrics.EXCEPTION_COUNT: self.metrics.exception_count.get_count(),
            Metrics.SEND_MESSAGE_COUNT_SENT: self.metrics.send_message_count_sent.get_count(),
            Metrics.SEND_MESSAGE_COUNT_VERIFIED: self.metrics.send_message_count_verified.get_count(),
            Metrics.SEND_MESSAGE_COUNT_TIMED_OUT: self.metrics.send_message_count_timed_out.get_count(),
            Metrics.RECEIVE_C2D_COUNT_RECEIVED: self.metrics.receive_c2d_count_received.get_count(),
            Metrics.RECEIVE_C2D_COUNT_TIMED_OUT: self.metrics.receive_c2d_count_timed_out.get_count(),
            Metrics.REPORTED_PROPERTIES_COUNT_ADDED: self.metrics.reported_properties_count_added.get_count(),
            Metrics.REPORTED_PROPERTIES_COUNT_REMOVED: self.metrics.reported_properties_count_removed.get_count(),
            Metrics.REPORTED_PROPERTIES_COUNT_TIMED_OUT: self.metrics.reported_properties_count_timed_out.get_count(),
            Metrics.GET_TWIN_COUNT_SUCCEEDED: self.metrics.get_twin_count_succeeded.get_count(),
            Metrics.GET_TWIN_COUNT_TIMED_OUT: self.metrics.get_twin_count_timed_out.get_count(),
            Metrics.DESIRED_PROPERTY_PATCH_COUNT_RECEIVED: self.metrics.desired_property_patch_count_received.get_count(),
            Metrics.DESIRED_PROPERTY_PATCH_COUNT_TIMED_OUT: self.metrics.desired_property_patch_count_timed_out.get_count(),
            Metrics.METHOD_INVOKE_COUNT_REQUEST_RECEIVED: self.metrics.method_invoke_count_request_received.get_count(),
            Metrics.METHOD_INVOKE_COUNT_REQUEST_TIMED_OUT: self.metrics.method_invoke_count_request_timed_out.get_count(),
        }
        return props

    def check_failure_counts(self):
        """
        Check all failure counts and raise an exception if they exceeded the allowed count
        """
        if self.metrics.exception_count.get_count() > self.config[Settings.ALLOWED_EXCEPTION_COUNT]:
            raise Exception(
                "Exception count ({}) too high.".format(self.metrics.exception_count.get_count())
            )

        timeout_count = (
            self.metrics.send_message_count_timed_out.get_count()
            + self.metrics.receive_c2d_count_timed_out.get_count()
            + self.metrics.reported_properties_count_timed_out.get_count()
            + self.metrics.get_twin_count_timed_out.get_count()
            + self.metrics.desired_property_patch_count_timed_out.get_count()
            + self.metrics.method_invoke_count_request_timed_out.get_count()
        )
        if timeout_count > self.config[Settings.OPERATION_TIMEOUT_ALLOWED_FAILURE_COUNT]:
            raise Exception("Timeout count ({}) too high.".format(timeout_count))

    def update_initial_reported_properties(self):
        """
        Update reported properties at the start of a run
        """

        # First remove all old props (in case of schema change).  Also clears out old results.
        props = {Fields.THIEF: None}
        self.client.patch_twin_reported_properties(props)

        props = {
            Fields.THIEF: {
                Fields.SYSTEM_PROPERTIES: self.get_system_properties(),
                Fields.SESSION_METRICS: self.get_session_metrics(),
                Fields.TEST_METRICS: self.get_test_metrics(),
                Fields.CONFIG: self.config,
            }
        }
        self.client.patch_twin_reported_properties(props)

    def get_system_properties(self):
        return {
            SystemProperties.LANGUAGE: "python",
            SystemProperties.LANGUAGE_VERSION: platform.python_version(),
            SystemProperties.SDK_VERSION: azure.iot.device.constant.VERSION,
            SystemProperties.SDK_GITHUB_REPO: os.getenv("THIEF_SDK_GIT_REPO"),
            SystemProperties.SDK_GITHUB_BRANCH: os.getenv("THIEF_SDK_GIT_BRANCH"),
            SystemProperties.SDK_GITHUB_COMMIT: os.getenv("THIEF_SDK_GIT_COMMIT"),
            SystemProperties.OS_TYPE: platform.system(),
            SystemProperties.OS_RELEASE: _get_os_release_based_on_user_agent_standard(),
        }

    def get_system_health_telemetry(self):
        props = {
            Metrics.PROCESS_CPU_PERCENT: self.system_health_telemetry.process_cpu_percent,
            Metrics.PROCESS_WORKING_SET_BYTES: self.system_health_telemetry.process_working_set_bytes,
            Metrics.PROCESS_WORKING_SET_PRIVATE_BYTES: self.system_health_telemetry.process_working_set_private_bytes,
            Metrics.PROCESS_GARBAGE_COLLECTION_OBJECTS: len(gc.get_objects()),
            Metrics.PROCESS_SDK_THREADS: threading.active_count()
            - len(self.outgoing_executor.all_threads)
            - len(self.incoming_executor.all_threads),
            Metrics.TEST_APP_ACTIVE_RECEIVE_THREADS: len(
                list(self.incoming_executor.active_threads)
            ),
            Metrics.TEST_APP_ACTIVE_SEND_THREADS: len(list(self.outgoing_executor.active_threads)),
        }
        return props

    def create_message_from_dict(self, payload):
        """
        helper function to create a message from a dict object
        """

        # Note: we're changing the dictionary that the user passed in.
        # This isn't the best idea, but it works and it saves us from deep copies
        if self.service_instance_id:
            payload[Fields.THIEF][Fields.SERVICE_INSTANCE_ID] = self.service_instance_id
        payload[Fields.THIEF][Fields.RUN_ID] = run_id

        # This function only creates the message.  The caller needs to queue it up for sending.
        msg = Message(json.dumps(payload))
        msg.content_type = Const.JSON_CONTENT_TYPE
        msg.content_encoding = Const.JSON_CONTENT_ENCODING

        msg.custom_properties[CustomPropertyNames.EVENT_DATE_TIME_UTC] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()

        return msg

    def pair_with_service(self):
        """
        "pair" with a service app. This is necessary because we can have a single
        service app responsible for multiple device apps.  The pairing process works
        like this:

        1. Device sets reported properties in `properties/reported/thief/pairing` which indicates
            that it doesn't have a service app (by settign `serviceInstanceId` = None).
        2. An available service sets `properties/desired/thief/pairing/serviceInstanceId` to the service
            app's `runId` value
        3. The device sets `properties/reported/thief/pairing/serviceInstanceId` to the service app's
            `runId` value.

        Once the device starts sending telemetry with `thief/serviceInstanceId` set to the service app's
            `runId` value, the pairing is complete.
        """

        pairing_start_time = time.time()

        while (time.time() - pairing_start_time) < self.config[
            Settings.PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS
        ]:
            props = {
                Fields.THIEF: {
                    Fields.PAIRING: {
                        Fields.REQUESTED_SERVICE_POOL: requested_service_pool,
                        Fields.SERVICE_INSTANCE_ID: None,
                        Fields.RUN_ID: run_id,
                    }
                }
            }
            logger.info("Updating pairing reported props: {}".format(pprint.pformat(props)))
            event_logger.info(Events.SENDING_PAIRING_REQUEST)
            self.client.patch_twin_reported_properties(props)

            try:
                msg = self.incoming_pairing_message_queue.get(
                    timeout=self.config[Settings.PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS]
                )
            except queue.Empty:
                msg = None

            if not msg:
                logger.info("No pairing msg.  looping")

            if msg:
                logger.info("Received pairing desired props: {}".format(pprint.pformat(msg)))
                event_logger.info(Events.RECEIVED_PAIRING_RESPONSE)

                pairing = msg.get(Fields.THIEF, {}).get(Fields.PAIRING, {})
                received_run_id = pairing.get(Fields.RUN_ID, None)
                received_service_instance_id = pairing.get(Fields.SERVICE_INSTANCE_ID, None)

                if received_run_id == run_id and received_service_instance_id:
                    azure_monitor.add_logging_properties(
                        service_instance_id=received_service_instance_id
                    )

                    # It looks like a service app has decided to pair with us.  Set reported
                    # properties to "select" this service instance as our partner.
                    logger.info(
                        "Service app {} claimed this device instance".format(
                            received_service_instance_id
                        )
                    )
                    self.service_instance_id = received_service_instance_id

                    props = {
                        Fields.THIEF: {
                            Fields.PAIRING: {
                                Fields.SERVICE_INSTANCE_ID: self.service_instance_id,
                                Fields.RUN_ID: run_id,
                            }
                        }
                    }
                    logger.info("Updating pairing reported props: {}".format(pprint.pformat(props)))
                    event_logger.info(Events.PAIRING_COMPLETE)
                    self.client.patch_twin_reported_properties(props)

                    return

        raise Exception("Pairing timed out")

    def send_metrics_to_azure_monitor(self, props):
        """
        Send metrics to azure monitor, based on the reported properties that we probably just
        sent to the hub
        """
        # We don't record session_metrics to Azure Monitor because the session metrics are
        # recording things like "start time" and "elapsed time" which are already available
        # in Azure Monitor in other forms.
        with self.reporter_lock:
            self.reporter.set_metrics_from_dict(props[Fields.SYSTEM_HEALTH_METRICS])
            self.reporter.set_metrics_from_dict(props[Fields.TEST_METRICS])
            self.reporter.record()

    def test_send_message_thread(self):
        """
        Thread to continuously send d2c messages throughout the longhaul run.  This thread doesn't
        actually send messages because send_message is blocking and we want to overlap our send
        operations.  Instead, this thread creates new transient threads that actually send the
        message.
        """

        def send_message():
            running_op = self.running_operation_list.make_event_based_operation()

            payload = {
                Fields.THIEF: {
                    Fields.CMD: Commands.SERVICE_ACK_REQUEST,
                    Fields.SERVICE_ACK_ID: running_op.id,
                    Fields.SESSION_METRICS: self.get_session_metrics(),
                    Fields.TEST_METRICS: self.get_test_metrics(),
                    Fields.SYSTEM_HEALTH_METRICS: self.get_system_health_telemetry(),
                }
            }

            msg = self.create_message_from_dict(payload)
            msg.custom_properties[CustomPropertyNames.SERVICE_ACK_ID] = running_op.id

            queue_time = time.time()
            self.client.send_message(msg)
            logger.info("Telemetry op {} sent to service".format(running_op.id))

            self.metrics.send_message_count_sent.increment()

            send_time = time.time()
            if running_op.event.wait(timeout=self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]):
                logger.info("Telemetry op {} arrived at service".format(running_op.id))
                self.metrics.send_message_count_verified.increment()

                with self.reporter_lock:
                    self.reporter.set_metrics_from_dict(
                        {Metrics.LATENCY_QUEUE_MESSAGE_TO_SEND: (send_time - queue_time) * 1000}
                    )
                    self.reporter.record()
            else:
                logger.warning("Telemetry op {} did not arrive at service".format(running_op.id))
                self.metrics.send_message_count_timed_out.increment()

        while not self.done.isSet():
            reset_watchdog()
            self.outgoing_executor.submit(send_message)
            # sleep until we need to send again
            self.done.wait(1 / self.config[Settings.SEND_MESSAGE_OPERATIONS_PER_SECOND])

    def handle_desired_property_patch_received(self, patch):
        """
        callback for desired property patch reception
        """
        # props that have the pairing structure go to `incoming_pairing_message_queue`
        if patch.get(Fields.THIEF, {}).get(Fields.PAIRING, {}):
            self.incoming_pairing_message_queue.put(patch)

        # other props go into incoming_deisred_property_patch_queue
        else:
            self.incoming_desired_property_patch_queue.put(patch)

    def handle_message_received(self, msg):
        """
        Callback for receiving c2d messages.
        """
        obj = json.loads(msg.data.decode())
        thief = obj.get(Fields.THIEF)

        if (
            thief
            and thief[Fields.RUN_ID] == run_id
            and thief[Fields.SERVICE_INSTANCE_ID] == self.service_instance_id
        ):
            # We only inspect messages that have `thief/runId` and `thief/serviceInstanceId` set to the expected values
            cmd = thief[Fields.CMD]
            if cmd in [
                Commands.SERVICE_ACK_RESPONSE,
                Commands.METHOD_RESPONSE,
                Commands.C2D_RESPONSE,
            ]:
                self.incoming_executor.submit(self.handle_service_ack_response, msg)

            else:
                logger.warning("Unknown command received: {}".format(obj))

        else:
            logger.warning("C2D received, but it's not for us: {}".format(obj))

    def handle_service_ack_response(self, msg):
        """
        Code to handle incoming service_ack responses.  This is where we go through the list
        of `serviceAckId` values that we received and call the appropriate callbacks to indicate that
        the service has responded.
        """

        thief = json.loads(msg.data.decode())[Fields.THIEF]

        service_acks = thief.get(Fields.SERVICE_ACKS, [])
        if not service_acks:
            service_acks = [
                thief.get(Fields.SERVICE_ACK_ID),
            ]

        logger.info("Received {} message with {}".format(thief[Fields.CMD], service_acks))

        for service_ack_id in service_acks:
            running_op = self.running_operation_list.get(service_ack_id)
            if running_op:
                running_op.result_message = msg
                running_op.complete()
            else:
                logger.warning("Received unknown serviceAckId: {}:".format(service_ack_id))

    def operation_test_thread(self):
        """
        Thread which loops through various hub features and tests them one at a time.
        """

        tests = [
            (self.test_reported_properties, (), {}),
            (self.test_desired_properties, (), {}),
            (self.test_method_invoke, [TestMethod(MethodNames.FAIL_WITH_404, 404, False)], {}),
            (self.test_method_invoke, [TestMethod(MethodNames.ECHO_REQUEST, 200, True)], {}),
            (
                self.test_method_invoke,
                [TestMethod(MethodNames.UNDEFINED_METHOD_NAME, 500, False)],
                {},
            ),
            (self.test_c2d, (), {}),
        ]

        while not self.done.isSet():
            for (function, args, kwargs) in tests:
                reset_watchdog()
                self.outgoing_executor.submit(function, *args, **kwargs)

                time.sleep(self.config[Settings.INTER_TEST_DELAY_INTERVAL_IN_SECONDS])
                if self.done.isSet():
                    break

    def test_reported_properties(self):
        """
        test function to send a single reported property and then clear it after the
        server verifies it. It does this by setting properties inside
        `properties/reported/thief/testContent/reportedPropertyTest`.  Each property has
        a `addServiceAckId` value and a `removeServiceAckId` value.  When  the service sees the
        property added, it sends the `addServiceAckId` to the device.  When the service sees the
        property removed, it sends the `removeServiceAckid` to the device. This way the device
        can add a property, verify that it was added, then remove it and verify that it was removed.
        """

        # Get metrics.  We report them to Azure monitor and also push them as part of the twin
        metrics = {
            Fields.TEST_METRICS: self.get_test_metrics(),
            Fields.SYSTEM_HEALTH_METRICS: self.get_system_health_telemetry(),
        }
        self.send_metrics_to_azure_monitor(metrics)

        # session metrics goes into reported propertes, but not azure monitor
        # They're either never-changing (like start time) or redundant (like elapsed time)
        metrics[Fields.SESSION_METRICS] = self.get_session_metrics()

        def make_reported_prop(property_name, val):
            return {
                Fields.THIEF: {
                    Fields.TEST_CONTENT: {Fields.REPORTED_PROPERTY_TEST: {property_name: val}}
                }
            }

        add_operation = self.running_operation_list.make_event_based_operation()
        remove_operation = self.running_operation_list.make_event_based_operation()

        prop_name = "prop_{}".format(self.reported_property_index)
        self.reported_property_index += 1

        prop_value = {
            Fields.ADD_SERVICE_ACK_ID: add_operation.id,
            Fields.REMOVE_SERVICE_ACK_ID: remove_operation.id,
        }

        logger.info("Adding test property {}".format(prop_name))
        props = make_reported_prop(prop_name, prop_value)
        props[Fields.THIEF].update(metrics)
        self.client.patch_twin_reported_properties(props)

        if add_operation.event.wait(timeout=self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]):
            logger.info("Add of reported property {} verified by service".format(prop_name))
            self.metrics.reported_properties_count_added.increment()
        else:
            logger.info("Add of reported property {} verification timeout".format(prop_name))
            self.metrics.reported_properties_count_timed_out.increment()

        logger.info("Removing test property {}".format(prop_name))
        self.client.patch_twin_reported_properties(make_reported_prop(prop_name, None))

        if remove_operation.event.wait(timeout=self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]):
            logger.info("Remove of reported property {} verified by service".format(prop_name))
            self.metrics.reported_properties_count_removed.increment()
        else:
            logger.info("Remove of reported property {} verification timeout".format(prop_name))
            self.metrics.reported_properties_count_timed_out.increment()

    def test_desired_properties(self):
        """
        Test function to set a desired property, wait for the patch to arrive at the client,
        then get the twin to verify that it shows up in the twin.
        """
        twin_guid = str(uuid.uuid4())

        payload_set_desired_props = {
            Fields.THIEF: {
                Fields.CMD: Commands.SET_DESIRED_PROPS,
                Fields.DESIRED_PROPERTIES: {
                    Fields.THIEF: {Fields.TEST_CONTENT: {Fields.TWIN_GUID: twin_guid}}
                },
            }
        }
        msg = self.create_message_from_dict(payload_set_desired_props)
        logger.info("Sending message to update desired getTwin property to {}".format(twin_guid))
        self.client.send_message(msg)

        start_time = time.time()
        end_time = start_time + self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]

        actual_twin_guid = None
        while time.time() <= end_time:
            try:
                patch = self.incoming_desired_property_patch_queue.get(
                    max(0, end_time - time.time())
                )
            except queue.Empty:
                break
            else:
                thief = patch.get(Fields.THIEF, {})
                test_content = thief.get(Fields.TEST_CONTENT, {})
                actual_twin_guid = test_content.get(Fields.TWIN_GUID)
                if actual_twin_guid == twin_guid:
                    logger.info("received expected patch: {} succeeded".format(twin_guid))
                    self.metrics.desired_property_patch_count_received.increment()
                    break
                else:
                    logger.info(
                        "Did not receive expected patch (yet). actual = {}.  expected = {}".format(
                            actual_twin_guid, twin_guid
                        )
                    )

        if actual_twin_guid != twin_guid:
            logger.warning(
                "wait_for_desired_property_patch did not retrieve expected properties within expected time.  expected={}".format(
                    twin_guid
                )
            )
            self.metrics.desired_property_patch_count_timed_out.increment()

        # Now test the twin.  Since we already received the patch, our property should
        # be in the twin.
        twin = self.client.get_twin()
        logger.info("Got twin: {}".format(twin))

        desired = twin.get(Fields.DESIRED, {})
        thief = desired.get(Fields.THIEF, {})
        test_content = thief.get(Fields.TEST_CONTENT, {})
        actual_twin_guid = test_content.get(Fields.TWIN_GUID)

        if actual_twin_guid == twin_guid:
            logger.info("Got desired_twin: {} succeeded".format(twin_guid))
            self.metrics.get_twin_count_succeeded.increment()
        else:
            logger.info(
                "get_twin property did not match: actual = {} expected = {}".format(
                    actual_twin_guid, twin_guid
                )
            )
            self.metrics.get_twin_count_timed_out_out.increment()

    def handle_method_received(self, method_request):
        def handle():
            logger.info("Received method request {}".format(method_request.name))
            self.metrics.method_invoke_count_request_received.increment()
            if method_request.name == MethodNames.FAIL_WITH_404:
                logger.info("sending response to fail with 404")
                self.client.send_method_response(
                    MethodResponse.create_from_method_request(method_request, 404)
                )
            elif method_request.name == MethodNames.ECHO_REQUEST:
                self.client.send_method_response(
                    MethodResponse.create_from_method_request(
                        method_request, 200, method_request.payload,
                    )
                )
            else:
                logger.info("sending response to fail with 500")
                self.client.send_method_response(
                    MethodResponse.create_from_method_request(method_request, 500)
                )

        self.incoming_executor.submit(handle)

    def make_random_payload(self):
        return {
            "random_guid": str(uuid.uuid4()),
            "sub_object": {
                "string_value": str(uuid.uuid4()),
                "bool_value": random.random() > 0.5,
                "int_value": random.randint(1, 65535),
                "float_value": random.random() * 65535,
            },
        }

    def test_method_invoke(self, method):
        running_op = self.running_operation_list.make_event_based_operation()

        if method.include_payload:
            payload = self.make_random_payload()
        else:
            payload = None

        command_payload = {
            Fields.THIEF: {
                Fields.CMD: Commands.INVOKE_METHOD,
                Fields.SERVICE_ACK_ID: running_op.id,
                Fields.METHOD_NAME: method.method_name,
                Fields.METHOD_INVOKE_PAYLOAD: payload,
            }
        }
        msg = self.create_message_from_dict(command_payload)
        logger.info("sending method invoke with guid={}".format(running_op.id))
        self.client.send_message(msg)

        if running_op.event.wait(timeout=self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]):
            logger.info(
                "method with guid {} returned {}".format(running_op.id, running_op.result_message)
            )
            thief = json.loads(running_op.result_message.data.decode())[Fields.THIEF]
            fail = False
            if thief[Fields.METHOD_RESPONSE_STATUS_CODE] != method.expected_status_code:
                logger.error(
                    "Unexpected method status: id={}, received {} expected {}".format(
                        running_op.id,
                        thief[Fields.METHOD_RESPONSE_STATUS_CODE],
                        method.expected_status_code,
                    )
                )
                fail = True
            if thief[Fields.METHOD_RESPONSE_PAYLOAD] != payload:
                logger.error(
                    "Unexpected payload: id={}, received {} expected {}".format(
                        running_op.id, thief[Fields.METHOD_RESPONSE_PAYLOAD], payload
                    )
                )
                fail = True

            if fail:
                raise ThiefFatalException("Content mismatch on method invoke")
            else:
                logger.info("Method call check succeeded")

        else:
            logger.error("method with guid {} never completed".format(running_op.id))
            self.metrics.method_invoke_count_request_timed_out = ThreadSafeCounter()

    def test_c2d(self):

        running_op = self.running_operation_list.make_event_based_operation()

        sent_test_payload = self.make_random_payload()

        command_payload = {
            Fields.THIEF: {
                Fields.CMD: Commands.SEND_C2D,
                Fields.SERVICE_ACK_ID: running_op.id,
                Fields.TEST_C2D_PAYLOAD: sent_test_payload,
            }
        }

        logger.info("Requesting C2D for serviceAckId {}".format(running_op.id))
        self.client.send_message(self.create_message_from_dict(command_payload))

        if running_op.event.wait(timeout=self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]):
            logger.info("C2D received for serviceAckId {}".format(running_op.id))
            self.metrics.receive_c2d_count_received.increment()

            thief = json.loads(running_op.result_message.data.decode())[Fields.THIEF]
            if thief[Fields.TEST_C2D_PAYLOAD] != sent_test_payload:
                logger.warning(
                    "C2D payload for serviceAckId {}  does not match.  Expected={}, Received={}".format(
                        running_op.id, sent_test_payload, thief[Fields.TEST_C2D_PAYLOAD]
                    )
                )
                raise ThiefFatalException("C2D payload mismatch")
        else:
            logger.info("C2D timed out for serviceAckId {}".format(running_op.id))
            self.metrics.receive_c2d_count_timed_out.increment()

    def wrap_handler(self, func):
        """
        Function to take a handler function and wrap it inside a try/catch block
        which increments exception count.  This is done because iothub callbacks
        will catch and swallow any exceptions that get raised in handlers.
        """

        def newfunc(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.error("exception in handler: {}".format(str(e) or type(e)), exc_info=True)
                self.metrics.exception_count.increment()

        return newfunc

    def main(self):

        self.metrics.run_start_utc = datetime.datetime.now(datetime.timezone.utc)
        self.metrics.run_state = RunStates.RUNNING
        logger.info("Starting at {}".format(self.metrics.run_start_utc))

        # Create our client and push initial properties
        self.client, self.hub, self.device_id = dps.create_device_client_using_dps_group_key(
            provisioning_host=provisioning_host,
            registration_id=registration_id,
            id_scope=id_scope,
            group_symmetric_key=group_symmetric_key,
            keep_alive=self.config[Settings.MQTT_KEEP_ALIVE_INTERVAL],
            sastoken_ttl=self.config[Settings.SAS_TOKEN_RENEWAL_INTERVAL],
        )
        hub_host_name = self.hub[: self.hub.find(".")]  # keep everything before the first dot
        azure_monitor.add_logging_properties(hub=hub_host_name, device_id=self.device_id)
        self.update_initial_reported_properties()

        event_logger.info(
            Events.STARTING_RUN, extra=custom_props({CustomDimensions.RUN_REASON: run_reason})
        )

        # Set handlers for incoming hub messages
        self.client.on_message_received = self.wrap_handler(self.handle_message_received)
        self.client.on_method_request_received = self.wrap_handler(self.handle_method_received)
        self.client.on_twin_desired_properties_patch_received = self.wrap_handler(
            self.handle_desired_property_patch_received
        )

        # Pair
        self.pair_with_service()

        # Start testing threads
        self.outgoing_executor.submit(self.test_send_message_thread, critical=True)
        self.outgoing_executor.submit(self.operation_test_thread, critical=True)

        self.metrics.exit_reason = ""
        start_time = time.time()
        planned_end_time = start_time + self.config[Settings.MAX_RUN_DURATION_IN_SECONDS]
        try:
            while time.time() < planned_end_time:
                # TODO: limit sleep length to check failure counts more often
                self.outgoing_executor.wait_for_thread_death_event(planned_end_time - time.time())
                self.outgoing_executor.check_watchdogs()
                self.incoming_executor.check_watchdogs()

                non_fatal_errors = 0
                fatal_error = None

                def count_failure(e):
                    nonlocal non_fatal_errors, fatal_error
                    if isinstance(e, ThiefFatalException):
                        logger.info("FATAL ERROR: {}".format(str(e) or type(e)))
                        fatal_error = e
                    else:
                        non_fatal_errors += 1

                self.outgoing_executor.check_for_failures(count_failure)
                self.incoming_executor.check_for_failures(count_failure)
                if non_fatal_errors:
                    logger.info("Adding {} failures to count".format(non_fatal_errors))
                    self.metrics.exception_count.add(non_fatal_errors)
                if fatal_error:
                    raise (fatal_error)
            self.metrics.run_state = RunStates.COMPLETE
        except KeyboardInterrupt:
            self.metrics.run_state = RunStates.INTERRUPTED
            self.metrics.exit_reason = "KeyboardInterrupt"
            raise
        except BaseException as e:
            self.metrics.run_state = RunStates.FAILED
            self.metrics.exit_reason = str(e) or type(e)
            logger.error("Run failed: {}".format(self.metrics.exit_reason), exc_info=True)
            raise
        finally:
            logger.info("-------------------------------------------------------------")
            logger.info("Setting done flag: {}".format(self.metrics.exit_reason))
            logger.info("-------------------------------------------------------------")
            self.done.set()
            active_threads = 0
            for executor in [self.outgoing_executor, self.incoming_executor]:
                done, not_done = executor.wait(
                    timeout=2 * self.config[Settings.OPERATION_TIMEOUT_IN_SECONDS]
                )
                active_threads += len(not_done)
            if active_threads:
                logger.error("{} threads not stopped after ending run".format(active_threads))
                dump_active_stacks(logger.info)

            logger.info("Exiting main at {}".format(datetime.datetime.utcnow()))
            event_logger.info(
                Events.ENDING_RUN,
                extra=custom_props({CustomDimensions.EXIT_REASON: self.metrics.exit_reason}),
            )

            # Update one last time.  This is required because the service app relies
            # on RUN_STATE to know when we're dead
            props = {
                Fields.THIEF: {
                    Fields.SESSION_METRICS: self.get_session_metrics(),
                    Fields.TEST_METRICS: self.get_test_metrics(),
                    Fields.SYSTEM_HEALTH_METRICS: self.get_system_health_telemetry(),
                }
            }
            logger.info("Results: {}".format(pprint.pformat(props)))
            self.client.patch_twin_reported_properties(props)

            logger.info("Disconnecting")
            self.client.disconnect()
            logger.info("Done disconnecting")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            run_reason = " ".join(sys.argv[1:])
        DeviceApp().main()
    except BaseException as e:
        logger.critical("App shutdown exception: {}".format(str(e) or type(e)), exc_info=True)
        raise
    finally:
        # Flush azure monitor telemetry
        logging.shutdown()
