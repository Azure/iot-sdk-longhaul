# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
import logging
import json
import os
import asyncio
from azure.iot.hub import IoTHubRegistryManager
from typing import Dict

registry_manager = None
iothub_connection_string = os.environ["IOTHUB_CONNECTION_STRING"]
send_list: Dict[str, Dict] = {}


async def sleep_and_send(device_id: str):
    """
    coroutine to sleep for a while and then send our message list.  While this coroutine
    is sleeping, other coroutines are adding to our message list.  This is how we batch
    message_ids and send them once every so-many seconds.
    """
    global send_list

    # since IoTHubRegistryManager is a sync API, we run it as a function inside our default
    # ThreadPoolExecutor so we don't block the event loop.
    def send(message: str):
        global registry_manager

        logging.info("sending {}".format(message))

        tries_left = 3
        while tries_left:
            tries_left -= 1

            if not registry_manager:
                registry_manager = IoTHubRegistryManager(iothub_connection_string)

            try:
                registry_manager.send_c2d_message(
                    device_id,
                    message,
                    {"contentType": "application/json", "contentEncoding": "utf-8"},
                )
                return
            except Exception:
                logging.info("Exception.  Disconnecting.  Tries left = {}".format(tries_left))
                registry_manager.amqp_svc_client.disconnect_sync()
                registry_manager = None
                if tries_left == 0:
                    raise

    # Wait a while for messages to queue up
    await asyncio.sleep(5)

    # then build the message. When we del send_list[device_id], that triggers the main coroutine
    # to make a new send_list and create a new send task for the next batch.
    message = json.dumps({"lh_response": True, "message_ids": send_list[device_id]})
    del send_list[device_id]

    # This is where we run the send on a background thread
    await asyncio.get_running_loop().run_in_executor(None, send, message)


async def main(events):
    global registry_manager
    global send_list

    create_task = False
    device_id = events[0].metadata["SystemPropertiesArray"][0]["iothub-connection-device-id"]
    for event in events:
        obj = json.loads(event.get_body().decode("utf-8"))
        if isinstance(obj, dict) and obj.get("lh_send_response"):
            message_id = obj["message_id"]
            logging.info("pingback to {} for {}".format(device_id, message_id))
            if device_id not in send_list:
                # if we don't have this device_id in our send_list dict yet, we need to
                # create a new task to send our message ids.
                create_task = True
                send_list[device_id] = []
            send_list[device_id].append(message_id)

    if create_task:
        asyncio.create_task(sleep_and_send(device_id))
