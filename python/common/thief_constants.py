# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.


class Const(object):
    """
    Generic constants that don't have another home
    """

    JSON_CONTENT_TYPE = "application/json"
    JSON_CONTENT_ENCODING = "utf-8"
    JSON_TYPE_AND_ENCODING = {"contentType": "application/json", "contentEncoding": "utf-8"}


class Fields(object):
    """
    Names of fields inside telemetry messages and twins
    """

    THIEF = "thief"
    PROPERTIES = "properties"
    REPORTED = "reported"
    DESIRED = "desired"

    # -----------------
    # Test run progress
    # -----------------

    # Start of the run in UTC time
    RUN_START_UTC = "runStartUtc"

    # Latest metric update in UTC time
    LATEST_UPDATE_TIME_UTC = "latestUpdateTimeUtc"

    # Elapsed test time
    ELAPSED_TIME = "elapsedTime"

    # State of the run: Running, Failed, etc
    RUN_STATE = "runState"

    # Reason the text exited
    EXIT_REASON = "exitReason"

    # ---------
    # Telemetry
    # ---------
    CMD = "cmd"
    SERVICE_ACK_ID = "serviceAckId"
    SERVICE_INSTANCE_ID = "serviceInstanceId"
    RUN_ID = "runId"
    DESIRED_PROPERTIES = "desiredProperties"

    # -------------------------
    # properties.reported.thief
    # -------------------------
    SYSTEM_PROPERTIES = "systemProperties"
    SESSION_METRICS = "sessionMetrics"
    TEST_METRICS = "testMetrics"
    SYSTEM_HEALTH_METRICS = "systemHealthMetrics"
    CONFIG = "config"
    PAIRING = "pairing"
    TEST_CONTROL = "testControl"
    TEST_CONTENT = "testContent"
    EXIT_REASON = "exitReason"

    # ---------------------------------
    # properties.reported.thief.pairing
    # ---------------------------------
    REQUESTED_SERVICE_POOL = "requestedServicePool"
    SERVICE_INSTANCE_ID = "serviceInstanceId"
    RUN_ID = "runId"

    # -------------------------------------
    # properties.reported.thief.testContent
    # -------------------------------------
    REPORTED_PROPERTY_TEST = "reportedPropertyTest"

    # ----------------------------------------------------------
    # properties.reported.thief.testContent.reportedPropertytest
    # ----------------------------------------------------------
    ADD_SERVICE_ACK_ID = "addServiceAckId"
    REMOVE_SERVICE_ACK_ID = "removeServiceAckId"

    # ------------------------
    # properties.desired.thief
    # ------------------------
    PAIRING = "pairing"
    TEST_CONTENT = "testContent"

    # -------------------------------
    # propeties.desired.thief.pairing
    # -------------------------------
    SERVICE_INSTANCE_ID = "serviceInstanceId"
    RUN_ID = "runId"

    # -----------------------------------
    # propeties.desired.thief.testContent
    # -----------------------------------
    TWIN_GUID = "twinGuid"

    # -----------------------------------
    # Names of fields inside c2d messages
    # -----------------------------------
    SERVICE_INSTANCE_ID = "serviceInstanceId"
    RUN_ID = "runId"
    SERVICE_ACKS = "serviceAcks"
    CMD = "cmd"

    # payload used for testing C2d Messages
    TEST_C2D_PAYLOAD = "testC2dPayload"

    # ----------------------------------------------------
    # Fields inside telemetry messages for testing methods
    # ----------------------------------------------------

    # Name of method to invoke
    METHOD_NAME = "methodName"

    # Payload to send with method invocation
    METHOD_INVOKE_PAYLOAD = "methodInvokePayload"

    # timeout for receiving a response from a method invoke
    METHOD_INVOKE_RESPONSE_TIMEOUT_IN_SECONDS = "methodInvokeResponseTimeoutInSeconds"

    # timeout for connecting a client based on a method invoke
    METHOD_INVOKE_CONNECT_TIMEOUT_IN_SECONDS = "methodInvokeConnectTimeoutInSeconds"

    # ---------------------------------------------------
    # Fields inside C2D messages used for testing methods
    # ---------------------------------------------------

    # Payload sent with method response
    METHOD_RESPONSE_PAYLOAD = "methodResponsePayload"

    # Status code sent with method response
    METHOD_RESPONSE_STATUS_CODE = "methodResponseStatusCode"


class Commands(object):
    """
    Names for different command/message types
    """

    # ------------------------------------------------------
    # Values for the command field inside telemetry messages
    # ------------------------------------------------------

    # Request a serviceAckResposne message from the service
    SERVICE_ACK_REQUEST = "serviceAckRequest"

    # Apply a the device twin desired properties patch
    SET_DESIRED_PROPS = "setDesiredProps"

    # Invoke a direct method
    INVOKE_METHOD = "invokeMethod"

    # Send C2d Message
    SEND_C2D = "sendC2d"

    # ------------------------------------------------
    # Values for the command field inside c2d messages
    # ------------------------------------------------

    # Response from one or more serviceAckRequest messsages
    SERVICE_ACK_RESPONSE = "serviceAckResponse"

    # C2d test messaage - a respnse to a SEND_C2D request
    C2D_RESPONSE = "c2dResponse"

    # Result of a direct method invocation
    METHOD_RESPONSE = "methodResponse"


