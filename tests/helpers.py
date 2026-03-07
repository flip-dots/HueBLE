"""Helpers for tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from dataclasses import dataclass
from typing import Callable, Union

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Union
from unittest import mock

from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class ReadRequest:
    """
    Internal data class used by MockDevice to keep track of which
    requests have been executed and what the correct response to
    the request is.
    """

    uuid: str
    """
    The expected UUID of the request.
    """

    response: Union[bytes, None]
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
        self._patcher = mock.patch("HueBLE.establish_connection")

        # List of assertions (requests and responses) we expect to be made
        self._assertions: list[Union[ReadRequest, WriteRequest]] = []

        # The most freshly created mock bleak client
        self._current_mock_bleak_client = None

        # The position of the next request we expect to get in the list
        # of assertions
        self._position = 0

        # The value that all our mocked bleak clients will return for
        # client.is_connected. This can be changed dynamically
        self._is_connected = True

    def new_connection_mock(self):
        """
        Executing this causes all new bleak clients created using
        establish_connection to be our mocked versions.
        """

        def custom_init(*args, **kwargs):
            """
            This function is used to create new mock bleak clients whenever
            establish_connection is called.
            """
            _LOGGER.debug(f"New mock bleak client created with '{args}', '{kwargs}'!")

            # We give it a name so we can tell the difference between them in logs
            mock_bleak_client = mock.AsyncMock(
                name=f"bleak_client_{len(self._mock_bleak_clients)}"
            )

            # Set functions/properties
            mock_bleak_client.read_gatt_char.side_effect = self.read_gatt_char
            mock_bleak_client.write_gatt_char.side_effect = self.write_gatt_char
            mock_bleak_client.start_notify.side_effect = self.start_notify
            type(mock_bleak_client).is_connected = mock.PropertyMock(
                side_effect=lambda: self._is_connected
            )

            # Add it to the list of all bleak clients
            self._mock_bleak_clients.append(
                (mock_bleak_client, [kwargs["disconnected_callback"]], [])
            )

            # Set this as the most current bleak client and return it
            self._current_mock_bleak_client = mock_bleak_client
            return mock_bleak_client

        # Use custom_init to manufacture all new bleak clients
        self._establish.side_effect = custom_init

    async def __aenter__(self):
        """Enter the context. Patches establish_connection so all new clients are mocks."""
        self._establish = self._patcher.start()
        self.new_connection_mock()
        return self

    def new_connection_error(self, side_effect: Any):
        """
        Executing this causes all new bleak clients created using
        establish_connection to trigger this side effect.

        :param side_effect: Side effect to trigger (e.g exception).
        """

        self._establish.side_effect = side_effect

    def allow_connect(self):
        """
        Set is_connected of all mocked bleak clients to True.
        """
        self._is_connected = True

    def disconnect(self):
        """
        Set is_connected of all mocked bleak clients to False and
        trigger call on_disconnect callbacks.
        """
        self._is_connected = False
        for bleak_client, dc_callbacks, _ in self._mock_bleak_clients:
            for callback in dc_callbacks:
                callback(bleak_client)

    def expect_ordered_read(self, uuid: str, response: Union[bytes, None]):
        """
        Expect an ordered read request to be made to the mock device with
        the specified UUID and optionally return bytes.

        If an unexpected or out of order request is made an error will be
        raised.

        :param uuid: UUID which is expected to be read from.
        :param response: Optional bytes which will be returned.
        """
        self._assertions.append(ReadRequest(uuid, response, False))

    def expect_ordered_write(
        self, uuid: bytes, value: bytes, responses: Union[dict[str, bytes], None] = None
    ):
        """
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
        self._assertions.append(WriteRequest(uuid, value, responses, False))

    async def start_notify(self, uuid: bytes, callback: Callable):
        """
        Patched version of the bleak clients start_notify function
        which will add the callback to the currently active bleak
        client only.

        :param uuid: The UUID the module under test wants notifications of.
        :param callback: The callback the module under test wants executed.
        """
        for client, _, n_callbacks in self._mock_bleak_clients:
            if client is self._current_mock_bleak_client:
                n_callbacks.append((uuid, callback))

    async def send_notification(self, uuid: str, data: bytes) -> None:
        """
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
                    f"Mock device sending '{data.hex()}' to client '{client}' for callback '{callback}' as notification on '{uuid}'..."
                )

                callback(uuid, data)

                # Wait between sending
                await asyncio.sleep(0.1)

    async def write_gatt_char(
        self, char_specifier: str, data: bytes, response: bool = False
    ) -> None:
        """
        Patched version of the bleak clients write_gatt_char function
        which will raise an error if the data is not expected and
        will respond with the value to all bleak clients with callbacks
        set if a response is set.

        :param char_specifier: The UUID the module wants to write to.
        :param data: The data the module wants to write.
        :param response: Not used. Bool of if the module wants a response to its write.
        """
        _LOGGER.debug(
            f"Mock device has received write request at: '{char_specifier}' with data: '{data.hex()}'"
        )

        # Find the request/response for this write
        request = None
        try:
            request = self._assertions[self._position]
        except IndexError:
            print(self._assertions)
            assert (
                False
            ), f"Received an unexpected request to: '{char_specifier}' with data: '{data.hex()}'. Number: {self._position+1}, Num expected: {len(self._assertions)}"

        # Assert the UUID matches
        assert (
            request.uuid == char_specifier
        ), f"Expected UUID '{request.uuid}' but got '{char_specifier}'!"

        # Assert the bytes matches
        assert (
            request.expected == data
        ), f"Expected bytes {request.expected.hex()}' but got '{data.hex()}'!"

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
        Patched version of the bleak clients read_gatt_char function
        which will raise an error if the request is not expected otherwise
        will respond with the value.

        :param char_specifier: The UUID the module wants to read from.
        :param data: The data the module wants to write.
        """
        _LOGGER.debug(
            f"Mock device has received request for data at: '{char_specifier}'"
        )

        # Find the request/response for this read
        request_response = None
        try:
            request_response = self._assertions[self._position]
        except IndexError:
            print(self._assertions)
            assert (
                False
            ), f"Received an unexpected read request '{char_specifier}'. Number: {self._position+1}, Num expected: {len(self._assertions)}"

        # Assert the UUID matches
        assert (
            request_response.uuid == char_specifier
        ), f"Expected UUID '{request_response.uuid}' but got '{char_specifier}'!"

        # Increment position
        self._position = self._position + 1
        request_response.called = True

        # Wait a little
        await asyncio.sleep(0.1)

        return request_response.response

    def check_assertions(self):
        """
        Check that all specified requests have been made by the module.
        """
        for i, item in enumerate(self._assertions):
            assert (
                item.called
            ), f"Request {i} with expected bytes '{item.expected.hex()}' was not called!"

    async def __aexit__(self, *exc):
        """
        Exit context. Stops patching establish_connection.
        """
        self._patcher.stop()
        return False
