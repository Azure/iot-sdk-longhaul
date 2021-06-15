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
from thief_constants import Const, Fields, Commands, RunStates

faulthandler.enable()

# use os.environ[] for required environment variables
iothub_connection_string = os.environ["THIEF_SERVICE_CONNECTION_STRING"]
iothub_name = os.environ["THIEF_IOTHUB_NAME"]
eventhub_connection_string = os.environ["THIEF_EVENTHUB_CONNECTION_STRING"]
eventhub_consumer_group = os.environ["THIEF_EVENTHUB_CONSUMER_GROUP"]
service_pool = os.environ["THIEF_SERVICE_POOL"]

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

ServiceAck = collections.namedtuple("ServiceAck", "device_id service_ack_id")
OutgoingC2d = collections.namedtuple("OutgoingC2d", "device_id message props fail_count")
OutgoingC2d.__new__.__defaults__ = (0,)  # applied to rightmost args, so fail_count defaults to 0


# TODO: remove items from pairing list of no traffic for X minutes


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
        self.amqp_sas_expiry_in_seconds = 3600

        # How often to refresh the AMQP connection.  Sometime before it expires.
        self.amqp_refresh_interval_in_seconds = self.amqp_sas_expiry_in_seconds - 300

        # How many times to retry sending C2D before failing
        self.send_c2d_retry_count = 3


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
        self.registry_manager_lock = threading.Lock()
        self.registry_manager = None
        self.eventhub_consumer_client = None
        self.config = ServiceRunConfig()

        # for any kind of c2d
        self.outgoing_c2d_queue = queue.Queue()

        # for service_acks
        self.outgoing_service_ack_response_queue = queue.Queue()

        # for pairing
        self.device_list = PerDeviceDataList()

        # for reported property tracking
        self.incoming_twin_changes = queue.Queue()

        # change the default SAS expiry
        iothub_amqp_client.default_sas_expiry = self.config.amqp_sas_expiry_in_seconds

    def handle_method_invoke(self, device_data, event):
        body = event.body_as_json()
        thief = body.get(Fields.THIEF, {})
        method_guid = thief.get(Fields.SERVICE_ACK_ID)
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

        # TODO: don't hold this lock while calling into registry manager
        # TODO: wrap registry manager call in try/except to return result to device
        logger.info("------------------------------------------------------------------")
        logger.info("invoking {}".format(method_guid))
        try:
            with self.registry_manager_lock:
                response = self.registry_manager.invoke_device_method(
                    device_data.device_id, request
                )
        except Exception as e:
            # TODO: remove this once future callback is added
            logger.info("------------------------------------------------------------------")
            logger.error("exception: {}".format(str(e) or type(e)))
            raise
        finally:
            logger.info("------------------------------------------------------------------")
            logger.info("invoke complete finally")
        logger.info("------------------------------------------------------------------")
        logger.info("invoke complete {}".format(method_guid))

        response_message = json.dumps(
            {
                Fields.THIEF: {
                    Fields.CMD: Commands.METHOD_RESPONSE,
                    Fields.SERVICE_INSTANCE_ID: service_instance_id,
                    Fields.RUN_ID: device_data.run_id,
                    Fields.SERVICE_ACK_ID: method_guid,
                    Fields.METHOD_RESPONSE_PAYLOAD: response.payload,
                    Fields.METHOD_RESPONSE_STATUS_CODE: response.status,
                }
            }
        )

        logger.info("------------------------------------------------------------------")
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
        thief = body.get(Fields.THIEF, {})
        received_service_instance_id = thief.get(Fields.SERVICE_INSTANCE_ID, None)
        received_run_id = thief.get(Fields.RUN_ID, None)

        device_data = self.device_list.try_get(device_id)

        if get_message_source_from_event(event) == "twinChangeEvents":
            thief = body.get(Fields.PROPERTIES, {}).get(Fields.REPORTED, {}).get(Fields.THIEF, {})
            if thief and thief.get(Fields.PAIRING, {}):
                self.executor.submit(self.handle_pairing_request, event)
            if device_data:
                self.incoming_twin_changes.put(event)

        elif received_run_id and received_service_instance_id:
            cmd = thief.get(Fields.CMD, None)

            if device_data:
                if cmd == Commands.SERVICE_ACK_REQUEST:
                    logger.info(
                        "Received telemetry serviceAckRequest from {} with serviceAckId {}".format(
                            device_id, thief[Fields.SERVICE_ACK_ID]
                        ),
                        extra=custom_props(device_id, device_data.run_id),
                    )
                    self.outgoing_service_ack_response_queue.put(
                        ServiceAck(
                            device_id=device_id, service_ack_id=thief[Fields.SERVICE_ACK_ID],
                        )
                    )
                elif cmd == Commands.SET_DESIRED_PROPS:
                    desired = thief.get(Fields.DESIRED_PROPERTIES, {})
                    if desired:
                        logger.info("Updating desired props: {}".format(desired))
                        with self.registry_manager_lock:
                            self.registry_manager.update_twin(
                                device_id, Twin(properties=TwinProperties(desired=desired)), "*"
                            )
                elif cmd == Commands.INVOKE_METHOD:
                    self.executor.submit(self.handle_method_invoke, device_data, event)
                    # TODO: add_done_callback -- code to handle this is in the device app, needs to be done here too

                elif cmd == Commands.SEND_C2D:
                    logger.info(
                        "Sending C2D to {} with serviceAckId {}".format(
                            device_id, thief[Fields.SERVICE_ACK_ID]
                        ),
                        extra=custom_props(device_id, device_data.run_id),
                    )
                    message = json.dumps(
                        {
                            Fields.THIEF: {
                                Fields.CMD: Commands.C2D_RESPONSE,
                                Fields.SERVICE_INSTANCE_ID: service_instance_id,
                                Fields.RUN_ID: device_data.run_id,
                                Fields.SERVICE_ACK_ID: thief[Fields.SERVICE_ACK_ID],
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
        last_amqp_refresh_epochtime = time.time()
        refresh_registry_manager = False

        while not (self.done.isSet() and self.outgoing_c2d_queue.empty()):
            reset_watchdog()

            if (
                time.time() - last_amqp_refresh_epochtime
                > self.config.amqp_refresh_interval_in_seconds
            ):
                logger.info("AMQP credential approaching expiration.")
                refresh_registry_manager = True

            if refresh_registry_manager:
                logger.info("Creating new registry manager object.")
                with self.registry_manager_lock:
                    self.registry_manager.amqp_svc_client.disconnect_sync()
                    self.registry_manager = None
                    time.sleep(1)
                    self.registry_manager = IoTHubRegistryManager(iothub_connection_string)
                logger.info("New registry_manager object created")
                last_amqp_refresh_epochtime = time.time()
                refresh_registry_manager = False

            try:
                outgoing_c2d = self.outgoing_c2d_queue.get(timeout=1)
                device_id = outgoing_c2d.device_id
                message = outgoing_c2d.message
                props = outgoing_c2d.props
            except queue.Empty:
                pass
            else:
                device_data = self.device_list.try_get(device_id)

                if not device_data:
                    logger.warning(
                        "C2D found in outgoing queue for device {} which is not paired".format(
                            device_id
                        )
                    )
                else:
                    start = time.time()
                    try:
                        with self.registry_manager_lock:
                            self.registry_manager.send_c2d_message(device_id, message, props)
                    except Exception as e:
                        fail_count = outgoing_c2d.fail_count + 1

                        if fail_count <= self.config.send_c2d_retry_count:
                            logger.warning(
                                "send_c2d_messge to {} raised {}. Failure count={}. Trying again.".format(
                                    device_id, str(e) or type(e), fail_count
                                ),
                                exc_info=e,
                                extra=custom_props(device_id, device_data.run_id),
                            )
                            refresh_registry_manager = True
                            self.outgoing_c2d_queue.put(
                                outgoing_c2d._replace(fail_count=fail_count)
                            )
                        else:
                            logger.error(
                                "send_c2d_message to {} raised {}. Failure count={}. Forcing un-pair with device".format(
                                    device_id, str(e) or type(e), fail_count
                                ),
                                exc_info=e,
                                extra=custom_props(device_id, device_data.run_id),
                            )
                            self.device_list.remove(device_id)
                    else:
                        end = time.time()
                        if end - start > 2:
                            logger.warning(
                                "Send throttled.  Time delta={} seconds".format(end - start),
                                extra=custom_props(device_id, device_data.run_id),
                            )

    def handle_service_ack_request_thread(self):
        """
        Thread which is responsible for returning serviceAckResponse message to the
        device clients.  The various serviceAcks are collected in `outgoing_service_ack_response_queue`
        and this thread collects the serviceAcks into batches to send at a regular interval.  This
        batching is required because we send many serviceAck responses per second and IoTHub will throttle
        C2D events if we send too many.  Sending fewer big messages is better than sending fewer
        small messages.
        """

        while not self.done.isSet():
            reset_watchdog()

            service_acks = {}
            while True:
                try:
                    service_ack = self.outgoing_service_ack_response_queue.get_nowait()
                except queue.Empty:
                    break
                if service_ack.device_id not in service_acks:
                    service_acks[service_ack.device_id] = []
                # it's possible to get the same eventhub message twice, especially if we have to reconnect
                # to refresh credentials. Don't send the same service ack twice.
                if service_ack.service_ack_id not in service_acks[service_ack.device_id]:
                    service_acks[service_ack.device_id].append(service_ack.service_ack_id)

            for device_id in service_acks:

                device_data = self.device_list.try_get(device_id)

                if device_data:
                    logger.info(
                        "Send serviceAckResponse for device_id = {}: {}".format(
                            device_id, service_acks[device_id]
                        ),
                        extra=custom_props(device_id, device_data.run_id),
                    )

                    message = json.dumps(
                        {
                            Fields.THIEF: {
                                Fields.CMD: Commands.SERVICE_ACK_RESPONSE,
                                Fields.SERVICE_INSTANCE_ID: service_instance_id,
                                Fields.RUN_ID: device_data.run_id,
                                Fields.SERVICE_ACKS: service_acks[device_id],
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
            time.sleep(15)

    def handle_pairing_request(self, event):
        """
        Handle all device twin reported propreties under /thief/pairing.  If the change is
        interesting, the thread acts on it.  If not, it ignores it.
        """

        device_id = get_device_id_from_event(event)
        body = event.body_as_json()
        pairing = (
            body.get(Fields.PROPERTIES, {})
            .get(Fields.REPORTED, {})
            .get(Fields.THIEF, {})
            .get(Fields.PAIRING, {})
        )

        received_run_id = pairing.get(Fields.RUN_ID, None)
        requested_service_pool = pairing.get(Fields.REQUESTED_SERVICE_POOL, None)
        received_service_instance_id = pairing.get(Fields.SERVICE_INSTANCE_ID, None)

        logger.info(
            "Received pairing request for device {}: {}".format(device_id, pairing),
            extra=custom_props(device_id, received_run_id),
        )

        if received_run_id and requested_service_pool == service_pool:
            if not received_service_instance_id:
                # If the device hasn't selected a serviceInstanceId value yet, we will try to
                # pair with it.
                logger.info(
                    "Device {} attempting to pair".format(device_id),
                    extra=custom_props(device_id, received_run_id),
                )

                # Assume success.  Remove later if we don't pair.
                device_data = PerDeviceData(device_id, received_run_id)
                self.device_list.add(device_id, device_data)

                desired = {
                    Fields.THIEF: {
                        Fields.PAIRING: {
                            Fields.SERVICE_INSTANCE_ID: service_instance_id,
                            Fields.RUN_ID: received_run_id,
                        }
                    }
                }

                with self.registry_manager_lock:
                    self.registry_manager.update_twin(
                        device_id, Twin(properties=TwinProperties(desired=desired)), "*"
                    )

            elif received_service_instance_id == service_instance_id:
                # If the device has selected us, the pairing is complete.
                logger.info(
                    "Device {} pairing complete".format(device_id),
                    extra=custom_props(device_id, received_run_id),
                )

            else:
                # If the device paired with someone else, drop any per-device-data that
                # we might have
                logger.info(
                    "Device {} deviced to pair with service instance {}.".format(
                        device_id, received_service_instance_id
                    ),
                    extra=custom_props(device_id, received_run_id),
                )
                self.device_list.remove(device_id)

    def respond_to_test_content_properties(self, event):
        """
        Function to respond to changes to `testContent` reported properties.  `testContent`
        properties contain content, such as properties that contain random strings which are
        used to test various features.

        for `reportedPropertyTest` properties, this function will send serviceAckResponse messages to the
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
            if property_name.startswith("prop_"):
                property_value = reported_property_test[property_name]

                with device_data.reported_property_list_lock:
                    if property_value:
                        service_ack_id = property_value[Fields.ADD_SERVICE_ACK_ID]
                        device_data.reported_property_values[property_name] = property_value
                    else:
                        service_ack_id = device_data.reported_property_values[property_name][
                            Fields.REMOVE_SERVICE_ACK_ID
                        ]
                        del device_data.reported_property_values[property_name]

                self.outgoing_service_ack_response_queue.put(
                    ServiceAck(device_id=device_id, service_ack_id=service_ack_id)
                )

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

        with self.registry_manager_lock:
            logger.info("creating registry manager")
            self.registry_manager = IoTHubRegistryManager(iothub_connection_string)

        self.eventhub_consumer_client = EventHubConsumerClient.from_connection_string(
            eventhub_connection_string, consumer_group=eventhub_consumer_group
        )

        self.executor.submit(self.receive_incoming_messages_thread, critical=True)
        self.executor.submit(self.dispatch_twin_change_thread, critical=True)
        self.executor.submit(self.send_outgoing_c2d_messages_thread, critical=True)
        self.executor.submit(self.handle_service_ack_request_thread, critical=True)

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