class Events(object):
    """
    Names of different Azure Monitor events
    """

    # The test run is starting
    STARTING_RUN = "StartingRun"

    # The test run is ending
    ENDING_RUN = "EndingRun"

    # The device app is sending a pairing request to the service app
    SENDING_PAIRING_REQUEST = "SendingPairingRequest"

    # The device app has received a pairing response from the service app
    RECEIVED_PAIRING_RESPONSE = "ReceivedPairingResponse"

    # The pairing process is complete.
    PAIRING_COMPLETE = "PairingComplete"


class Metrics(object):
    """
    Names of metrics which are pushed via reported properties, telemetry, and Azure Monitor
    """

    # ---------------------
    # System Health metrics
    # ---------------------

    # CPU use for the device app, as a percentage of all cores
    PROCESS_CPU_PERCENT = "processCpuPercent"

    # Working set for the device app, includes shared and private, read-only and writeable memory
    PROCESS_WORKING_SET_BYTES = "processWorkingSet"

    # Amount of private data used by the process
    PROCESS_WORKING_SET_PRIVATE_BYTES = "processWorkingSetPrivate"

    # Number of active objects being managed by the garbage collector
    PROCESS_GARBAGE_COLLECTION_OBJECTS = "processGarbageCollectionObjects"

    # number of threads being used by the current SDK
    PROCESS_SDK_THREADS = "processSdkThreads"

    # number of active threads in the test app receive threadpool
    TEST_APP_ACTIVE_RECEIVE_THREADS = "testAppActiveReceiveThreads"

    # number of active threads in the test app send threadpool
    TEST_APP_ACTIVE_SEND_THREADS = "testAppActiveSendThreads"

    # ----------------
    # test app metrics
    # ----------------

    # Number of (non-fatal) exceptions raised by the client library or test code
    EXCEPTION_COUNT = "exceptionCount"

    # --------------------
    # SendMesssage metrics
    # --------------------

    # Number of telemetry messages sent
    SEND_MESSAGE_COUNT_SENT = "sendMessageCountSent"

    # Number of telemetry messages sent and verified by the service
    SEND_MESSAGE_COUNT_VERIFIED = "sendMessageCountVerified"

    # Number of telemetry messages that timed out with no response from the service
    SEND_MESSAGE_COUNT_TIMED_OUT = "sendMessageCountTimedOut"

    # -------------------
    # Receive c2d metrics
    # -------------------

    # Number of c2d messages received
    RECEIVE_C2D_COUNT_RECEIVED = "receiveC2dCountReceived"

    # Number of c2d messages not received in time
    RECEIVE_C2D_COUNT_TIMED_OUT = "receiveC2dCountTimedOut"

    # -------------------------
    # Reported property metrics
    # -------------------------

    # Number of reported properties which have been added
    REPORTED_PROPERTIES_COUNT_ADDED = "reportedPropertiesCountAdded"

    # Number of reported properties which have been removed
    REPORTED_PROPERTIES_COUNT_REMOVED = "reportedPropertiesCountRemoved"

    # Number of reported property add & remove operations that timed out
    REPORTED_PROPERTIES_COUNT_TIMED_OUT = "reportedPropertiesCountTimedOut"

    # ----------------
    # Get-twin metrics
    # ----------------

    # Number of times get_twin successfully verified a property update
    GET_TWIN_COUNT_SUCCEEDED = "getTwinCountSucceeded"

    # Number of times get_twin was unable to verify a property update
    GET_TWIN_COUNT_TIMED_OUT = "getTwinCountTimedOut"

    # ------------------------------
    # desired property patch metrics
    # ------------------------------

    # Count of desired property patches that were successfully received
    DESIRED_PROPERTY_PATCH_COUNT_RECEIVED = "desiredPropertyPatchCountReceived"

    # Count of desired property patches that were not received
    DESIRED_PROPERTY_PATCH_COUNT_TIMED_OUT = "desiredPropertyPatchCountTimedOut"

    # ---------------------
    # method invoke metrics
    # ---------------------

    # Number of method invoke requests received
    METHOD_INVOKE_COUNT_REQUEST_RECEIVED = "methodInvokeCountRequestReceived"

    # Number of method invoke requests timed out
    METHOD_INVOKE_COUNT_REQUEST_TIMED_OUT = "methodInvokeCountRequestTimedOut"

    # ---------------
    # Latency metrics
    # ---------------

    # Number of milliseconds between queueing a telemetry message and actually sending it
    LATENCY_QUEUE_MESSAGE_TO_SEND = "latencyQueueMessageToSendInMilliseconds"


