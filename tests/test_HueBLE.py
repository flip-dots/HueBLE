"""Tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from contextlib import nullcontext
from struct import pack
import time
import traceback
from typing import Any, Union
from bleak import BLEDevice
from unittest import mock

from bleak.exc import BleakError
import pytest
import HueBLE
from tests import MOCK_BLE_DEVICE, MOCK_DEVICE_ADDRESS, MOCK_DEVICE_NAME
from tests.helpers import MockDevice, sleep_side_effect


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
        pytest.param(
            HueBLE.UUID_EFFECTS,
            bytes.fromhex("01010102015004049bc54f3606010108015e"),
            {
                HueBLE.UUID_EFFECTS: bytes.fromhex(
                    "01010102015004049bc54f3606010108015e"
                ),
            },
            "set_colour_effect",
            [0.77191, 0.21215, 80, HueBLE.EffectType.CANDLE, 94],
            {
                "effect": (HueBLE.EffectType.CANDLE, 94),
                "colour_xy": (0.7719081406881819, 0.21214618142977035),
                "colour_temp_mode": False,
            },
            id="colour_effect",
        ),
        pytest.param(
            HueBLE.UUID_EFFECTS,
            bytes.fromhex("01010102015003022c0106010108015e"),
            {
                HueBLE.UUID_EFFECTS: bytes.fromhex("01010102015003022c0106010108015e"),
            },
            "set_temperature_effect",
            [300, 80, HueBLE.EffectType.CANDLE, 94],
            {
                "effect": (HueBLE.EffectType.CANDLE, 94),
                "colour_temp": 300,
                "colour_temp_mode": True,
            },
            id="temperature_effect",
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
    "requests, expected_props",
    [
        pytest.param(
            {},
            {
                "manufacturer": None,
                "model": None,
                "firmware": None,
                "zigbee_address": None,
                "name_in_app": None,
                "power_state": None,
                "brightness": None,
                "colour_temp": None,
                "colour_xy": None,
                "colour_temp_mode": None,
            },
            id="none",
        ),
        pytest.param(
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
            id="minimal",
        ),
        pytest.param(
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
                "brightness": None,
                "colour_temp": None,
                "minimum_mireds": None,
                "maximum_mireds": None,
                "colour_xy": None,
                "colour_temp_mode": None,
            },
            id="power_only",
        ),
        pytest.param(
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
                "colour_temp": None,
                "minimum_mireds": None,
                "maximum_mireds": None,
                "colour_xy": None,
                "colour_temp_mode": None,
            },
            id="power_and_brightness",
        ),
        pytest.param(
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
                "colour_xy": None,
            },
            id="colour_temperature",
        ),
        pytest.param(
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
        pytest.param(
            {
                HueBLE.UUID_MANUFACTURER: "atmospheric lights".encode(),
                HueBLE.UUID_MODEL: "Candle Lights".encode(),
                HueBLE.UUID_FW_VERSION: "c.a.f.f.e.e".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("00010203040506070809"),
                HueBLE.UUID_NAME: "Tea light".encode(),
                HueBLE.UUID_EFFECTS: bytes.fromhex(
                    "01010102015004046666ff7f06010108015e"
                ),
            },
            {
                "manufacturer": "atmospheric lights",
                "model": "Candle Lights",
                "firmware": "c.a.f.f.e.e",
                "zigbee_address": "00:01:02:03:04:05:06:07:08:09",
                "name_in_app": "Tea light",
                "power_state": True,
                "brightness": 80,
                "colour_temp": None,
                "colour_xy": (0.4, 0.49999237048905165),
                "effect": (HueBLE.EffectType.CANDLE, 94),
            },
            id="colour_effect",
        ),
        pytest.param(
            {
                HueBLE.UUID_MANUFACTURER: "atmospheric lights".encode(),
                HueBLE.UUID_MODEL: "Candle Lights".encode(),
                HueBLE.UUID_FW_VERSION: "c.a.f.f.e.e".encode(),
                HueBLE.UUID_ZIGBEE_ADDRESS: bytes.fromhex("00010203040506070809"),
                HueBLE.UUID_NAME: "Tea light".encode(),
                HueBLE.UUID_EFFECTS: bytes.fromhex("01010102015003022c0106010108015e"),
            },
            {
                "manufacturer": "atmospheric lights",
                "model": "Candle Lights",
                "firmware": "c.a.f.f.e.e",
                "zigbee_address": "00:01:02:03:04:05:06:07:08:09",
                "name_in_app": "Tea light",
                "power_state": True,
                "brightness": 80,
                "colour_temp": 300,
                "colour_xy": None,
                "effect": (HueBLE.EffectType.CANDLE, 94),
            },
            id="temperature_effect",
        ),
    ],
)
async def test_poll_state(
    requests: dict[str, bytes],
    expected_props: dict[str, Any],
):
    """
    Test polling all supported values from a device with
    different supported parameters.

    :param requests: Map of UUIDs to what the mock light should return.
    :param expected_props: Map of light properties to expected values.
    """

    async with MockDevice() as mock_bluetooth:

        def mock_get_characteristic(uuid: str) -> bytes:
            """
            Mocked client.services.get_characteristic for BleakClient.

            If the UUID is in the requests dict (its expected) then we set it
            to 00, i.e is supported, else its None, meaning that UUID is not
            supported.
            """
            if uuid in requests:
                return bytes.fromhex("00")
            else:
                return None

        mock_bluetooth.set_side_effects(services_side_effect=mock_get_characteristic)

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
        assert device.available, "Expected available to return True"
        assert callback_count == 1, "Expected callback to be executed on connect"

        # Expect all of the poll functions to be called inside poll_state
        for key, value in requests.items():
            mock_bluetooth.expect_ordered_read(key, value)

        # Poll all the values and assert state changed
        state_changed = await device.poll_state()

        if requests:
            assert state_changed, "Expected state to have changed"
        else:
            assert not state_changed, "Expected state to be the same"

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
        assert device.available, "Expected available to return True"
        assert callback_count == 1, "Expected callback to be run on first connection!"

        # We then trigger a disconnect from the device
        mock_bluetooth.disconnect()
        await asyncio.sleep(0.5)
        assert not device.connected, "Expected connected to be False"
        assert not device.available, "Expected available to return False"
        assert callback_count == 2, "Expected callback to be run on disconnection!"

        # Set .is_connected to True
        mock_bluetooth.allow_connect()

        # We expect to have been automatically reconnected
        async with asyncio.timeout(20):

            while not device.connected or callback_count != 3:
                await asyncio.sleep(1)

        assert device.connected, "Expected connected to be True"
        assert device.available, "Expected available to be True"
        assert callback_count == 3, "Expected callback to be run on reconnection!"


@pytest.mark.asyncio
async def test_disconnect():
    """
    Test the mock device is disconnected and no automatic
    reconnection attempts are executed when disconnect is called.

    We also expect no callbacks to be run and multiple calls
    to disconnect to do nothing.
    """

    async with MockDevice() as mock_bluetooth:

        device = HueBLE.HueBleLight(MOCK_BLE_DEVICE)

        # We expect the device to connect
        await device.connect()
        await asyncio.sleep(0.5)
        assert device.connected, "Expected connected to be True"
        assert device.available, "Expected available to be True"

        def my_callback(*args, **kwargs):
            """We expect this to never be called."""
            assert False

        device.add_callback_on_state_changed(my_callback)

        # Fast forward any delays by 100x
        sleep = asyncio.sleep
        with mock.patch("asyncio.sleep", new=lambda d: sleep(d / 100)):

            # We then trigger a disconnect from the device
            await device.disconnect()
            await asyncio.sleep(1)
            assert not device.connected, "Expected connected to be False"
            assert not device.available, "Expected available to be False"

            # Assert that disconnect was called
            mock_bluetooth._current_mock_bleak_client.disconnect.assert_called()

            # Assert we are still disconnected
            await asyncio.sleep(100)
            assert not device.connected, "Expected connected to be False"
            assert not device.available, "Expected available to be False"

            # Assert that calling disconnect again does nothing
            await device.disconnect()

            await asyncio.sleep(100)
            assert not device.connected, "Expected connected to be False"
            assert not device.available, "Expected available to be False"

            # Assert that triggering the disconnect from the bleak
            # client does nothing
            mock_bluetooth.disconnect()
            await asyncio.sleep(100)
            assert not device.connected, "Expected connected to be False"
            assert not device.available, "Expected available to be False"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform, properties, value",
    [
        pytest.param(
            "Windows",
            None,
            None,
            id="windows",
        ),
        pytest.param(
            "Darwin",
            None,
            None,
            id="mac",
        ),
        pytest.param(
            "",
            None,
            None,
            id="unknown_platform",
        ),
        pytest.param(
            "Linux",
            None,
            None,
            id="linux_no_props",
        ),
        pytest.param(
            "Linux",
            {},
            None,
            id="linux_no_pair_props",
        ),
        pytest.param(
            "Linux",
            {"Paired": False},
            False,
            id="linux_not_paired",
        ),
        pytest.param(
            "Linux",
            {"Paired": True},
            True,
            id="linux_paired",
        ),
    ],
)
async def test_authenticated(
    platform: str, properties: Union[bool, None], value: Union[bool, None]
):
    """
    Test the authenticated property by mocking different platforms and
    connection properties.

    :param platform: The platform (e.g windows, linux, etc).
    :param properties: The properties of the BLEDevice.
    :param value: Expected value of light.authenticated.
    """

    ble_device = BLEDevice(MOCK_DEVICE_ADDRESS, MOCK_DEVICE_NAME, {"props": properties})
    light = HueBLE.HueBleLight(ble_device)

    with mock.patch("platform.system", return_value=platform):
        assert (
            light.authenticated == value
        ), "light.authenticated does not match expected!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "establish_side_effect, connected_side_effect, pair_side_effect, authenticated_side_effect, services_side_effect, subscribe_side_effect, connection_lock_side_effect, error, error_messages",
    [
        pytest.param(
            None,
            False,
            None,
            None,
            None,
            None,
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Failed to make an initial connection to the light",
                "Not connected to ",
            ],
            id="is_connected_false",
        ),
        pytest.param(
            Exception("Generic exception raised by establish_connection"),
            False,
            None,
            None,
            None,
            None,
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Failed to make an initial connection to the light",
                "Generic exception raised by establish_connection",
            ],
            id="establish_connection_exception",
        ),
        pytest.param(
            sleep_side_effect,
            False,
            None,
            None,
            None,
            None,
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Timed out attempting to connect to",
            ],
            id="establish_connection_timeout",
        ),
        pytest.param(
            None,
            True,
            sleep_side_effect,
            None,
            None,
            None,
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Timed out attempting to pair",
            ],
            id="pair_timeout",
        ),
        pytest.param(
            None,
            True,
            BleakError("Generic pairing error!"),
            None,
            None,
            None,
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Error from Bluetooth backend when attempting to pair",
                "Generic pairing error!",
            ],
            id="pair_bleak_exception",
        ),
        pytest.param(
            None,
            True,
            None,
            None,
            [True, True, Exception("NOPE BAD SERVICE")],
            None,
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Failed to determine what services",
                "NOPE BAD SERVICE",
            ],
            id="service_discovery_exception",
        ),
        pytest.param(
            None,
            True,
            None,
            None,
            None,
            [True, True, Exception("NOPE BAD SUBSCRIPTION")],
            None,
            HueBLE.ConnectionError,
            [
                "Exception connecting to light",
                "Failed to subscribe to services offered",
                "NOPE BAD SUBSCRIPTION",
            ],
            id="subscription_exception",
        ),
        pytest.param(
            None,
            None,
            None,
            None,
            None,
            None,
            sleep_side_effect,
            HueBLE.ConnectionError,
            [
                "Timed out waiting for connection lock for",
            ],
            id="timeout_wait_lock",
        ),
    ],
)
async def test_connect_errors(
    fast_timeouts,
    establish_side_effect: Any,
    connected_side_effect: Any,
    pair_side_effect: Any,
    authenticated_side_effect: Any,
    services_side_effect: Any,
    subscribe_side_effect: Any,
    connection_lock_side_effect: Any,
    error: Exception,
    error_messages: list[str],
):
    """
    Test the error raising of the connect function of a light.

    :param establish_side_effect: Side effect of calling establish_connection().
    :param connected_side_effect: Side effect of client.is_connected.
    :param pair_side_effect: Side effect of calling client.pair().
    :param authenticated_side_effect: Side effect of calling light.authenticated.
    :param services_side_effect: Side effect of calling client.services.get_characteristic().
    :param subscribe_side_effect: Side effect of calling client.start_notify().
    :param connection_lock_side_effect: Side effect of entering context of self._connection_lock.
    :param error: Expected exception to be raised inside connect.
    :param error_messages: Expected error messages inside exception message.
    """

    mock_device = MockDevice()

    # Configure side effects
    mock_device.set_side_effects(
        establish_side_effect=establish_side_effect,
        connected_side_effect=connected_side_effect,
        pair_side_effect=pair_side_effect,
        services_side_effect=services_side_effect,
        subscribe_side_effect=subscribe_side_effect,
    )

    sleep = asyncio.sleep
    async with mock_device as mock_bluetooth:

        device = HueBLE.HueBleLight(MOCK_BLE_DEVICE)

        # Use Linux platform (MacOS can't pair)
        # Patch authenticated to enable simulating paired is False
        # Fast forward delays by 100x
        with (
            mock.patch("platform.system", return_value="linux"),
            mock.patch(
                "HueBLE.HueBleLight.authenticated",
                new_callable=mock.PropertyMock,
                return_value=authenticated_side_effect,
            ),
            mock.patch("asyncio.sleep", new=lambda d: sleep(d / 100)),
        ):

            # Patch connection lock for connection lock timeout test
            if connection_lock_side_effect is not None:
                device._connection_lock = mock.MagicMock()
                device._connection_lock.__aenter__ = mock.AsyncMock(
                    side_effect=connection_lock_side_effect
                )

            # Expect error to be raised
            with (pytest.raises(error) as e,):
                await device.connect()

            # Expect error log messages to be present
            traceback_message = "".join(
                traceback.format_exception(e.type, e.value, e.tb)
            )
            for error_message in error_messages:
                assert error_message in traceback_message
