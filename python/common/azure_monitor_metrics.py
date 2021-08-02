# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import thief_secrets
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from opencensus.tags import tag_map as tag_map_module
import azure_monitor

stats = stats_module.stats
view_manager = stats.view_manager
stats_recorder = stats.stats_recorder

app_insights_instrumentation_key = thief_secrets.APP_INSIGHTS_INSTRUMENTATION_KEY
if app_insights_instrumentation_key:
    app_insights_connection_string = "InstrumentationKey={}".format(
        app_insights_instrumentation_key
    )
else:
    app_insights_connection_string = None


def json_name_to_metric_name(metric_name):
    # Change first character to upper case:
    # e.g. metricName -> MetricName
    return metric_name[:1].upper() + metric_name[1:]


class MetricsReporter(object):
    def __init__(self):
        if app_insights_connection_string:
            self.exporter = metrics_exporter.new_metrics_exporter(
                connection_string=app_insights_connection_string, enable_standard_metrics=False,
            )
            self.exporter.add_telemetry_processor(azure_monitor.telemetry_processor_callback)
            view_manager.register_exporter(self.exporter)
            self.mmap = stats_recorder.new_measurement_map()
            self.tmap = tag_map_module.TagMap()
            self.metrics = {}

    def add_integer_measurement(self, json_name, description, units):
        """
        Add a measurement for an integer value
        """
        if app_insights_connection_string:
            metric_name = json_name_to_metric_name(json_name)

            new_measure = measure_module.MeasureInt(metric_name, description, units)
            new_view = view_module.View(
                metric_name, description, [], new_measure, aggregation_module.LastValueAggregation()
            )
            view_manager.register_view(new_view)

            def new_setter(value):
                self.mmap.measure_int_put(new_measure, value)

            self.metrics[json_name] = new_setter

    def add_float_measurement(self, json_name, description, units):
        """
        Add a measurement for a float value
        """
        if app_insights_connection_string:
            metric_name = json_name_to_metric_name(json_name)

            new_measure = measure_module.MeasureFloat(metric_name, description, units)
            new_view = view_module.View(
                metric_name, description, [], new_measure, aggregation_module.LastValueAggregation()
            )
            view_manager.register_view(new_view)

            def new_setter(value):
                self.mmap.measure_float_put(new_measure, value)

            self.metrics[json_name] = new_setter

    def set_metrics_from_dict(self, metrics):
        """
        Given a dict with metrics, indexed by json name, record measurements using the
        appropriate metric name
        """
        if app_insights_connection_string:
            for key in metrics:
                self.set_metric(key, metrics[key])

    def set_metric(self, key, value):
        """
        Set the value of an individual metric
        """
        if app_insights_connection_string:
            setter = self.metrics[key]
            setter(value)

    def record(self):
        if app_insights_connection_string:
            self.mmap.record(self.tmap)
