# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
Helpers for tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self
from unittest import mock

from HueBLE.const import (
    UUID_BRIGHTNESS,
    UUID_EFFECTS,
    UUID_FW_VERSION,
    UUID_HUE_IDENTIFIER,
    UUID_MANUFACTURER,
    UUID_MODEL,
    UUID_NAME,
    UUID_POWER,
    UUID_TEMPERATURE,
    UUID_XY_COLOUR,
    UUID_ZIGBEE_ADDRESS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)


def mock_get_services_fn(value: str) -> dict[str, str] | None:
    """Return a list of supported services."""

    return (
        {"fake_service": "fake_value"}
        if value
        in [
            UUID_BRIGHTNESS,
            UUID_EFFECTS,
            UUID_FW_VERSION,
            UUID_HUE_IDENTIFIER,
            UUID_MANUFACTURER,
            UUID_MODEL,
            UUID_NAME,
            UUID_POWER,
            UUID_TEMPERATURE,
            UUID_XY_COLOUR,
            UUID_ZIGBEE_ADDRESS,
        ]
        else None
    )


@dataclass
class ReadRequest:
    """
    Read request to mock light.

    Internal data class used by MockDevice to keep track of which
    requests have been executed and what the correct response to
    the request is.
    """

    uuid: str
    """
    The expected UUID of the request.
    """

    response: bytes | None
    """
    The bytes (if any) that should be returned in response to a matching request.
    """

    called: bool
    """
    Has this request been fulfilled.
    """


@dataclass
class WriteRequest:
    """
    Mock write request to mock light.

    Internal data class used by MockDevice to keep track of which
    requests have been executed and what the correct response to
    the request is.
    """

    uuid: str
    """
    The expected UUID of the request.
    """

    expected: bytes
    """
    The bytes expected in the write request.
    """

    responses: dict[str, bytes]
    """
    Contains a dictionary mapping notification UUIDs to the bytes that should
    be sent as a notification in response to this request.
    """

    called: bool
    """
    Has this request been fulfilled.
    """


