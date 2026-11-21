# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
HueBLE light scanning module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from HueBLE.const import DEFAULT_DISCOVER_TIME, UUID_HUE_IDENTIFIER


def is_hue_ble_device(
    device: BLEDevice,  # noqa: ARG001
    advertisement_data: AdvertisementData,
) -> bool:
    """
    Return True if the device is a Hue BLE device, else false.

    :param device: BLEDevice to check.
    :param advertising_data: Bleak BLE advertisement data.
    :returns: True if device is a Hue BLE device else false.
    """
    return UUID_HUE_IDENTIFIER in advertisement_data.service_uuids


async def discover_lights(
    scanner: type[BleakScanner] | None = None,
    timeout: int = DEFAULT_DISCOVER_TIME,  # noqa: ASYNC109
) -> list[BLEDevice]:
    """
    Scan for Hue BLE devices.

    Scans the BLE neighborhood for Hue BLE light(s) using the provided scanner
    and returns a list of nearby lights based upon detection of a known UUID.

    :param scanner: BleakScanner implementation, allows for use with Home Assistant.
    :param timeout: Scanning time before returning results in seconds.
    :returns: List of discovered Hue BLE devices.
    """

    devices: list[BLEDevice] = []

    # Callback for when advertising data is received
    def callback(device: BLEDevice, advertising_data: AdvertisementData) -> None:
        if is_hue_ble_device(device, advertising_data) and device not in devices:
            devices.append(device)

    # Scan for timeout seconds
    async with (scanner or BleakScanner)(callback):
        await asyncio.sleep(timeout)

    # Return what we found
    return devices
