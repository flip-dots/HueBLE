import asyncio
from bleak import BleakScanner
import HueBLE


async def main():

    # Address of light to connect to
    address = "F6:9B:48:A4:D2:D8"

    # Obtain the BLEDevice from bleak
    device = await BleakScanner.find_device_by_address(address)

    # Initialize the light object
    light = HueBLE.HueBleLight(device)

    # Optionally we could call connect but it will be called automatically
    # on the first request to the light. You might want to call this if
    # you want to subscribe to state changes without changing the lights state.
    # await light.connect()

    # Will automatically connect to the light and turn it off
    await light.set_power(False)

    # Wait
    await asyncio.sleep(5)

    # Turn the light back on again
    await light.set_power(True)

if __name__ == "__main__":
    asyncio.run(main())
