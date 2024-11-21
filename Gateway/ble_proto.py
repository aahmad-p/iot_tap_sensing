import asyncio
from bleak import BleakScanner

DEVICE_NAME='Tap Sensor'


async def main():
    stop_event = asyncio.Event()

    # TODO: add something that calls stop_event.set()

    def callback(device, advertising_data):
        # Filter for our devices name
        print(device)
        if device.name == DEVICE_NAME:
            service_data_dict = advertising_data.service_data
            # Print the advertising data payload, TODO: parse this
            print(service_data_dict[list(service_data_dict.keys())[0]])

    async with BleakScanner(callback) as scanner:
        ...
        # Important! Wait for an event to trigger stop, otherwise scanner
        # will stop immediately.
        await stop_event.wait()

    # scanner stops when block exits
    ...

asyncio.run(main())
