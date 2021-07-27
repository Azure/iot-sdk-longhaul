# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import logging
import time
import os
import queue
import threading
import json
import datetime
import uuid
import collections
import faulthandler
from executor import BetterThreadPoolExecutor, reset_watchdog
from azure.iot.hub import IoTHubRegistryManager, iothub_amqp_client
from azure.iot.hub.protocol.models import Twin, TwinProperties, CloudToDeviceMethod
import azure.iot.hub.constant
from azure.eventhub import EventHubConsumerClient
import azure_monitor
from thief_constants import Const, Fields, Commands, RunStates, Flags
import thief_secrets

faulthandler.enable()

iothub_connection_string = thief_secrets.THIEF_SERVICE_CONNECTION_STRING
iothub_name = thief_secrets.THIEF_IOTHUB_NAME
eventhub_connection_string = thief_secrets.THIEF_EVENTHUB_CONNECTION_STRING
eventhub_consumer_group = thief_secrets.THIEF_EVENTHUB_CONSUMER_GROUP
service_pool = thief_secrets.THIEF_SERVICE_POOL

# Optional environment variables.
# run_id can be an environment variable or it can be automatically generated
service_instance_id = os.getenv("THIEF_SERVICE_INSTANCE_ID")
if not service_instance_id:
    service_instance_id = str(uuid.uuid4())

# set default logging which will only go to the console
logging.basicConfig(level=logging.WARNING)
logging.getLogger("thief").setLevel(level=logging.INFO)
logging.getLogger("azure.iot").setLevel(level=logging.INFO)
logger = logging.getLogger("thief.{}".format(__name__))

# configure which traces and events go to Azure Monitor
azure_monitor.add_logging_properties(
    client_type="service",
    service_instance_id=service_instance_id,
    hub=iothub_name,
    sdk_version=azure.iot.hub.constant.VERSION,
    pool_id=service_pool,
)
event_logger = azure_monitor.get_event_logger()
azure_monitor.log_to_azure_monitor("thief")

OperationResponse = collections.namedtuple("OperationResponse", "device_id operation_id")
OutgoingC2d = collections.namedtuple("OutgoingC2d", "device_id message props")


def custom_props(device_id, run_id=None):
    """
    helper function for adding customDimensions to logger calls at execution time
    """
    props = {"deviceId": device_id}
    if run_id:
        props["runId"] = run_id
    return {"custom_dimensions": props}


class PerDeviceData(object):
    """
    Object that holds data that needs to be stored in a device-by-device basis
    """

    def __init__(self, device_id, run_id):
        self.device_id = device_id
        self.run_id = run_id

        # for verifying reported property changes
        self.reported_property_list_lock = threading.Lock()
        self.reported_property_values = {}


