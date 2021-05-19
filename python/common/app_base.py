# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import logging
import six
import abc
import sys
import platform
import os
import traceback
import pdb
from system_health_telemetry import SystemHealthTelemetry
from thief_constants import Metrics


logger = logging.getLogger("thief.{}".format(__name__))

WAITING = "Waiting"
RUNNING = "Running"
FAILED = "Failed"
COMPLETE = "Complete"
INTERRUPTED = "Interrupted"


class WorkerThreadInfo(object):
    """
    This structure holds information about a running worker thread.
    """

    def __init__(self, threadproc, name):
        self.threadproc = threadproc
        self.name = name
        self.future = None
        self.watchdog_epochtime = None
        self.thread_id = None


python_runtime = platform.python_version()
os_type = platform.system()
os_release = platform.version()
architecture = platform.machine()

# TODO: this is no longer a base class, per-se.  Distribute functionality into propert places.


def _get_os_release_based_on_user_agent_standard():
    return "({python_runtime};{os_type} {os_release};{architecture})".format(
        python_runtime=python_runtime,
        os_type=os_type,
        os_release=os_release,
        architecture=architecture,
    )


@six.add_metaclass(abc.ABCMeta)
class AppBase(object):
    def __init__(self):
        self.system_health_telemetry = SystemHealthTelemetry()
        self.paused = False

    def pause_all_threads(self):
        """
        Pause all threads.  Used to stop all background threads while debugging
        """
        self.paused = True

    def unpause_all_threads(self):
        """
        Unpause all threads.  Used when debugging is finished.
        """
        self.paused = False

    def is_paused(self):
        """
        return True if threads should be paused.
        """
        return self.paused

    def breakpoint(self):
        """
        Pause all threads and break into the debugger
        """
        self.pause_all_threads()
        pdb.set_trace()

    def get_system_properties(self, version):
        return {
            "language": "python",
            "languageVersion": platform.python_version(),
            "sdkVersion": version,
            "sdkGithubRepo": os.getenv("THIEF_SDK_GIT_REPO"),
            "sdkGithubBranch": os.getenv("THIEF_SDK_GIT_BRANCH"),
            "sdkGithubCommit": os.getenv("THIEF_SDK_GIT_COMMIT"),
            "osType": platform.system(),
            "osRelease": _get_os_release_based_on_user_agent_standard(),
        }

    def get_system_health_telemetry(self):
        props = {
            Metrics.PROCESS_CPU_PERCENT: self.system_health_telemetry.process_cpu_percent,
            Metrics.PROCESS_WORKING_SET: self.system_health_telemetry.process_working_set,
            Metrics.PROCESS_BYTES_IN_ALL_HEAPS: self.system_health_telemetry.process_bytes_in_all_heaps,
            Metrics.PROCESS_PRIVATE_BYTES: self.system_health_telemetry.process_private_bytes,
            Metrics.PROCESS_WORKING_SET_PRIVATE: self.system_health_telemetry.process_working_set_private,
        }
        return props

    def _dump_all_threads(self, problem_thread_id=None):
        """
        Dump all threads for debugging
        """
        if six.PY3:
            logger.warning("Dumping all stacks")
            for thread_id, frame in sys._current_frames().items():
                if problem_thread_id and thread_id == problem_thread_id:
                    logger.warning("Stack for PROBLEM thread {}".format(thread_id))
                else:
                    logger.warning("Stack for thread {}".format(thread_id))
                logger.warning(str(traceback.format_stack(frame)))