class MockDevice:
    """
    Class designed to emulate the behavior of a Bluetooth GATT device.

    This is designed to be used as a context manager and allows for the
    easy defining of expected requests and the appropriate responses as
    well as built in assertions for checking that all the requests were
    made.

    This implementation is a tad cursed to allow us to test some strange
    edge cases that seem to keep popping up.
    """

    def __init__(self) -> None:
        """Initialise mock device."""

        # Tuple used to keep track of all the bleak clients that have been
        # created. Each tuple contains the client, the clients disconnect
        # callbacks, and the clients notification callbacks
        self._mock_bleak_clients: list[
            tuple[BleakClient, list[Callable], list[tuple[str, Callable]]]
        ] = []

        # This is the result of the mock.patch and used to return our
        # modified bleak client when establish connection is called
        self._establish = None

        # This is the function we are patching so instead of an actual
        # bleak client its getting our mocked one
        self._patcher = mock.patch("HueBLE.light.establish_connection")

        # List of assertions (requests and responses) we expect to be made
        self._assertions: list[ReadRequest | WriteRequest] = []

        # The most freshly created mock bleak client
        self._current_mock_bleak_client: mock.AsyncMock | None = None

        # The position of the next request we expect to get in the list
        # of assertions
        self._position = 0

        # The value that all our mocked bleak clients will return for
        # client.is_connected. This can be changed dynamically
        self._is_connected = True

        # Customizable side effects for newly initialized bleak clients
        self._side_effect_establish = None
        self._side_effect_connected = None
        self._side_effect_pair = None
        self._side_effect_services = None
        self._side_effect_subscribe = None
        self._side_effect_read = None
        self._side_effect_write = None
        self._side_effect_disconnect = None

    def new_connection_mock(self) -> None:
        """
        Return new mock BleakClient.

        Executing this causes all new bleak clients created using
        establish_connection to be our mocked versions.
        """

        def custom_init(*args: dict, **kwargs: dict) -> mock.AsyncMock:
            """
            Init new mock BleakClient.

            This function is used to create new mock bleak clients whenever
            establish_connection is called.
            """
            _LOGGER.debug(f"New mock bleak client created with '{args}', '{kwargs}'!")

            # We give it a name so we can tell the difference between them in logs
            mock_bleak_client = mock.AsyncMock(
                name=f"bleak_client_{len(self._mock_bleak_clients)}",
            )

            # Set functions/properties
            mock_bleak_client.read_gatt_char.side_effect = self.read_gatt_char
            mock_bleak_client.write_gatt_char.side_effect = self.write_gatt_char
            mock_bleak_client.start_notify.side_effect = self.start_notify
            mock_bleak_client.services.get_characteristic = mock.MagicMock()
            mock_bleak_client.is_connected = mock.PropertyMock(
                side_effect=lambda: self._is_connected,
            )

            # Override with any set side effects
            if self._side_effect_connected is not None:
                mock_bleak_client.is_connected = self._side_effect_connected
            if self._side_effect_pair is not None:
                mock_bleak_client.pair.side_effect = self._side_effect_pair
            if self._side_effect_services is not None:
                mock_bleak_client.services.get_characteristic.side_effect = (
                    self._side_effect_services
                )
            if self._side_effect_subscribe is not None:
                mock_bleak_client.start_notify.side_effect = self._side_effect_subscribe
            if self._side_effect_read is not None:
                mock_bleak_client.read_gatt_char.side_effect = self._side_effect_read
            if self._side_effect_write is not None:
                mock_bleak_client.write_gatt_char.side_effect = self._side_effect_write
            if self._side_effect_disconnect is not None:
                mock_bleak_client.disconnect.side_effect = self._side_effect_disconnect

            # Add it to the list of all bleak clients
            self._mock_bleak_clients.append(
                (
                    mock_bleak_client,
                    [kwargs["disconnected_callback"]],  # type: ignore[list-item]
                    [],
                ),
            )

            # Set this as the most current bleak client and return it
            self._current_mock_bleak_client = mock_bleak_client
            return mock_bleak_client

        # If establish_connection has an overridden side effect use that
        if self._side_effect_establish is not None:
            self._establish.side_effect = self._side_effect_establish

        # Else use custom_init to manufacture all new bleak clients
        else:
            self._establish.side_effect = custom_init  # type: ignore[attr-defined]

    async def __aenter__(self) -> Self:
        """
        Enter the context.

        Patches :func:`~bleak_retry_connector.establish_connection` so all new clients
        are mocks.
        """
        self._establish = self._patcher.start()  # type: ignore[assignment]
        self.new_connection_mock()

        return self

    def set_side_effects(  # noqa: PLR0913, PLR0917
        self,
        establish_side_effect: Any = None,  # noqa: ANN401
        connected_side_effect: Any = None,  # noqa: ANN401
        pair_side_effect: Any = None,  # noqa: ANN401
        services_side_effect: Any = None,  # noqa: ANN401
        subscribe_side_effect: Any = None,  # noqa: ANN401
        read_side_effect: Any = None,  # noqa: ANN401
        write_side_effect: Any = None,  # noqa: ANN401
        disconnect_side_effect: Any = None,  # noqa: ANN401
    ) -> None:
        """
        Set side effects of mock client.

        This sets the specified side effects on all future bleak clients
        which are initialized. They can be unset for new clients by setting
        them to None. If you need to use None use [None].

        :param establish_side_effect: Side effect of using establish_connection().
        :param connected_side_effect: Side effect of client.is_connected.
        :param pair_side_effect: Side effect of calling client.pair().
        :param services_side_effect: Side effect of calling client.services.get_characteristic().
        :param read_side_effect: Side effect of calling client.read_gatt_char().
        :param write_side_effect: Side effect of calling client.write_gatt_char().
        :param disconnect_side_effect: Side effect of calling client.disconnect().
        """  # noqa: E501
        self._side_effect_establish = establish_side_effect
        self._side_effect_connected = connected_side_effect
        self._side_effect_pair = pair_side_effect
        self._side_effect_services = services_side_effect
        self._side_effect_subscribe = subscribe_side_effect
        self._side_effect_read = read_side_effect
        self._side_effect_write = write_side_effect
        self._side_effect_disconnect = disconnect_side_effect

    def allow_connect(self) -> None:
        """
        Set is_connected of all mocked bleak clients to True.
        """
        self._is_connected = True

    def disconnect(self) -> None:
        """
        Trigger a mock disconnection.

        Set is_connected of all mocked bleak clients to False and
        trigger call on_disconnect callbacks.
        """
        self._is_connected = False
        for bleak_client, dc_callbacks, _ in self._mock_bleak_clients:
            for callback in dc_callbacks:
                callback(bleak_client)

    def expect_ordered_read(self, uuid: str, response: bytes | None) -> None:
        """
        Expect a read.

        Expect an ordered read request to be made to the mock device with
        the specified UUID and optionally return bytes.

        If an unexpected or out of order request is made an error will be
        raised.

        :param uuid: UUID which is expected to be read from.
        :param response: Optional bytes which will be returned.
        """
        self._assertions.append(ReadRequest(uuid, response, False))  # noqa: FBT003

    def expect_ordered_write(
        self,
        uuid: str,
        value: bytes,
        responses: dict[str, bytes] | None = None,
    ) -> None:
        """
        Expect a write.

        Expect an ordered write request to be made to the mock device with
        the specified value and optionally respond with bytes on the specified
        notification uuids.

        The responses parameter is an optional mapping of UUIDs to bytes which
        should be sent as a notification to those UUIDs.

        If an unexpected or out of order request is made an error will be
        raised.

        :param uuid: UUID which is expected to be written to.
        :param value: Expected bytes in write request.
        :param responses: Optional mapping of UUID and bytes responses.
        """
        self._assertions.append(
            WriteRequest(uuid, value, responses or {}, False),  # noqa: FBT003
        )

    async def start_notify(self, uuid: bytes, callback: Callable) -> None:
        """
        Patched :func:`~bleak.BleakClient.start_notify`.

        Patched version of the bleak clients start_notify function
        which will add the callback to the currently active bleak
        client only.

        :param uuid: The UUID the module under test wants notifications of.
        :param callback: The callback the module under test wants executed.
        """
        for client, _, n_callbacks in self._mock_bleak_clients:
            if client is self._current_mock_bleak_client:
                n_callbacks.append((uuid, callback))  # type: ignore[arg-type]

    async def send_notification(self, uuid: str, data: bytes) -> None:
        """
        Sent notification.

        Send the notification on the specified UUID to all clients
        with registered callbacks.

        :param uuid: UUID of notification.
        :param data: Data to send.
        """

        for client, _, n_callbacks in self._mock_bleak_clients:
            for c_uuid, callback in n_callbacks:

                if c_uuid != uuid:
                    continue

                _LOGGER.debug(
                    f"Mock device sending '{data.hex()}' to client '{client}' for callback '{callback}' as notification on '{uuid}'...",  # noqa: E501
                )

                callback(uuid, data)

                # Wait between sending
                await asyncio.sleep(0.1)

    async def write_gatt_char(
        self,
        char_specifier: str,
        data: bytes,
        response: bool = False,  # noqa: ARG002, FBT001, FBT002
    ) -> None:
        """
        Patched :func:`~bleak.BleakClient.write_gatt_char`.

        Patched version of the bleak clients write_gatt_char function
        which will raise an error if the data is not expected and
        will respond with the value to all bleak clients with callbacks
        set if a response is set.

        :param char_specifier: The UUID the module wants to write to.
        :param data: The data the module wants to write.
        :param response: Not used. Bool of if the module wants a response to its write.
        """
        _LOGGER.debug(
            f"Mock device has received write request at: '{char_specifier}' with data: '{data.hex()}'",  # noqa: E501
        )
        error_preamble = f"Received an unexpected write request to: '{char_specifier}' with data: '{data.hex()}'. Expected request {self._position+1}/{len(self._assertions)}'"  # noqa: E501

        def get_request() -> WriteRequest:
            try:
                item = self._assertions[self._position]
                if type(item) is not WriteRequest:
                    print(self._assertions)  # noqa: T201
                    raise AssertionError(  # noqa: TRY003
                        f"{error_preamble} to be a write request but it was '{item}' of type '{type(item)}'.",  # noqa: E501, EM102
                    )
                return item  # noqa: TRY300
            except IndexError:
                print(self._assertions)  # noqa: T201
                raise AssertionError(  # noqa: B904, TRY003
                    f"{error_preamble} to not be made but it was.",  # noqa: EM102
                )

        # Find the request/response for this write
        request = get_request()

        # Assert the UUID matches
        assert (
            request.uuid == char_specifier
        ), f"{error_preamble} to have the UUID '{request.uuid}' but it was '{char_specifier}'!"  # noqa: E501

        # Assert the bytes matches
        assert (
            request.expected == data
        ), f"{error_preamble} to have bytes {request.expected.hex()}' but it was '{data.hex()}'!"  # noqa: E501

        # Increment position
        self._position = self._position + 1
        request.called = True

        # Wait a little
        await asyncio.sleep(0.1)

        # If no response return
        if request.responses is None:
            return

        for resp_uuid, resp_bytes in request.responses.items():
            # Respond with notification to all clients on all callbacks
            # for UUID
            await self.send_notification(resp_uuid, resp_bytes)

    async def read_gatt_char(self, char_specifier: str) -> bytes:
        """
        Patched :func:`~bleak.BleakClient.read_gatt_char`.

        Patched version of the bleak clients read_gatt_char function
        which will raise an error if the request is not expected otherwise
        will respond with the value.

        :param char_specifier: The UUID the module wants to read from.
        :param data: The data the module wants to write.
        """
        _LOGGER.debug(
            f"Mock device has received request for data at: '{char_specifier}'",
        )
        error_preamble = f"Received an unexpected read request of '{char_specifier}'. Expected request {self._position+1}/{len(self._assertions)}'"  # noqa: E501

        def get_request() -> ReadRequest:
            try:
                item = self._assertions[self._position]
                if type(item) is not ReadRequest:
                    print(self._assertions)  # noqa: T201
                    raise AssertionError(  # noqa: TRY003
                        f"{error_preamble} to be a read request but it was '{item}' of type '{type(item)}'.",  # noqa: E501, EM102
                    )
                return item  # noqa: TRY300
            except IndexError:
                print(self._assertions)  # noqa: T201
                raise AssertionError(  # noqa: B904, TRY003
                    f"{error_preamble} to not be made but it was.",  # noqa: EM102
                )

        # Find the request/response for this write
        request = get_request()

        # Assert the UUID matches
        assert (
            request.uuid == char_specifier
        ), f"{error_preamble} to have the UUID '{request.uuid}' but it was '{char_specifier}'!"  # noqa: E501

        # Increment position
        self._position = self._position + 1
        request.called = True

        # Wait a little
        await asyncio.sleep(0.1)

        if request.response is None:
            raise AssertionError(  # noqa: TRY003
                f"{error_preamble} to define a response value but none was defined by the test!",  # noqa: E501, EM102
            )

        return request.response

    def check_assertions(self) -> None:
        """
        Check that all specified requests have been made by the module.
        """
        for i, item in enumerate(self._assertions):
            assert (
                item.called
            ), f"Request {i} with expected bytes '{item.expected.hex()}' was not called!"  # type: ignore[union-attr] # noqa: E501, RUF100, W291

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        """
        Exit context.

        Stops patching :func:`~bleak_retry_connector.establish_connection`.
        """
        self._patcher.stop()
        return False


async def sleep_side_effect(*args: dict, **kwargs: dict) -> None:  # noqa: ARG001
    """
    Sleep side effect.

    Side effect used by some tests for triggering timeouts.
    """
    await asyncio.sleep(999)
