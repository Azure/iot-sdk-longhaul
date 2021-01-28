# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.


class Const(object):
    """
    Generic constants that don't have another home
    """

    JSON_CONTENT_TYPE = "application/json"
    JSON_CONTENT_ENCODING = "utf-8"
    JSON_TYPE_AND_ENCODING = {
        "contentType": "application/json",
        "contentEncoding": "utf-8",
    }
    PROPERTIES = "properties"
    REPORTED = "reported"


class Fields(object):
    """
    Names of fields inside telemetry, c2d, and device twins
    """

    class Telemetry(object):
        """
        Names of fields inside telemetry messages
        """

        THIEF = "thief"
        CMD = "cmd"
        SERVICE_ACK_ID = "serviceAckId"
        SERVICE_INSTANCE_ID = "serviceInstanceId"
        RUN_ID = "runId"

    class Reported(object):
        """
        Names of fields inside reported properties
        """

        THIEF = "thief"
        SYSTEM_PROPERTIES = "systemProperties"
        SESSION_METRICS = "sessionMetrics"
        TEST_METRICS = "testMetrics"
        SYSTEM_HEALTH_METRICS = "systemHealthMetrics"
        CONFIG = "config"

        PAIRING = "pairing"

        class Pairing(object):
            REQUESTED_SERVICE_POOL = "requestedServicePool"
            SERVICE_INSTANCE_ID = "serviceInstanceId"
            RUN_ID = "runId"

        TEST_CONTENT = "testContent"

        class TestContent(object):
            REPORTED_PROPERTY_TEST = "reportedPropertyTest"

            class ReportedPropertyTest(object):
                ADD_SERVICE_ACK_ID = "addServiceAckId"
                REMOVE_SERVICE_ACK_ID = "removeServiceAckId"

        TEST_CONTROL = "testControl"

        class TestControl(object):
            C2D = "c2d"

            class C2d(object):
                SEND = "send"
                MESSAGE_INTERVAL_IN_SECONDS = "messageIntervalInSeconds"

    class Desired(object):
        """
        Names of fields inside desired properties
        """

        THIEF = "thief"

        PAIRING = "pairing"

        class Pairing(object):
            SERVICE_INSTANCE_ID = "serviceInstanceId"
            RUN_ID = "runId"

    class C2d(object):
        """
        Names of fields inside c2d messages
        """

        THIEF = "thief"
        SERVICE_INSTANCE_ID = "serviceInstanceId"
        RUN_ID = "runId"

        SERVICE_ACKS = "serviceAcks"
        CMD = "cmd"

        TEST_C2D_MESSAGE_INDEX = "testC2dMessageIndex"


class Types(object):
    """
    Names for different types
    """

    class ServiceAck(object):
        """
        Names of different types of serviceAck messages
        """

        TELEMETRY_SERVICE_ACK = "telemetry"
        ADD_REPORTED_PROPERTY_SERVICE_ACK = "add_reported"
        REMOVE_REPORTED_PROPERTY_SERVICE_ACK = "remove_reported"

    class Message(object):
        """
        Names of different types of messsages
        """

        SERVICE_ACK_REQUEST = "serviceAckRequest"
        SERVICE_ACK_RESPONSE = "serviceAckResponse"
        TEST_C2D = "testC2d"


class Events(object):
    """
    Names of different Azure Monitor events
    """

    STARTING_RUN = "StartingRun"
    ENDING_RUN = "EndingRun"
    SENDING_PAIRING_REQUEST = "SendingPairingRequest"
    RECEIVED_PAIRING_RESPONSE = "ReceivedPairingResponse"
    PAIRING_COMPLETE = "PairingComplete"


