"""Tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from struct import pack
from typing import Any

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