class PerDeviceDataList(object):
    """
    Thread-safe object for holding a dictionary of PerDeviceData objects.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.devices = {}

    def add(self, device_id, data):
        """
        Add a new object to the dict
        """
        with self.lock:
            self.devices[device_id] = data

    def remove(self, device_id):
        """
        remove an object from the dict
        """
        with self.lock:
            if device_id in self.devices:
                del self.devices[device_id]

    def try_get(self, device_id):
        """
        Try to get an object from the dict, returning None if the object doesn't exist
        """
        with self.lock:
            return self.devices.get(device_id, None)

    def get_keys(self):
        """
        Get a list of keys for the objects in the dict
        """
        with self.lock:
            return list(self.devices.keys())


class ServiceRunConfig(object):
    """
    Object we use internally to keep track of how the entire test is configured.
    """

    def __init__(self):
        # How long do we allow a thread to be unresponsive for.
        self.watchdog_failure_interval_in_seconds = 300

        # How long until our AMQP sas tokens expire
        self.amqp_sas_expiry_in_seconds = 24 * 60 * 60


def get_device_id_from_event(event):
    """
    Helper function to get the device_id from an EventHub message
    """
    return event.message.annotations["iothub-connection-device-id".encode()].decode()


def get_message_source_from_event(event):
    """
    Helper function to get the message source from an EventHub message
    """
    return event.message.annotations["iothub-message-source".encode()].decode()


class ServiceApp(object):
    """
    Main application object
    """

    def __init__(self):
        super(ServiceApp, self).__init__()

        self.executor = BetterThreadPoolExecutor(max_workers=128)
        self.done = threading.Event()
        self.registry_manager = None
        self.eventhub_consumer_client = None
        self.config = ServiceRunConfig()

        # for any kind of c2d
        self.outgoing_c2d_queue = queue.Queue()

        # for operationResponse messages
        self.force_send_operation_response = threading.Event()
        self.outgoing_operation_response_queue = queue.Queue()

        # for pairing
        self.device_list = PerDeviceDataList()

        # for reported property tracking
        self.incoming_twin_changes = queue.Queue()

        # change the default SAS expiry
        iothub_amqp_client.default_sas_expiry = self.config.amqp_sas_expiry_in_seconds

    def handle_method_invoke(self, device_data, event):
        body = event.body_as_json()
        thief = body.get(Fields.THIEF, {})
        method_guid = thief.get(Fields.OPERATION_ID)
        method_name = thief.get(Fields.METHOD_NAME)

        logger.info("------------------------------------------------------------------")
        logger.info("received method invoke method={}, guid={}".format(method_name, method_guid))

        request = CloudToDeviceMethod(
            method_name=method_name,
            payload=thief.get(Fields.METHOD_INVOKE_PAYLOAD, None),
            response_timeout_in_seconds=thief.get(
                Fields.METHOD_INVOKE_RESPONSE_TIMEOUT_IN_SECONDS, None
            ),
            connect_timeout_in_seconds=thief.get(
                Fields.METHOD_INVOKE_CONNECT_TIMEOUT_IN_SECONDS, None
            ),
        )

        logger.info("invoking {}".format(method_guid))
        try:
            response = self.registry_manager.invoke_device_method(device_data.device_id, request)
        except Exception as e:
            logger.error("exception for invoke on {}: {}".format(method_guid, str(e) or type(e)))
            raise
        logger.info("invoke complete {}".format(method_guid))

        response_message = json.dumps(
            {
                Fields.THIEF: {
                    Fields.CMD: Commands.METHOD_RESPONSE,
                    Fields.SERVICE_INSTANCE_ID: service_instance_id,
                    Fields.RUN_ID: device_data.run_id,
                    Fields.OPERATION_ID: method_guid,
                    Fields.METHOD_RESPONSE_PAYLOAD: response.payload,
                    Fields.METHOD_RESPONSE_STATUS_CODE: response.status,
                }
            }
        )

        logger.info("queueing response {}".format(method_guid))

        self.outgoing_c2d_queue.put(
            OutgoingC2d(
                device_id=device_data.device_id,
                message=response_message,
                props=Const.JSON_TYPE_AND_ENCODING,
            )
        )

    def dispatch_incoming_message(self, event):
        """
        Function to dispatch incoming EventHub messages.  A different thread receives the messages
        and spins up a temporary thread to call this function.
        """

        device_id = get_device_id_from_event(event)

        body = event.body_as_json()

        if get_message_source_from_event(event) == "twinChangeEvents":
            thief = body.get(Fields.PROPERTIES, {}).get(Fields.REPORTED, {}).get(Fields.THIEF, {})
        else:
            thief = body.get(Fields.THIEF, {})

        received_service_instance_id = thief.get(Fields.SERVICE_INSTANCE_ID, None)
        received_run_id = thief.get(Fields.RUN_ID, None)
        received_operation_id = thief.get(Fields.OPERATION_ID, None)

        device_data = self.device_list.try_get(device_id)

        if not device_data and received_service_instance_id == service_instance_id:
            # The device app wants to pair with us
            device_data = PerDeviceData(device_id, received_run_id)
            self.device_list.add(device_id, device_data)
        elif device_data and not received_service_instance_id == service_instance_id:
            # previously paired, but not any more
            logger.info(
                "Device {} deviced to pair with service instance {}.".format(
                    device_id, received_service_instance_id
                ),
                extra=custom_props(device_id, received_run_id),
            )
            self.device_list.remove(device_id)

        if device_data:
            device_data.run_id = received_run_id

        if get_message_source_from_event(event) == "twinChangeEvents":
            if device_data:
                self.incoming_twin_changes.put(event)

        elif received_run_id:
            cmd = thief.get(Fields.CMD, None)

            if cmd == Commands.PAIR_WITH_SERVICE_APP:
                if thief.get(Fields.REQUESTED_SERVICE_POOL, None) == service_pool:
                    logger.info(
                        "Device {} attempting to pair with operation ID {}".format(
                            device_id, received_operation_id
                        ),
                        extra=custom_props(device_id, received_run_id),
                    )

                    message = json.dumps(
                        {
                            Fields.THIEF: {
                                Fields.CMD: Commands.PAIR_RESPONSE,
                                Fields.SERVICE_INSTANCE_ID: service_instance_id,
                                Fields.RUN_ID: received_run_id,
                                Fields.OPERATION_ID: received_operation_id,
                            }
                        }
                    )

                    self.outgoing_c2d_queue.put(
                        OutgoingC2d(
                            device_id=device_id,
                            message=message,
                            props=Const.JSON_TYPE_AND_ENCODING,
                        )
                    )

                    # don't add device_id to self.device_list until we get a message with our
                    # service_instance_id

            elif received_service_instance_id == service_instance_id:
                if cmd == Commands.SEND_OPERATION_RESPONSE:
                    logger.info(
                        "Received telemetry sendOperationResponse from {} with operationId {}".format(
                            device_id, received_operation_id,
                        ),
                        extra=custom_props(device_id, device_data.run_id),
                    )
                    self.outgoing_operation_response_queue.put(
                        OperationResponse(device_id=device_id, operation_id=received_operation_id,)
                    )

                    if Flags.RESPOND_IMMEDIATELY in thief.get(Fields.FLAGS, []):
                        self.force_send_operation_response.set()

                elif cmd == Commands.SET_DESIRED_PROPS:
                    desired = thief.get(Fields.DESIRED_PROPERTIES, {})
                    if desired:
                        logger.info("Updating desired props: {}".format(desired))
                        self.registry_manager.update_twin(
                            device_id, Twin(properties=TwinProperties(desired=desired)), "*"
                        )
                elif cmd == Commands.INVOKE_METHOD:
                    self.executor.submit(self.handle_method_invoke, device_data, event)
                    # TODO: add_done_callback -- code to handle this is in the device app, needs to be done here too, so we can count exceptions in non-critical threads

                elif cmd == Commands.SEND_C2D:
                    logger.info(
                        "Sending C2D to {} with operationId {}".format(
                            device_id, received_operation_id,
                        ),
                        extra=custom_props(device_id, device_data.run_id),
                    )
                    message = json.dumps(
                        {
                            Fields.THIEF: {
                                Fields.CMD: Commands.C2D_RESPONSE,
                                Fields.SERVICE_INSTANCE_ID: service_instance_id,
                                Fields.RUN_ID: device_data.run_id,
                                Fields.OPERATION_ID: received_operation_id,
                                Fields.TEST_C2D_PAYLOAD: thief[Fields.TEST_C2D_PAYLOAD],
                            }
                        }
                    )

                    self.outgoing_c2d_queue.put(
                        OutgoingC2d(
                            device_id=device_id,
                            message=message,
                            props=Const.JSON_TYPE_AND_ENCODING,
                        )
                    )

                else:
                    logger.info(
                        "Unknown command received from {}: {}".format(device_id, body),
                        extra=custom_props(device_id, device_data.run_id),
                    )

    def receive_incoming_messages_thread(self):
        """
        Thread to listen on eventhub for events that we can handle.  This thread does minimal
        checking to see if an event is "interesting" before starting up a temporary thread to
        handle it.  Any additional processing necessary to handle the events is done in that
        temporary thread.
        """

        def on_error(partition_context, error):
            logger.error("EventHub on_error: {}".format(str(error) or type(error)))

        def on_partition_initialize(partition_context):
            logger.warning("EventHub on_partition_initialize")

        def on_partition_close(partition_context, reason):
            logger.warning("EventHub on_partition_close: {}".format(reason))

        def on_event(partition_context, event):
            reset_watchdog()
            if event:
                self.executor.submit(self.dispatch_incoming_message, event)

        logger.info("Starting EventHub receive")
        with self.eventhub_consumer_client:
            self.eventhub_consumer_client.receive(
                on_event,
                on_error=on_error,
                on_partition_initialize=on_partition_initialize,
                on_partition_close=on_partition_close,
                max_wait_time=30,
            )

    def send_outgoing_c2d_messages_thread(self):
        """
        Thread which is responsible for sending C2D messages.  This is separated into it's own
        thread in order to centralize error handling and also because sending is a synchronous
        function and we don't want to block other threads while we're sending.
        """
        logger.info("Starting thread")

        while not (self.done.isSet() and self.outgoing_c2d_queue.empty()):
            reset_watchdog()

            try:
                outgoing_c2d = self.outgoing_c2d_queue.get(timeout=1)
            except queue.Empty:
                pass
            else:
                device_id = outgoing_c2d.device_id
                message = outgoing_c2d.message
                props = outgoing_c2d.props
                device_data = self.device_list.try_get(device_id)
                run_id = device_data.run_id if device_data else None

                start = time.time()
                try:
                    self.registry_manager.send_c2d_message(device_id, message, props)
                except Exception as e:
                    logger.error(
                        "send_c2d_message to {} raised {}. Dropping. ".format(
                            device_id, str(e) or type(e)
                        ),
                        exc_info=e,
                        extra=custom_props(device_id, run_id),
                    )
                else:
                    end = time.time()
                    if end - start > 2:
                        logger.warning(
                            "Send throttled.  Time delta={} seconds".format(end - start),
                            extra=custom_props(device_id, run_id),
                        )

    def handle_send_operation_response_thread(self):
        """
        Thread which is responsible for returning operationResponse message to the
        device clients. The operationResponse objects are collected in `outgoing_operation_response_queue`
        and this thread collects the responses into batches to send at a regular interval.  This
        batching is required because we send many responses per second and IoTHub will throttle
        C2D events if we send too many.  Sending fewer big messages is better than sending fewer
        small messages.
        """

        while not self.done.isSet():
            reset_watchdog()

            operation_ids = {}
            while True:
                try:
                    operation_response = self.outgoing_operation_response_queue.get_nowait()
                except queue.Empty:
                    break
                if operation_response.device_id not in operation_ids:
                    operation_ids[operation_response.device_id] = []
                # it's possible to get the same eventhub message twice, especially if we have to reconnect
                # to refresh credentials. Don't send the same service ack twice.
                if (
                    operation_response.operation_id
                    not in operation_ids[operation_response.device_id]
                ):
                    operation_ids[operation_response.device_id].append(
                        operation_response.operation_id
                    )

            for device_id in operation_ids:

                device_data = self.device_list.try_get(device_id)

                if device_data:
                    logger.info(
                        "Send operationResponse for device_id = {}: {}".format(
                            device_id, operation_ids[device_id]
                        ),
                        extra=custom_props(device_id, device_data.run_id),
                    )

                    message = json.dumps(
                        {
                            Fields.THIEF: {
                                Fields.CMD: Commands.OPERATION_RESPONSE,
                                Fields.SERVICE_INSTANCE_ID: service_instance_id,
                                Fields.RUN_ID: device_data.run_id,
                                Fields.OPERATION_IDS: operation_ids[device_id],
                            }
                        }
                    )

                    self.outgoing_c2d_queue.put(
                        OutgoingC2d(
                            device_id=device_id,
                            message=message,
                            props=Const.JSON_TYPE_AND_ENCODING,
                        )
                    )

            # TODO: this should be configurable
            # Too small and this causes C2D throttling
            self.force_send_operation_response.wait(timeout=15)
            self.force_send_operation_response.clear()

    def respond_to_test_content_properties(self, event):
        """
        Function to respond to changes to `testContent` reported properties.  `testContent`
        properties contain content, such as properties that contain random strings which are
        used to test various features.

        for `reportedPropertyTest` properties, this function will send operationResponse messages to the
        device when the property is added, and then again when the property is removed
        """
        device_id = get_device_id_from_event(event)
        device_data = self.device_list.try_get(device_id)

        test_content = (
            event.body_as_json()
            .get(Fields.PROPERTIES, {})
            .get(Fields.REPORTED, {})
            .get(Fields.THIEF, {})
            .get(Fields.TEST_CONTENT, {})
        )
        reported_property_test = test_content.get(Fields.REPORTED_PROPERTY_TEST)

        for property_name in reported_property_test:
            if device_data and property_name.startswith("prop_"):
                property_value = reported_property_test[property_name]

                with device_data.reported_property_list_lock:
                    if property_value:
                        operation_id = property_value[Fields.ADD_OPERATION_ID]
                        if Fields.REMOVE_OPERATION_ID in property_value:
                            device_data.reported_property_values[property_name] = property_value
                    else:
                        if (
                            Fields.REMOVE_OPERATION_ID
                            in device_data.reported_property_values[property_name]
                        ):
                            operation_id = device_data.reported_property_values[property_name][
                                Fields.REMOVE_OPERATION_ID
                            ]
                            del device_data.reported_property_values[property_name]
                        else:
                            operation_id = None

                if operation_id:
                    self.outgoing_operation_response_queue.put(
                        OperationResponse(device_id=device_id, operation_id=operation_id)
                    )
                    self.force_send_operation_response.set()

    def dispatch_twin_change_thread(self):
        """
        Thread which goes through the queue of twin changes messages which have arrived and
        acts on the content.
        """
        while not self.done.isSet():
            reset_watchdog()

            try:
                event = self.incoming_twin_changes.get(timeout=1)
            except queue.Empty:
                continue

            device_id = get_device_id_from_event(event)
            thief = (
                event.body_as_json()
                .get(Fields.PROPERTIES, {})
                .get(Fields.REPORTED, {})
                .get(Fields.THIEF, {})
            )
            if not thief:
                thief = {}

            device_data = self.device_list.try_get(device_id)
            if device_data:
                run_id = device_data.run_id
            else:
                run_id = thief.get(Fields.PAIRING, {}).get(Fields.RUN_ID, None)

            logger.info(
                "Twin change for {}: {}".format(device_id, event.body_as_json()),
                extra=custom_props(device_id, run_id),
            )

            if thief.get(Fields.TEST_CONTENT):
                self.respond_to_test_content_properties(event)

            run_state = thief.get(Fields.SESSION_METRICS, {}).get("runState")
            if run_state and run_state != RunStates.RUNNING:
                logger.info(
                    "Device {} no longer running.".format(device_id),
                    extra=custom_props(device_id, run_id),
                )
                self.device_list.remove(device_id)

    def main(self):

        logger.info("creating registry manager")
        self.registry_manager = IoTHubRegistryManager(iothub_connection_string)

        self.eventhub_consumer_client = EventHubConsumerClient.from_connection_string(
            eventhub_connection_string, consumer_group=eventhub_consumer_group
        )

        self.executor.submit(self.receive_incoming_messages_thread, critical=True)
        self.executor.submit(self.dispatch_twin_change_thread, critical=True)
        self.executor.submit(self.send_outgoing_c2d_messages_thread, critical=True)
        self.executor.submit(self.handle_send_operation_response_thread, critical=True)

        try:
            while True:
                self.executor.wait_for_thread_death_event()
                self.executor.check_watchdogs()
                self.executor.check_for_failures(None)
        except Exception as e:
            logger.error("Fatal exception: {}".format(str(e) or type(e), exc_info=True))
        finally:
            # close the eventhub consumer before shutting down threads.  This is necessary because
            # the "receive" function that we use to receive EventHub events is blocking and doesn't
            # have a timeout.
            logger.info("closing eventhub listener")
            self.eventhub_consumer_client.close()
            self.done.set()
            done, not_done = self.executor.wait(timeout=60)
            if not_done:
                logger.error("{} threads not stopped after ending run".format(len(not_done)))

            logger.info("Exiting main at {}".format(datetime.datetime.utcnow()))


if __name__ == "__main__":
    try:
        ServiceApp().main()
    except BaseException as e:
        logger.critical("App shutdown exception: {}".format(str(e) or type(e)), exc_info=True)
        raise
    finally:
        # Flush azure monitor telemetry
        logging.shutdown()