class SystemProperties(object):
    """
    Properties for the system runnin the test
    """

    # Language of the app running the test (Python, Node, etc)
    LANGUAGE = "language"

    # Version of the language running the test (3.6, 3.7, etc)
    LANGUAGE_VERSION = "languageVersion"

    # Version of the SDK that the test is using
    SDK_VERSION = "sdkVersion"

    # Github repo with the SDK code that the test is using
    SDK_GITHUB_REPO = "sdkGithubRepo"

    # Branch in the github repo with the SDK code that the test is using
    SDK_GITHUB_BRANCH = "sdkGithubBranch"

    # Commit SHA for the commit in the github repo that the test is using
    SDK_GITHUB_COMMIT = "sdkGithubCommit"

    # Type of OS: Linux, Windows, etc
    OS_TYPE = "osType"

    # Specific OS release being used
    OS_RELEASE = "osRelease"


class Settings(object):
    """
    Names of thief settings which are used to configure the device app for a test run
    """

    # how long should the test run before finishing.  0 = forever
    MAX_RUN_DURATION_IN_SECONDS = "maxRunDurationInSeconds"

    # How many exceptions do we allow before we fail the test?
    ALLOWED_EXCEPTION_COUNT = "allowedExceptionCount"

    # How many seconds between tests
    INTER_TEST_DELAY_INTERVAL_IN_SECONDS = "interTestDelayIntervalInSeconds"

    # Generic value for operation timeouts
    OPERATION_TIMEOUT_IN_SECONDS = "operationTimeoutInSeconds"

    # How many timeouts are allowed before the test fails
    OPERATION_TIMEOUT_ALLOWED_FAILURE_COUNT = "operationTimeoutAllowedFailureCount"

    # interval (in seconds) for sending PINGREQ packets on quiet MQTT connections
    MQTT_KEEP_ALIVE_INTERVAL = "mqttKeepAliveInterval"

    # interval (in seconds) for renewing SAS tokens
    SAS_TOKEN_RENEWAL_INTERVAL = "sasTokenRenewalInterval"

    # maximum number of send threads in the test app
    MAX_TEST_SEND_THREADS = "maxTestSendThreads"

    # maximum number of receive threads in the test app
    MAX_TEST_RECEIVE_THREADS = "maxTestReceiveThreads"

    # ----------------
    # pairing settings
    # ----------------

    # How long to keep trying to pair with a service instance before giving up
    PAIRING_REQUEST_TIMEOUT_INTERVAL_IN_SECONDS = "pairingRequestTimeoutIntervalInSeconds"

    # How many seconds to wait while pairing before trying to pair again
    PAIRING_REQUEST_SEND_INTERVAL_IN_SECONDS = "pairingRequestSendIntervalInSeconds"

    # ---------------------
    # send_message settings
    # ---------------------

    # How many times to call send_message per second
    SEND_MESSAGE_OPERATIONS_PER_SECOND = "sendMessageOperationsPerSecond"


class CustomDimensions(object):
    """
    Names of customDimension fields pushed to Azure Monitor
    """

    # OS type, e.g. Linux, Windows
    OS_TYPE = "osType"

    # Language being used.  e.g. Python, Node, dotnet
    SDK_LANGUAGE = "sdkLanguage"

    # Version of language being used.  e.g. 3.8.1
    SDK_LANGUAGE_VERSION = "sdkLanguageVersion"

    # Version of the SDK library being tested.  e.g. 2.4.2
    SDK_VERSION = "sdkVersion"

    # ServiceInstanceId being used for this test run
    SERVICE_INSTANCE_ID = "serviceInstanceId"

    # RunId for the run.  May be None for service app features that aren't tied to a specific run
    RUN_ID = "runId"

    # Service app pool being used
    POOL_ID = "poolId"

    # Hub instance being used, without the .azuredevices.net suffix
    HUB = "hub"

    # Device being tested
    DEVICE_ID = "deviceId"

    # Transport being used by the device under test
    TRANSPORT = "transport"

    # Reason the test is running
    RUN_REASON = "runReason"

    # Reason the test is exiting
    EXIT_REASON = "exitReason"


class MethodNames(object):
    """
    Names of vaious methods used while testing direct methods
    """

    # Fail with status 404 and verify that it returns the error to the caller.
    FAIL_WITH_404 = "failWith404"

    # echo the request as the resopnse with a 200 return code
    ECHO_REQUEST = "echoRequest"

    # method name which is not handled by the device client.
    UNDEFINED_METHOD_NAME = "undefinedMethodName"


class RunStates(object):
    """
    Enum to report run states
    """

    # Test app has not started
    WAITING = "Waiting"

    # Test app is currently running
    RUNNING = "Running"

    # Test run has failed
    FAILED = "Failed"

    # Test run has completed successfully
    COMPLETE = "Complete"

    # Test run was interrupted
    INTERRUPTED = "Interrupted"
