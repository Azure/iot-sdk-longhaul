# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.


class Const(object):
    JSON_CONTENT_TYPE = "application/json"
    JSON_CONTENT_ENCODING = "utf-8"
    JSON_TYPE_AND_ENCODING = {
        "contentType": "application/json",
        "contentEncoding": "utf-8",
    }
    PROPERTIES = "properties"
    REPORTED = "reported"


class Fields(object):
    class Telemetry(object):
        THIEF = "thief"
        CMD = "cmd"
        SERVICE_ACK_ID = "serviceAckId"
        SERVICE_INSTANCE = "serviceInstance"
        RUN_ID = "runId"

    class Reported(object):
        THIEF = "thief"
        SYSTEM_PROPERTIES = "systemProperties"
        SESSION_METRICS = "sessionMetrics"
        TEST_METRICS = "testMetrics"
        SYSTEM_HEALTH_METRICS = "systemHealthMetrics"
        CONFIG = "config"

        PAIRING = "pairing"

        class Pairing(object):
            REQUESTED_SERVICE_POOL = "requestedServicePool"
            SERVICE_INSTANCE = "serviceInstance"
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
        THIEF = "thief"

        PAIRING = "pairing"

        class Pairing(object):
            SERVICE_INSTANCE = "serviceInstance"
            RUN_ID = "runId"

    class C2d(object):
        THIEF = "thief"
        SERVICE_INSTANCE = "serviceInstance"
        RUN_ID = "runId"

        SERVICE_ACKS = "serviceAcks"
        CMD = "cmd"

        TEST_C2D_MESSAGE_INDEX = "testC2dMessageIndex"


class Types(object):
    class ServiceAck(object):
        TELEMETRY_SERVICE_ACK = "telemetry"
        ADD_REPORTED_PROPERTY_SERVICE_ACK = "add_reported"
        REMOVE_REPORTED_PROPERTY_SERVICE_ACK = "remove_reported"

    class Message(object):
        SERVICE_ACK_REQUEST = "serviceAckRequest"
        SERVICE_ACK_RESPONSE = "serviceAckResponse"
        TEST_C2D = "testC2d"


class Events(object):
    STARTING_RUN = "StartingRun"
    ENDING_RUN = "EndingRun"
    SENDING_PAIRING_REQUEST = "SendingPairingRequest"
    RECEIVED_PAIRING_RESPONSE = "ReceivedPairingResponse"
    PAIRING_COMPLETE = "PairingComplete"


class MetricNames(object):
    # ---------------------
    # System Health metrics
    # ---------------------
    PROCESS_CPU_PERCENT = "processCpuPercent"
    PROCESS_WORKING_SET = "processWorkingSet"
    PROCESS_BYTES_IN_ALL_HEAPS = "processBytesInAllHeaps"
    PROCESS_PRIVATE_BYTES = "processPrivateBytes"
    PROCESS_WORKING_SET_PRIVATE = "processWorkingSetPrivate"

    # --------------------
    # SendMesssage metrics
    # --------------------
    SEND_MESSAGE_COUNT_SENT = "sendMessageCountSent"
    SEND_MESSAGE_COUNT_IN_BACKLOG = "sendMessaageCountInBacklog"
    SEND_MESSAGE_COUNT_UNACKED = "sendMessageCountUnacked"
    SEND_MESSAGE_COUNT_NOT_RECEIVED = "sendMessageCountNotReceivedByServiceApp"
    SEND_MESSAGE_COUNT_FAILURES = "sendMessageCountFailures"

    # -------------------
    # Receive c2d metrics
    # -------------------
    RECEIVE_C2D_COUNT_RECEIVED = "receiveC2dCountReceived"
    RECEIVE_C2D_COUNT_MISSING = "receiveC2dCountMissing"

    # -------------------------
    # Reported property metrics
    # -------------------------
    REPORTED_PROPERTIES_COUNT_ADDED = "reportedPropertiesCountAdded"
    REPORTED_PROPERTIES_COUNT_ADDED_NOT_VERIFIED = (
        "reportedPropertiesCountAddedButNotVerifiedByServiceApp"
    )
    REPORTED_PROPERTIES_REMOVED = "reportedPropertiesCountRemoved"
    REPORTED_PROPERTIES_REMOVED_NOT_VERIFIED = (
        "reportedPropertiesCountRemovedButNotVerifiedbyServiceApp"
    )

    # ---------------
    # Latency metrics
    # ---------------
    LATENCY_QUEUE_MESSAGE_TO_SEND = "latencyQueueMessageToSendInMilliseconds"
    LATENCY_SEND_MESSAGE_TO_SERVICE_ACK = "latencySendMessageToServiceAckInSeconds"
    LATENCY_ADD_REPORTED_PROPERTY_TO_SERVICE_ACK = "latencyAddReportedPropertyToServiceAckInSeconds"
    LATENCY_REMOVE_REPORTED_PROPERTY_TO_SERVICE_ACK = (
        "latencyRemoveReportedPropertyToServiceAckInSeconds"
    )
    LATENCY_BETWEEN_C2D = "latencyBetweenC2dInSeconds"
