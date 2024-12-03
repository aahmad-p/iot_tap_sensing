# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

# Import modules, appending directory to path where necessary
from awscrt import mqtt, http
from awsiot import mqtt_connection_builder
import sys
import threading
import time
import json
import queue

import asyncio
from bleak import BleakScanner

import sys
sys.path.append('./aws-iot-device-sdk-python-v2/samples')

from utils.command_line_utils import CommandLineUtils

# cmdData is the arguments/input from the command line placed into a single struct for
# use in this sample. This handles all of the command line parsing, validating, etc.
# See the Utils/CommandLineUtils for more information.
cmdData = CommandLineUtils.parse_sample_input_pubsub()

received_count = 0
received_all_event = threading.Event()

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))

# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)

def on_resubscribe_complete(resubscribe_future):
    resubscribe_results = resubscribe_future.result()
    print("Resubscribe results: {}".format(resubscribe_results))

    for topic, qos in resubscribe_results['topics']:
        if qos is None:
            sys.exit("Server rejected resubscribe to topic: {}".format(topic))

# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global received_count
    received_count += 1
    if received_count == cmdData.input_count:
        received_all_event.set()

# Callback when the connection successfully connects
def on_connection_success(connection, callback_data):
    assert isinstance(callback_data, mqtt.OnConnectionSuccessData)
    print("Connection Successful with return code: {} session present: {}".format(callback_data.return_code, callback_data.session_present))

# Callback when a connection attempt fails
def on_connection_failure(connection, callback_data):
    assert isinstance(callback_data, mqtt.OnConnectionFailureData)
    print("Connection failed with error code: {}".format(callback_data.error))

# Callback when a connection has been disconnected or shutdown successfully
def on_connection_closed(connection, callback_data):
    print("Connection closed")

DEVICE_NAME='Tap Sensor'
TAP_OFF = "Water Off"
TAP_ON = "tap on"
WATCHDOG = "Watchdog"

q = queue.Queue()

def tap_monitor(mqtt_connection, message_topic, message_string, message_count):
    previous_state = TAP_OFF

    def send_tap_update(tap_state): 
        message = "{" + "\"tap_state\" : \"{message}\"".format(message=tap_state) + "}"
        print("Publishing message to topic '{}': {}".format(message_topic, message))
        mqtt_connection.publish(topic=message_topic, payload=message, qos=mqtt.QoS.AT_LEAST_ONCE)
    
    def send_tap_watchdog(): 
        message = "{}".format("{\"watchdog\" : 1}")
        print("Publishing message to topic '{}': {}".format(message_topic, message))
        mqtt_connection.publish(topic=message_topic, payload=message, qos=mqtt.QoS.AT_LEAST_ONCE)

    while True:
        state = q.get()
        if (previous_state == TAP_OFF and state == TAP_ON):
            send_tap_update("tap on")
        elif (previous_state == TAP_ON and state == TAP_OFF):
            send_tap_update("Water Off")
        elif (state == WATCHDOG):
            send_tap_watchdog()

        previous_state = state
        q.task_done()



async def ble_scan():
    stop_event = asyncio.Event()
    current_tap_state = False

    # TODO: add something that calls stop_event.set()

    def callback(device, advertising_data):
        
        # Filter for our devices name
        # print(device)
        if device.name == DEVICE_NAME:
            service_data_dict = advertising_data.service_data
            # Print the advertising data payload, TODO: parse this
            #print(datetime.datetime.now())
            # q.put(service_data_dict[list(service_data_dict.keys())[0]])
            # TODO: Write code to better unpack packet
            #print(service_data_dict[list(service_data_dict.keys())[0]] == b"@'\x00\x0f\x00")
            match service_data_dict[list(service_data_dict.keys())[0]]:
                case b"@'\x00\x0f\x00":
                    q.put(TAP_OFF)
                case b"@'\x01\x0f\x00":
                    q.put(TAP_ON)
                case b"@'\x00\x0f\x01":
                    q.put(WATCHDOG)


    

    # if True:
    async with BleakScanner(callback) as scanner:
        # Important! Wait for an event to trigger stop, otherwise scanner
        # will stop immediately.
        
 

        await stop_event.wait()

if __name__ == '__main__':
    # Create the proxy options if the data is present in cmdData
    proxy_options = None
    if cmdData.input_proxy_host is not None and cmdData.input_proxy_port != 0:
        proxy_options = http.HttpProxyOptions(
            host_name=cmdData.input_proxy_host,
            port=cmdData.input_proxy_port)

    # Create a MQTT connection from the command line data
    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=cmdData.input_endpoint,
        port=cmdData.input_port,
        cert_filepath=cmdData.input_cert,
        pri_key_filepath=cmdData.input_key,
        ca_filepath=cmdData.input_ca,
        on_connection_interrupted=on_connection_interrupted,
        on_connection_resumed=on_connection_resumed,
        client_id=cmdData.input_clientId,
        clean_session=False,
        keep_alive_secs=30,
        http_proxy_options=proxy_options,
        on_connection_success=on_connection_success,
        on_connection_failure=on_connection_failure,
        on_connection_closed=on_connection_closed)

    if not cmdData.input_is_ci:
        print(f"Connecting to {cmdData.input_endpoint} with client ID '{cmdData.input_clientId}'...")
    else:
        print("Connecting to endpoint with client ID")
    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    message_count = cmdData.input_count
    message_topic = cmdData.input_topic
    #message_string = cmdData.input_message
    # TODO: Populate message_string using received BLE data
    message_string = "{\"tap_state\" : 1}"

    # Subscribe
    print("Subscribing to topic '{}'...".format(message_topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=message_topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))

    '''
    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if message_count != 0 and not received_all_event.is_set():
        print("Waiting for all messages to be received...")

    received_all_event.wait()
    print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")
    '''
   
    # Turn-on the worker thread.
    threading.Thread(target=tap_monitor, args=(mqtt_connection, message_topic, message_string, message_count), daemon=True).start()
    asyncio.run(ble_scan())
    q.join()
