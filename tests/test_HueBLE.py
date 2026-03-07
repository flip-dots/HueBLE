"""Tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from struct import pack
from typing import Any
from unittest import mock

import pytest
import HueBLE
from tests import MOCK_BLE_DEVICE
from tests.helpers import MockDevice


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_uuid, command_bytes, responses, function, args, expected_props",
    [
        pytest.param(
            HueBLE.UUID_POWER,
            bytes.fromhex("01"),
            {HueBLE.UUID_POWER: bytes.fromhex("01")},
            "set_power",
            [True],
            {"power_state": True},
            id="power_on",
        ),
        pytest.param(
            HueBLE.UUID_POWER,
            bytes.fromhex("00"),
            {HueBLE.UUID_POWER: bytes.fromhex("00")},
            "set_power",
            [False],
            {"power_state": False},
            id="power_off",
        ),
        pytest.param(
            HueBLE.UUID_BRIGHTNESS,
            bytes.fromhex("05"),
            {HueBLE.UUID_BRIGHTNESS: bytes.fromhex("05")},
            "set_brightness",
            [5],
            {"brightness": 5},
            id="brightness",
        ),
        pytest.param(
            HueBLE.UUID_TEMPERATURE,
            bytes.fromhex("2C01"),
            {HueBLE.UUID_TEMPERATURE: bytes.fromhex("2C01")},
            "set_colour_temp",
            [300],
            {"colour_temp": 300},
            id="colour_temp",
        ),
        pytest.param(
            HueBLE.UUID_XY_COLOUR,
            pack("<HH", int(0.7 * 0xFFFF), int(0.5 * 0xFFFF)),
            {HueBLE.UUID_XY_COLOUR: pack("<HH", int(0.7 * 0xFFFF), int(0.5 * 0xFFFF))},
            "set_colour_xy",
            [0.7, 0.5],
            {
                "colour_xy": (0.6999923704890516, 0.49999237048905165),
                "colour_temp_mode": False,
            },
            id="colour_xy",
        ),
        pytest.param(
            HueBLE.UUID_TEMPERATURE,
            bytes.fromhex("5E01"),
            {
                HueBLE.UUID_TEMPERATURE: bytes.fromhex("5E01"),
                HueBLE.UUID_XY_COLOUR: pack(
                    "<HH", int(0.0 * 0xFFFF), int(0.0 * 0xFFFF)
                ),
            },
            "set_colour_temp",
            [350],
            {
                "colour_temp": 350,
                "colour_xy": (0.0, 0.0),
                "colour_temp_mode": True,
            },
            id="colour_temp_mode",
        ),
    ],
)
async def test_commands(
    command_uuid: str,
    command_bytes: bytes,
    responses: dict[str, bytes],
    function: str,
    args: list[Any],
    expected_props: dict[str, Any],
):
    """
    Test connecting and sending commands to the light and assert that
    a notification sent in response to a command results in the value
    being updated.

    :param command_uuid: The UUID the commands should be sent to and the response should come from.
    :param command_bytes: The bytes that should be written to the mock light.
    :param responses: Mapping of UUIDs to bytes which should be sent as a notification in response to command.
    :param function: The name of the function of HueBleLight that should be called.
    :param args: The arguments that should be given to the HueBleLight function being called.
    :param expected_props: Map of properties (e.g brightness, xy_colour) to expected value after update.
    """

    device = HueBLE.HueBleLight(MOCK_BLE_DEVICE)

    async with MockDevice() as mock_bluetooth:

        # We expect the connection to succeed
        await device.connect()
        assert device.connected, "Expected connected to return True"

        # Expect the write request and setup the notification responses
        mock_bluetooth.expect_ordered_write(command_uuid, command_bytes, responses)

        # Execute the command
        await getattr(device, function)(*args)

        # Assert that the command was sent
        mock_bluetooth.check_assertions()

        # Assert that the light parsed all of the responses and the
        # state has been correctly set
        for key, value in expected_props.items():

            prop = getattr(device, key)
            assert (
                prop == value
            ), f"Light state '{key}' is not expected value after command!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "supports, requests, expected_props",
    [
        pytest.param(
            {
                "on_off": False,
                "brightness": False,
                "colour_temp": False,
                "colour_xy": False,
            },
            {
                HueBLE.UUID_MANUFACTURER: "Elliott".encode(),
                HueBLE.UUID_MODEL: "ABCDEF".encode(),
                HueBLE.UUID_FW_VERSION: "1.9.2.3".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("0a0b0c0d0e0f"),
                HueBLE.UUID_NAME: "Red Wheelbarrow".encode(),
            },
            {
                "manufacturer": "Elliott",
                "model": "ABCDEF",
                "firmware": "1.9.2.3",
                "zigbee_address": "0a:0b:0c:0d:0e:0f",
                "name_in_app": "Red Wheelbarrow",
                "power_state": None,
                "brightness": None,
                "colour_temp": None,
                "minimum_mireds": None,
                "maximum_mireds": None,
                "colour_xy": None,
                "colour_temp_mode": None,
            },
            id="none",
        ),
        pytest.param(
            {
                "on_off": True,
                "brightness": False,
                "colour_temp": False,
                "colour_xy": False,
            },
            {
                HueBLE.UUID_MANUFACTURER: "sigNifY".encode(),
                HueBLE.UUID_MODEL: "Cloning Machine 2000".encode(),
                HueBLE.UUID_FW_VERSION: "2".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("ffff"),
                HueBLE.UUID_NAME: "Mauler Twins Base".encode(),
                HueBLE.UUID_POWER: bytes.fromhex("01"),
            },
            {
                "manufacturer": "sigNifY",
                "model": "Cloning Machine 2000",
                "firmware": "2",
                "zigbee_address": "ff:ff",
                "name_in_app": "Mauler Twins Base",
                "power_state": True,
            },
            id="power_only",
        ),
        pytest.param(
            {
                "on_off": True,
                "brightness": True,
                "colour_temp": False,
                "colour_xy": False,
            },
            {
                HueBLE.UUID_MANUFACTURER: "Govee".encode(),
                HueBLE.UUID_MODEL: "Hue Clone".encode(),
                HueBLE.UUID_FW_VERSION: "0.0.0".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("010101010101"),
                HueBLE.UUID_NAME: "Totally a Hue light".encode(),
                HueBLE.UUID_POWER: bytes.fromhex("01"),
                HueBLE.UUID_BRIGHTNESS: bytes.fromhex("FA"),
            },
            {
                "manufacturer": "Govee",
                "model": "Hue Clone",
                "firmware": "0.0.0",
                "zigbee_address": "01:01:01:01:01:01",
                "name_in_app": "Totally a Hue light",
                "power_state": True,
                "brightness": 250,
            },
            id="power_and_brightness",
        ),
        pytest.param(
            {
                "on_off": True,
                "brightness": True,
                "colour_temp": True,
                "colour_xy": False,
            },
            {
                HueBLE.UUID_MANUFACTURER: "IKEA".encode(),
                HueBLE.UUID_MODEL: "Slightly Better Hue Clone".encode(),
                HueBLE.UUID_FW_VERSION: "1.2.3-alpha".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("09080706050403020100"),
                HueBLE.UUID_NAME: "Hue light?".encode(),
                HueBLE.UUID_POWER: bytes.fromhex("01"),
                HueBLE.UUID_BRIGHTNESS: bytes.fromhex("96"),
                HueBLE.UUID_TEMPERATURE: bytes.fromhex("7201"),
            },
            {
                "manufacturer": "IKEA",
                "model": "Slightly Better Hue Clone",
                "firmware": "1.2.3-alpha",
                "zigbee_address": "09:08:07:06:05:04:03:02:01:00",
                "name_in_app": "Hue light?",
                "power_state": True,
                "brightness": 150,
                "colour_temp": 370,
                "minimum_mireds": HueBLE.MIN_MIREDS,
                "maximum_mireds": HueBLE.MAX_MIREDS,
                "colour_temp_mode": True,
            },
            id="colour_temperature",
        ),
        pytest.param(
            {
                "on_off": True,
                "brightness": True,
                "colour_temp": True,
                "colour_xy": True,
            },
            {
                HueBLE.UUID_MANUFACTURER: "pHillIpS".encode(),
                HueBLE.UUID_MODEL: "BIG LIGHT 3000".encode(),
                HueBLE.UUID_FW_VERSION: "0.0.0.0.0.1a".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("00010203040506070809"),
                HueBLE.UUID_NAME: "Volcano lair kitchen".encode(),
                HueBLE.UUID_POWER: bytes.fromhex("00"),
                HueBLE.UUID_BRIGHTNESS: bytes.fromhex("36"),
                HueBLE.UUID_TEMPERATURE: bytes.fromhex("9900"),
                HueBLE.UUID_XY_COLOUR: pack(
                    "<HH", int(0.0 * 0xFFFF), int(0.0 * 0xFFFF)
                ),
            },
            {
                "manufacturer": "pHillIpS",
                "model": "BIG LIGHT 3000",
                "firmware": "0.0.0.0.0.1a",
                "zigbee_address": "00:01:02:03:04:05:06:07:08:09",
                "name_in_app": "Volcano lair kitchen",
                "power_state": False,
                "brightness": 54,
                "colour_temp": 153,
                "colour_xy": (0.0, 0.0),
                "colour_temp_mode": True,
            },
            id="all",
        ),
    ],
)
async def test_poll_state(
    supports: dict[str, bool],
    requests: dict[str, bytes],
    expected_props: dict[str, Any],
):
    """
    Test polling all supported values from a device with
    different supported parameters.

    :param supports: Map of supported features.
    :param requests: Map of UUIDs to what the mock light should return.
    :param expected_props: Map of light properties to expected values.
    """

    async with MockDevice() as mock_bluetooth:
        with (
            mock.patch(
                "HueBLE.HueBleLight.supports_on_off",
                new_callable=mock.PropertyMock,
                return_value=supports["on_off"],
            ),
            mock.patch(
                "HueBLE.HueBleLight.supports_brightness",
                new_callable=mock.PropertyMock,
                return_value=supports["brightness"],
            ),
            mock.patch(
                "HueBLE.HueBleLight.supports_colour_temp",
                new_callable=mock.PropertyMock,
                return_value=supports["colour_temp"],
            ),
            mock.patch(
                "HueBLE.HueBleLight.supports_colour_xy",
                new_callable=mock.PropertyMock,
                return_value=supports["colour_xy"],
            ),
        ):

            device = HueBLE.HueBleLight(MOCK_BLE_DEVICE)

            callback_count = 0

            def my_callback(*args, **kwargs):
                """We expect this to be called twice."""
                nonlocal callback_count
                callback_count = callback_count + 1

            device.add_callback_on_state_changed(my_callback)

            # We expect the connection to succeed
            await device.connect()
            assert device.connected, "Expected connected to return True"
            assert callback_count == 1, "Expected callback to be executed on connect"

            # Expect all of the poll functions to be called inside poll_state
            for key, value in requests.items():
                mock_bluetooth.expect_ordered_read(key, value)

            # Poll all the values and assert state changed
            assert await device.poll_state(), "Expected state to have changed"

            # Assert that all values were polled
            mock_bluetooth.check_assertions()

            # Assert that the light parsed all of the responses and the
            # state has been correctly set
            for key, value in expected_props.items():

                prop = getattr(device, key)
                assert prop == value, f"Light state '{key}' is not the expected value!"


@pytest.mark.asyncio
async def test_automatic_retry():
    """
    Test the automatic retrying of a lost connection.

    This test expects the module to connect to the mock device
    and then the mock device drops the connection and we expect
    the module to automatically reconnect.

    We expect callbacks to be run on connection, disconnection,
    and reconnection.
    """

    async with MockDevice() as mock_bluetooth:

        device = HueBLE.HueBleLight(MOCK_BLE_DEVICE)

        callback_count = 0

        def my_callback(*args, **kwargs):
            """We expect this to be called three times."""
            nonlocal callback_count
            callback_count = callback_count + 1

        device.add_callback_on_state_changed(my_callback)

        # We expect the device to connect
        await device.connect()
        await asyncio.sleep(0.5)
        assert device.connected, "Expected connected to be True"
        assert callback_count == 1, "Expected callback to be run on first connection!"

        # We then trigger a disconnect from the device
        mock_bluetooth.disconnect()
        await asyncio.sleep(0.5)
        assert not device.connected, "Expected connected to be False"
        assert callback_count == 2, "Expected callback to be run on disconnection!"

        # Set .is_connected to True
        mock_bluetooth.allow_connect()

        # We expect to have been automatically reconnected
        async with asyncio.timeout(20):

            while not device.connected or callback_count != 3:
                await asyncio.sleep(1)

        assert device.connected, "Expected connected to be True"
        assert callback_count == 3, "Expected callback to be run on reconnection!"
