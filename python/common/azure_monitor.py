# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import os
import logging
import platform
from thief_constants import CustomDimensionNames
from opencensus.ext.azure.log_exporter import AzureEventHandler
from opencensus.ext.azure.log_exporter import AzureLogHandler

app_insights_instrumentation_key = os.environ["THIEF_APP_INSIGHTS_INSTRUMENTATION_KEY"]
app_insights_connection_string = "InstrumentationKey={}".format(app_insights_instrumentation_key)

_client_type = None
_service_instance_id = None
_run_id = None
_hub = None
_sdk_version = None
_device_id = None
_pool_id = None
_transport = None


def _default_value():
    """
    use a function to represent a unique value.
    """
    pass


def add_logging_properties(
    client_type=_default_value,
    run_id=_default_value,
    hub=_default_value,
    sdk_version=_default_value,
    device_id=_default_value,
    service_instance_id=_default_value,
    pool_id=_default_value,
    transport=_default_value,
):
    """
    Add customDimension values which will be applied to all Azure Monitor records
    """
    global _client_type, _run_id, _hub, _sdk_version, _device_id, _pool_id, _transport, _service_instance_id
    if client_type != _default_value:
        _client_type = client_type
    if run_id != _default_value:
        _run_id = run_id
    if hub != _default_value:
        _hub = hub
    if sdk_version != _default_value:
        _sdk_version = sdk_version
    if device_id != _default_value:
        _device_id = device_id
    if service_instance_id != _default_value:
        _service_instance_id = service_instance_id
    if pool_id != _default_value:
        _pool_id = pool_id
    if transport != _default_value:
        _transport = transport


def telemetry_processor_callback(envelope):
    """
    Get a callback which applies our customDimension values to records which will eventually be
    sent to Azure Monitor.
    """
    global _client_type, _run_id, _hub, _sdk_version, _device_id, _pool_id, _transport
    envelope.tags["ai.cloud.role"] = _client_type
    if _service_instance_id:
        envelope.tags["ai.cloud.roleInstance"] = _service_instance_id
    else:
        envelope.tags["ai.cloud.roleInstance"] = _run_id
    envelope.data.baseData.properties[CustomDimensionNames.OS_TYPE] = platform.system()
    if _device_id:
        envelope.data.baseData.properties[CustomDimensionNames.DEVICE_ID] = _device_id
    if _hub:
        envelope.data.baseData.properties[CustomDimensionNames.HUB] = _hub
    if _run_id:
        envelope.data.baseData.properties[CustomDimensionNames.RUN_ID] = _run_id
    if _service_instance_id:
        envelope.data.baseData.properties[
            CustomDimensionNames.SERVICE_INSTANCE_ID
        ] = _service_instance_id
    envelope.data.baseData.properties[CustomDimensionNames.SDK_LANGUAGE] = "python"

    envelope.data.baseData.properties[
        CustomDimensionNames.SDK_LANGUAGE_VERSION
    ] = platform.python_version()
    envelope.data.baseData.properties[CustomDimensionNames.SDK_VERSION] = _sdk_version
    if _transport:
        envelope.data.baseData.properties[CustomDimensionNames.TRANSPORT] = _transport

    if _pool_id:
        envelope.data.baseData.properties[CustomDimensionNames.POOL_ID] = _pool_id

    return True


def get_event_logger():
    """
    Get the event logger for this module.  This event logger can be used to send customEvents to
    Azure Monitor.
    """
    global _client_type
    logger = logging.getLogger("thief_events.{}".format(_client_type))

    handler = AzureEventHandler(connection_string=app_insights_connection_string)
    handler.add_telemetry_processor(telemetry_processor_callback)

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    return logger


def log_all_warnings_and_exceptions_to_azure_monitor():
    """
    Log all WARNING, ERROR, and CRITICAL messages to Azure Monitor, regardless of the module that
    produced them and any logging levels set in other loggers.
    """
    always_log_handler = AzureLogHandler(connection_string=app_insights_connection_string)
    always_log_handler.add_telemetry_processor(telemetry_processor_callback)
    always_log_handler.setLevel(level=logging.WARNING)
    logging.getLogger(None).addHandler(always_log_handler)


log_handler = None


def log_to_azure_monitor(logger_name):
    """
    Log all messages sent to a specific logger to Azure Monitor
    """
    global log_handler

    if not log_handler:
        log_handler = AzureLogHandler(connection_string=app_insights_connection_string)
        log_handler.add_telemetry_processor(telemetry_processor_callback)

    logging.getLogger(logger_name).addHandler(log_handler)