class MetricNames(object):
    """
    Names of metrics which are pushed via reported properties, telemetry, and Azure Monitor
    """

    # ---------------------
    # System Health metrics
    # ---------------------

    # CPU use for the device app, as a percentage of all cores
    PROCESS_CPU_PERCENT = "processCpuPercent"
    # Working set for the device app, includes shared and private, read-only and writeable memory
    PROCESS_WORKING_SET = "processWorkingSet"
    # Size of all heaps for the device app, essentially "all available memory"
    PROCESS_BYTES_IN_ALL_HEAPS = "processBytesInAllHeaps"
    # Amount of private data used by the process
    PROCESS_PRIVATE_BYTES = "processPrivateBytes"
    # Amount of private data used by the process
    PROCESS_WORKING_SET_PRIVATE = "processWorkingSetPrivate"

    # ----------------
    # test app metrics
    # ----------------

    # Number of exceptions raised by the client library or libraries
    CLIENT_LIBRARY_COUNT_EXCEPTIONS = "clientLibraryCountExceptions"

    # --------------------
    # SendMesssage metrics
    # --------------------

    # Number of telemetry messages sent
    SEND_MESSAGE_COUNT_SENT = "sendMessageCountSent"
    # Number of telemetry messages queued, and waiting to be sent
    SEND_MESSAGE_COUNT_IN_BACKLOG = "sendMessageCountInBacklog"
    # Number of telemetry messages sent, but not acknowledged (PUBACK'ed) by the transport
    SEND_MESSAGE_COUNT_UNACKED = "sendMessageCountUnacked"
    # Number of telemetry messages that have not (yet) arrived at the hub
    SEND_MESSAGE_COUNT_NOT_RECEIVED = "sendMessageCountNotReceivedByServiceApp"
    # Number of "extra" service acks received -- probably duplicte messages
    SEND_MESSAGE_COUNT_EXTRA_SERVICE_ACKS_RECEIVED = "sendMessageCountExtraServiceAcksReceived"

    # -------------------
    # Receive c2d metrics
    # -------------------

    # Number of c2d messages received
    RECEIVE_C2D_COUNT_RECEIVED = "receiveC2dCountReceived"
    # Number of c2d messages not received
    RECEIVE_C2D_COUNT_MISSING = "receiveC2dCountMissing"

    # -------------------------
    # Reported property metrics
    # -------------------------

    # Number of reported properites which have been added
    REPORTED_PROPERTIES_COUNT_ADDED = "reportedPropertiesCountAdded"
    # Number of reported properties which have been added, but the add was not verified by the service app
    REPORTED_PROPERTIES_COUNT_ADDED_NOT_VERIFIED = (
        "reportedPropertiesCountAddedButNotVerifiedByServiceApp"
    )
    # Number of reported properties which have been removed
    REPORTED_PROPERTIES_REMOVED = "reportedPropertiesCountRemoved"
    # Number of reported properties which have been removed, but the removal was not verified by the service app
    REPORTED_PROPERTIES_REMOVED_NOT_VERIFIED = (
        "reportedPropertiesCountRemovedButNotVerifiedbyServiceApp"
    )

    # ---------------
    # Latency metrics
    # ---------------

    # Number of milliseconds between queueing a telemetry message and actually sending it
    LATENCY_QUEUE_MESSAGE_TO_SEND = "latencyQueueMessageToSendInMilliseconds"
    # Number of seconds between sending a telemetry message and receiving the verification from the service app
    LATENCY_SEND_MESSAGE_TO_SERVICE_ACK = "latencySendMessageToServiceAckInSeconds"
    # Number of seconds between adding a reported property and receiving verification of the add from the service app
    LATENCY_ADD_REPORTED_PROPERTY_TO_SERVICE_ACK = "latencyAddReportedPropertyToServiceAckInSeconds"
    # Number of seconds between removing a reported property and receiving verification of the removal from the service app
    LATENCY_REMOVE_REPORTED_PROPERTY_TO_SERVICE_ACK = (
        "latencyRemoveReportedPropertyToServiceAckInSeconds"
    )
    # Number of seconds between consecutive c2d messages
    LATENCY_BETWEEN_C2D = "latencyBetweenC2dInSeconds"


class DeviceSettings(object):
    """
    Names of thief settings which are used to configure the device app for a test run
    """

    # how long should the test run before finishing.  0 = forever
    THIEF_MAX_RUN_DURATION_IN_SECONDS = "thiefMaxRunDurationInSeconds"
    # How often do we update thief reported properties (with metrics)
    THIEF_PROPERTY_UPDATE_INTERVAL_IN_SECONDS = "thiefPropertyUpdateIntervalInSeconds"
    # How long can a thread go without updating its watchdog before failing
    THIEF_WATCHDOG_FAILURE_INTERVAL_IN_SECONDS = "thiefWatchdogFailureIntervalInSeconds"
    # How many client exceptions do we allow before we fail the test?
    THIEF_ALLOWED_CLIENT_LIBRARY_EXCEPTION_COUNT = "thiefAllowedClientLibraryExceptionCount"

    # How long to keep trying to pair with a service instance before giving up
    PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS = "pairingRequestTimeoutIntervalInSeconds"
    # How many seconds to wait while pairing before trying to pair again
    PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS = "pairingRequestSendIntervalInSeconds"

    # How many times to call send_message per second
    SEND_MESSAGE_OPERATIONS_PER_SECOND = "sendMessageOperationsPerSecond"
    # How many threads do we spin up for overlapped send_message calls
    SEND_MESSAGE_THREAD_COUNT = "sendMessageThreadCount"
    # How many messages fail to arrive at the service before we fail the test
    SEND_MESSAGE_ALLOWED_FAILURE_COUNT = "sendMessageAllowedFailureCount"

    # How often do we want the service to send test C2D messages?
    RECEIVE_C2D_INTERVAL_IN_SECONDS = "receiveC2dIntervalInSeconds"
    # How many missing C2D messages will cause the test to fail?
    RECEIVE_C2D_ALLOWED_MISSING_MESSAGE_COUNT = "receiveC2dAllowedMissingMessageCount"

    # How many seconds between reported property patches
    REPORTED_PROPERTIES_UPDATE_INTERVAL_IN_SECONDS = "reportedPropertiesUpdateIntervalInSeconds"
    # How many reported property patches are allowed to fail before we fail the test
    REPORTED_PROPERTIES_UPDATE_ALLOWED_FAILURE_COUNT = "reportedPropertiesUpdateAllowedFailureCount"


class CustomDimensionNames(object):
    """
    Names of customDimension fields pushed to Azure Monitor
    """

    OS_TYPE = "osType"
    SDK_LANGUAGE = "sdkLanguage"
    SDK_LANGUAGE_VERSION = "sdkLanguageVersion"
    SDK_VERSION = "sdkVersion"

    SERVICE_INSTANCE_ID = "serviceInstanceId"
    RUN_ID = "runId"
    POOL_ID = "poolId"

    HUB = "hub"
    DEVICE_ID = "deviceId"
    TRANSPORT = "transport"
