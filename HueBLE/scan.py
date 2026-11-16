"""HueBLE light scanning module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from HueBLE.const import DEFAULT_DISCOVER_TIME, UUID_HUE_IDENTIFIER


async def discover_lights(
    scanner: BleakScanner | None = None, timeout: int = DEFAULT_DISCOVER_TIME
) -> list[BLEDevice]:
    """Scanning feature
    Scans the BLE neighborhood for Hue BLE light(s) and returns
    a list of nearby lights based upon detection of a known UUID.
    """

    if scanner is None:
        scanner = BleakScanner

    devices = []

    # Callback for when advertising data is received
    def callback(device, advertising_data):
        if (
            UUID_HUE_IDENTIFIER in advertising_data.service_uuids
            and device not in devices
        ):
            devices.append(device)

    # Scan for timeout seconds
    async with BleakScanner(callback) as scanner:
        await asyncio.sleep(timeout)

    # Return what we found
    return devices
