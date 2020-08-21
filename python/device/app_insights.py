# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
from dictionary_object import SimpleObject, DictionaryObject
from opencensus.stats import measure as measure_module

from opencensus.tags.tag_key import TagKey
from opencensus.tags.tag_map import TagMap
from opencensus.tags.tag_value import TagValue
from opencensus.stats.stats_recorder import StatsRecorder
from opencensus.stats.view_manager import ViewManager
from opencensus.stats.view import View
from opencensus.stats.aggregation import SumAggregation, LastValueAggregation
from opencensus.ext.azure import metrics_exporter

# opencensus is the open standard that Azure Monitor uses for metrics.  Most of our interaction
# is with the opencensus library, except for the metrics_exporter module which is Azure specific.
# Thus, we use lots of opencensus code and we end up learning all kinds of things about opencensus.

# The tag map is the list of all possible values that we might pivot our metrics on.
# The values in here are just temporary while we figure out how we want to explore data
# on the back end.  At the very least, we need some sort of "run id" that we can use to
# drill down into a specific run of the tests
tmap = TagMap()
tmap.insert(TagKey("device_id"), TagValue("fake_device_id"))

# dimensions are the set of tags that we actually attach to the data that we're pushing up.
dimensions = ["device_id"]

# The Metrics object is our own thing that we use to hold the integers and floats that we're
# going to push up.

# TODO: This is DictionaryObject to support to_dict for debug string.  Make into SimpleObject?


class D2cMetrics(DictionaryObject):
    def __init__(self):
        super(D2cMetrics, self).__init__()
        self.d2c_roundtrip_latency = None
        self.d2c_in_flight_count = None
        self.d2c_succeeded_count = None
        self.d2c_failed_count = None
        self.d2c_waiting_to_verify_count = None
        self.d2c_verified_count = None
        self.freeze_attributes()


# Measures are the opencensus objects which hold the measurements that we want to publish.  You
# can think of MeasureFloat and MeasureInt as wrappers around the floats and ints above which add
# metadata about what we're measuring.
class D2cMeasures(SimpleObject):
    def __init__(self):
        super(D2cMeasures, self).__init__()
        self.d2c_roundtrip_latency = measure_module.MeasureFloat(
            "d2c_roundtrip_latency", "average d2c roundtrip latency", "s"
        )
        self.d2c_in_flight_count = measure_module.MeasureInt(
            "d2c_in_flight_count", "number of messages currently in flight", "messages"
        )
        self.d2c_succeeded_count = measure_module.MeasureInt(
            "d2c_succeeded_count",
            "number of messages that succeeded since last measurement",
            "messages",
        )
        self.d2c_failed_count = measure_module.MeasureInt(
            "d2c_failed_count",
            "number of messages that verified since last measurement",
            "messages",
        )
        self.d2c_waiting_to_verify_count = measure_module.MeasureInt(
            "d2c_waiting_to_verify_count",
            "number of messages currently waiting to be verified",
            "messages",
        )
        self.d2c_verified_count = measure_module.MeasureInt(
            "d2c_verified_count",
            "number of messages that were verified since last measurement",
            "messages",
        )
        self.freeze_attributes()


# Views are used to define how we want to aggregate opencensus measures.  OpenCensus sends
# metrics to the server on it's own schedule. We decide how often, but it decides when.  This
# means that the measures that we make may get combined together on the wire.  The View is
# what defines exactly _how_ the measures get combined.
#
# For some measurements, we specify SumAggregation(), which means we want to sum all recorded
# measurements when they get pushed.  We use this for things that we count per interval, like
# x messages sent since the last measurement.
#
# For some measurements, we speficy LastValueAggregation, which means we want to push the latest
# measurement.  We use this for absolute counts like "total messages pushed".
#
# Unfortunately there is no "AverageAggregation" to push the average value of something.  I
# guess opencensus prefers to sample and/or bucket measurements like this.
#
class D2cViews(SimpleObject):
    def __init__(self, measures):
        super(D2cViews, self).__init__()
        self.d2c_roundtrip_latency = self._make_view(
            measures.d2c_roundtrip_latency, LastValueAggregation()
        )
        self.d2c_in_flight_count = self._make_view(
            measures.d2c_in_flight_count, LastValueAggregation()
        )
        self.d2c_succeeded_count = self._make_view(
            measures.d2c_succeeded_count, LastValueAggregation()
        )
        self.d2c_failed_count = self._make_view(measures.d2c_failed_count, SumAggregation())
        self.d2c_waiting_to_verify_count = self._make_view(
            measures.d2c_waiting_to_verify_count, LastValueAggregation()
        )
        self.d2c_verified_count = self._make_view(measures.d2c_verified_count, SumAggregation())
        self.freeze_attributes()

    def _make_view(self, measure, aggregation):
        return View(measure.name, measure.description, dimensions, measure, aggregation)

    def register(self, view_manager):
        for key in self.get_attribute_names():
            view = getattr(self, key)
            view_manager.register_view(view)


# Helper fnction to copy our internal metrics object into the opencensus measures object and
# record it.
def record(stats_recorder, metrics, measures):
    mmap = stats_recorder.new_measurement_map()
    for key in measures.get_attribute_names():
        measure = getattr(measures, key)
        metric = getattr(metrics, key, None)
        if metric is not None:
            if isinstance(measure, measure_module.MeasureFloat):
                mmap.measure_float_put(measure, metric)
            elif isinstance(measure, measure_module.MeasureInt):
                mmap.measure_int_put(measure, metric)
            else:
                assert False
    mmap.record(tmap)


# TODO: make this init into a function once this gets sorted out bettter

d2c_metrics = D2cMetrics()
d2c_measures = D2cMeasures()
d2c_views = D2cViews(d2c_measures)


def d2c_record():
    record(stats_recorder, d2c_metrics, d2c_measures)


# connection string comes from APPLICATIONINSIGHTS_CONNECTION_STRING env variable
# TODO: get export interval from data_model.py

exporter = metrics_exporter.new_metrics_exporter(export_interval=10.0)
view_manager = ViewManager()
d2c_views.register(view_manager)
view_manager.register_exporter(exporter)
stats_recorder = StatsRecorder()
