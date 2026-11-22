# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
HueBLE light module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import builtins
import logging
import platform
import uuid
from collections.abc import Callable
from struct import pack, unpack
from typing import Any

from bleak import BleakClient, BleakError
from bleak.backends import BleakBackend
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from HueBLE.const import (
    DEFAULT_CONNECTION_ATTEMPTS_MAX,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_CONNECTION_WAIT_TIMEOUT,
    DEFAULT_MAX_RECONNECT_ATTEMPTS,
    DEFAULT_ON_CONNECT_RUN_CALLBACKS,
    DEFAULT_PAIR_TIMEOUT,
    DEFAULT_POLL_STATE_CALLBACKS_IF_CHANGED,
    DEFAULT_POLL_STATE_TIMEOUT,
    DEFAULT_POLL_WRITES_STATE,
    DEFAULT_READ_GATT_MAX_ATTEMPTS,
    DEFAULT_READ_GATT_TIMEOUT,
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_WRITE_GATT_MAX_ATTEMPTS,
    DEFAULT_WRITE_GATT_TIMEOUT,
    MAX_MIREDS,
    MIN_MIREDS,
    UUID_BRIGHTNESS,
    UUID_CAPABILITY,
    UUID_EFFECTS,
    UUID_FW_VERSION,
    UUID_MANUFACTURER,
    UUID_MODEL,
    UUID_NAME,
    UUID_POWER,
    UUID_TEMPERATURE,
    UUID_XY_COLOUR,
    UUID_ZIGBEE_ADDRESS,
)
from HueBLE.constructs.capability import TLV_CAPABILITY, CapabilityTLVTag
from HueBLE.constructs.effects import TLV_EFFECT, EffectTLVTag, EffectType
from HueBLE.exceptions import (
    CallbackError,
    ConnectionError,  # noqa: A004
    InitialConnectionError,
    NotConnectedError,
    PairingError,
    ReadError,
    ServiceDiscoveryError,
    ServiceSubscriptionError,
    TimeoutError,  # noqa: A004
    WriteError,
)

_LOGGER = logging.getLogger(__name__)


class HueBleLight:
    """Philips Hue BLE Light object."""

    def __init__(self, ble_device: BLEDevice) -> None:
        """Initialise light object. Does not connect automatically."""

        _LOGGER.debug(
            f"""Initializing Hue light "{ble_device.name}" with"""
            f""" address "{ble_device.address}" and details"""
            f""" "{ble_device.details}".""",
        )

        # Internals
        self._ble_device: BLEDevice = ble_device
        self._client: BleakClient | None = None
        self._state_changed_callbacks: list[Callable[[], None]] = []
        self._expect_disconnect: bool = True
        self._connection_attempts: int = 0
        self._connection_lock: asyncio.Lock = asyncio.Lock()
        self._state_update_lock: asyncio.Lock = asyncio.Lock()

        # Light state
        self._manufacturer: str | None = None
        self._model: str | None = None
        self._fw: str | None = None
        self._zigbee_address: str | None = None
        self._light_name: str | None = None
        self._power_on: bool | None = None
        self._brightness: int | None = None
        self._colour_temp: int | None = None
        self._minimum_mireds = MIN_MIREDS
        self._maximum_mireds = MAX_MIREDS
        self._colour_xy: tuple[float, float] | None = None
        self._effect: EffectType | None = None
        self._effect_speed: int | None = None

        # Light feature support
        self._supports_metadata_manufacturer: bool | None = None
        self._supports_metadata_model: bool | None = None
        self._supports_metadata_firmware: bool | None = None
        self._supports_metadata_zigbee_address: bool | None = None
        self._supports_metadata_name_in_app: bool | None = None
        self._supports_metadata_capability: bool | None = None

        self._supports_on_off: bool | None = None
        self._supports_brightness: bool | None = None
        self._supports_colour_temp: bool | None = None
        self._supports_colour_xy: bool | None = None
        self._supports_effects: bool | None = None

    def add_callback_on_state_changed(self, function: Callable[[], None]) -> None:
        """
        Add state change callback.

        Register a callback to be run on device state changes. Triggers
        include changes to power, brightness, temp, colour, and connection
        status.

        .. note::
            Triggers are not dependant on the request being made
            by this program. (e.g If a ZigBee switch or Hue app commands the
            light off the callback will still be run).

        .. warning::
            If a callback raises an exception this will be raised as a
            :exc:`~HueBLE.CallbackError` and will result in all following
            callbacks not being executed.

        :param function: Callable function to execute on state change. Not async.
        """
        self._state_changed_callbacks.append(function)

    def remove_callback(self, function: Callable[[], None]) -> None:
        """
        Remove a state change callback.

        Remove a registered state change callback.

        :param function: Callable function to remove from callbacks list.
        :raises ValueError: If the callable function does not exist in the callbacks.
        """
        self._state_changed_callbacks.remove(function)

    def _run_state_changed_callbacks(self) -> None:
        """
        Execute registered state chance callbacks.

        This executes all registered callbacks for a state change.
        Exceptions are caught and re-raised as a :exc:`~HueBLE.CallbackError`.
        """
        for function in self._state_changed_callbacks:
            try:
                function()
            except Exception as e:
                raise CallbackError(self._ble_device, function, e) from e

    def _disconnect_callback(self, client: BleakClient) -> None:
        """
        Handle unexpected disconnect events.

        This is executed by the :class:`~bleak.BleakClient` when
        connection is lost to the device. This attempts to automatically
        reconnect to the device if we did not expect the disconnect.

        :param client: The BleakClient that issued the disconnect.
        """
        # If the disconnect did not come from the class client then either
        # its null, in which case disconnect() was run and connect() was not
        # or we made a fresh BleakClient and should ignore the disconnect
        # event from the old one, either way we ignore the event.
        # The log message is here to help with debugging in case it causes
        # issues again in future. It can probably be removed in some later version.
        if client != self._client:
            _LOGGER.debug(
                f"""The disconnect came from an unexpected client. The class"""
                f""" client is "{self._client}", but the callback"""
                f""" gave us "{client}". Ignoring disconnect event.""",
            )
            return

        # If we expected the disconnect then we don't try to reconnect.
        if self._expect_disconnect:
            _LOGGER.info(f"""Received expected disconnect from "{client}".""")
            return

        _LOGGER.warning(f"""Unexpected disconnect from "{client}".""")

        # Run callbacks if we did not expect the disconnect
        self._run_state_changed_callbacks()

        if (
            DEFAULT_MAX_RECONNECT_ATTEMPTS == -1
            or self._connection_attempts < DEFAULT_MAX_RECONNECT_ATTEMPTS
        ):

            # Try and reconnect
            # TODO (flip-dots): Replace with more reliable implementation from SolixBLE  # noqa: FIX002, TD003
            self._reconnect_task = asyncio.create_task(self.reconnect())

        else:
            _LOGGER.warning(
                f"""Maximum re-connect attempts to "{client}". exceeded."""
                """ Will NOT attempt reconnect.""",
            )

    async def reconnect(self, reconnect_delay: int = DEFAULT_RECONNECT_DELAY) -> None:
        """
        Disconnect then reconnect to device.

        This function is called when a disconnect callback is raised by the
        :class:`~bleak.BleakClient` and will attempt to reconnect to the device.

        :param reconnect_delay: Delay between calling :func:`~HueBleLight.disconnect` and :func:`~HueBleLight.connect`.
        :raises :exc:`~HueBLE.ConnectionError`: if the connect fails.
        """  # noqa: E501

        _LOGGER.debug(f"""Disconnecting then reconnecting to "{self.address}".""")

        # There *should* be no harm in calling disconnect even if we are
        # already disconnected. We could call self.connected but
        # it might be possible for that to return inaccurate values
        # if the OS starts being silly. Might make sense to do that in the
        # future though, so heads up future me or other equally cool person.
        await self.disconnect()
        await asyncio.sleep(reconnect_delay)
        await self.connect()

    async def _subscribe_to_light_legacy(self, client: BleakClient) -> None:
        """
        Subscribe to individual supported attributes of the device.

        This is the legacy option which subscribes to updated from individual
        attributes (e.g on/off, brightness, etc). This is not the preferred
        option as the effects API will provide us with all this information
        in one call.

        :raises :exc:`~bleak.BleakError`: If unable to subscribe to attribute updates.
        """

        # If turning off an on is supported :|
        if self.supports_on_off:

            def report(_: BleakGATTCharacteristic, data: bytearray) -> None:
                self._power_on = bool(data[0])
                _LOGGER.debug(
                    f"""Light "{self.name}" has informed us of a new"""
                    f""" power state of ({self.power_state})""",
                )
                _LOGGER.debug(f"Light state: {self}")
                self._run_state_changed_callbacks()

            _LOGGER.debug("Subscribing to power state UUID")
            await client.start_notify(UUID_POWER, report)

        # If brightness is supported
        if self.supports_brightness:

            def report(_: BleakGATTCharacteristic, data: bytearray) -> None:
                self._brightness = data[0]
                _LOGGER.debug(
                    f"""Light "{self.name}" has informed us of a new"""
                    f""" brightness state of ({self.brightness})""",
                )
                _LOGGER.debug(f"Light state: {self}")
                self._run_state_changed_callbacks()

            _LOGGER.debug("Subscribing to brightness UUID")
            await client.start_notify(UUID_BRIGHTNESS, report)

        # If colour temperature is supported
        if self.supports_colour_temp:

            def report(_: BleakGATTCharacteristic, data: bytearray) -> None:
                self._colour_temp = int.from_bytes(data, "little")
                _LOGGER.debug(
                    f"""Light "{self.name}" has informed us of a new"""
                    f""" colour temp state of ({self.colour_temp})""",
                )
                _LOGGER.debug(f"Light state: {self}")
                self._run_state_changed_callbacks()

            _LOGGER.debug("Subscribing to colour temperature UUID")
            await client.start_notify(UUID_TEMPERATURE, report)

        # If XY colour is supported
        if self.supports_colour_xy:

            def report(_: BleakGATTCharacteristic, data: bytearray) -> None:
                x, y = unpack("<HH", data)
                self._colour_xy = (x / 0xFFFF, y / 0xFFFF)
                _LOGGER.debug(
                    f"""Light "{self.name}" has informed us of a new"""
                    f""" XY colour state of ({self.colour_xy})""",
                )
                _LOGGER.debug(f"Light state: {self}")
                self._run_state_changed_callbacks()

            _LOGGER.debug("Subscribing to XY colour UUID")
            await client.start_notify(UUID_XY_COLOUR, report)

    async def _subscribe_to_light_modern(self, client: BleakClient) -> None:
        """
        Subscribe to the effects API of the device.

        This is the preferred way to receive state updates from the device
        as the effects API reports on all state changes.

        :raises :exc:`~bleak.BleakError`: If unable to subscribe to attribute updates.
        """

        def report(_: BleakGATTCharacteristic, data: bytearray) -> None:

            _LOGGER.debug(f"Effect bytes: {data.hex()}")
            tlv = TLV_EFFECT.parse(data)
            _LOGGER.debug(f"Parsed effect TLV: {tlv}")

            state_difference: dict[str, tuple[Any, Any]] = {}

            power_on = tlv.get(EffectTLVTag.ON_OFF)
            if power_on != self._power_on:
                state_difference[EffectTLVTag.ON_OFF.name] = (self._power_on, power_on)
                self._supports_on_off = True
                self._power_on = power_on

            brightness = tlv.get(EffectTLVTag.BRIGHTNESS)
            if brightness != self._brightness:
                state_difference[EffectTLVTag.BRIGHTNESS.name] = (
                    self._brightness,
                    brightness,
                )
                self._supports_brightness = True
                self._brightness = brightness

            colour_temp = tlv.get(EffectTLVTag.COLOUR_TEMP)
            if colour_temp != self._colour_temp:
                state_difference[EffectTLVTag.COLOUR_TEMP.name] = (
                    self._colour_temp,
                    colour_temp,
                )
                self._supports_colour_temp = True
                self._colour_temp = colour_temp

            colour_xy = tlv.get(EffectTLVTag.COLOUR_XY)
            if colour_xy != self._colour_xy:
                state_difference[EffectTLVTag.COLOUR_XY.name] = (
                    self._colour_xy,
                    colour_xy,
                )
                self._supports_colour_xy = True
                self._colour_xy = colour_xy

            effect_type = tlv.get(EffectTLVTag.EFFECT_TYPE)
            if effect_type != self._effect:
                state_difference[EffectTLVTag.EFFECT_TYPE.name] = (
                    self._effect,
                    effect_type,
                )
                self._supports_effects = True
                self._effect = effect_type

            effect_speed = tlv.get(EffectTLVTag.EFFECT_SPEED)
            if effect_speed != self._effect_speed:
                state_difference[EffectTLVTag.EFFECT_SPEED.name] = (
                    self._effect_speed,
                    effect_speed,
                )
                self._supports_effects = True
                self._effect_speed = effect_speed

            _LOGGER.debug(
                f"""Light "{self.name}" has informed us of a new"""
                f""" Effect state of ({self.effect}) with diff ({state_difference})""",
            )
            _LOGGER.debug(f"Light state: {self}")

            if state_difference:
                self._run_state_changed_callbacks()

        _LOGGER.debug("Subscribing to Effects UUID")
        await client.start_notify(UUID_EFFECTS, report)

    async def _subscribe_to_light(self) -> None:
        """
        Subscribe to supported attributes of the device.

        This is called on :func:`~HueBleLight.connect` and subscribes to state updates
        of supported attributes of the device (e.g on/off brightness, etc). Service
        discovery must be performed before this is called using
        :func:`~HueBleLight._determine_services`.

        :raises :exc:`~HueBLE.NotConnectedError`: If not connected to the device.
        :raises :exc:`~bleak.BleakError`: If unable to subscribe to attribute updates.
        """

        if self._client is None:
            raise NotConnectedError

        # Use effects API for state updates if available
        if self.supports_effects:
            await self._subscribe_to_light_modern(self._client)

        # Else use legacy individual attributes
        else:
            await self._subscribe_to_light_legacy(self._client)

    async def connect(  # noqa: C901
        self,
        max_attempts: int = DEFAULT_CONNECTION_ATTEMPTS_MAX,
        connection_timeout: int = DEFAULT_CONNECTION_TIMEOUT,
        wait_timeout: int = DEFAULT_CONNECTION_WAIT_TIMEOUT,
        run_callbacks: bool = DEFAULT_ON_CONNECT_RUN_CALLBACKS,  # noqa: FBT001
    ) -> None:
        """
        Establish connection to the device.

        This function will establish a BLE connection to the device
        and attempt to pair if necessary.

        .. note::
            This is automatically called when a connection to the device is needed to
            perform an action (e.g :exc:`~HueBLE.HueBleLight.set_power` will
            automatically call connect if not already connected).

        .. warning::
            Connecting to a light will not automatically populate values (e.g
            :func:`~HueBLE.HueBleLight.brightness`,
             :func:`~HueBLE.HueBleLight.manufacturer`, etc). Some values like
             :func:`~HueBLE.HueBleLight.brightness` will be populated by state updates
             from the device but others such as :func:`~HueBLE.HueBleLight.manufacturer`
             must be polled, in this example using either
             :func:`~HueBLE.HueBleLight.poll_manufacturer` or
             :func:`~HueBLE.HueBleLight.poll_state`.

        .. note::
            This function uses a lock to ensure that only one connection attempt may
            performed at any one point.

        .. warning::
            Pairing is not supported on MacOS and must be done in the operating system
            settings.

        .. note::
            It is only possible for the program to determine if it is paired to a device
            on Linux, on other platforms this information is not available and pairing
            will be performed even if the device is already paired, but this has no
            adverse affects (pairing if you are already paired always works even if
            the light is no longer in a pairing state).


        :param max_attempts: Maximum number of attempts before failing.
        :param connection_timeout: Maximum time to successfully connect before retry.
        :param wait_timeout: Maximum time to wait for a connection lock.
        :param run_callbacks: If callbacks should be executed on success.

        :raises :exc:`~HueBLE.ConnectionError`: on failure.
        :raises :exc:`~HueBLE.CallbackError`: if any callback raises an exception.
        """

        # If we are already connected then do nothing
        if self.connected:
            _LOGGER.debug(f"""Already connected to "{self.name}" Nothing to do here.""")
            return

        # Print warning that the connection is already in progress by
        # another method.
        if self._connection_lock.locked():
            _LOGGER.debug(
                f"""Connection already in progress to "{self.name}"."""
                f""" Waiting for it to complete...""",
            )

        # Timeout if waiting too long
        # Idea is to prevent a large queue from forming
        try:
            async with asyncio.timeout(wait_timeout):

                # Use a lock to prevent the library from trying to connect
                # to the same light at the same time from different methods.
                async with self._connection_lock:

                    # If we are now connected after waiting for the lock to
                    # release then do nothing.
                    if self.connected:
                        _LOGGER.debug(
                            f"""Now connected to "{self.name}" after waiting"""
                            f""" for lock release""",
                        )
                        return

                    _LOGGER.debug(
                        f"""Connecting to "{self.name}" with address"""
                        f""" "{self.address}".""",
                    )

                    # Increment attempts
                    self._connection_attempts += 1

                    # Maximum time to make a connection
                    try:
                        async with asyncio.timeout(connection_timeout):

                            # Make a fresh bleak client and connect
                            try:
                                self._client = await establish_connection(
                                    BleakClient,
                                    device=self._ble_device,
                                    name=self.address,
                                    max_attempts=max_attempts,
                                    disconnected_callback=self._disconnect_callback,
                                )
                                _LOGGER.debug(
                                    f"""Using client "{self._client}" with """
                                    f"""backend "{self._client.backend_id}".""",
                                )

                                # If we failed to connect
                                if not self._client.is_connected:
                                    raise NotConnectedError  # noqa: TRY301

                            except Exception as e:
                                raise InitialConnectionError(
                                    self._ble_device,
                                    e,
                                ) from e

                            # Attempt to pair if not paired
                            _LOGGER.debug("Attempting to pair to the light...")
                            await self.pair()

                            # Determine what features the light supports
                            try:
                                _LOGGER.debug(
                                    "Determining services offered by the light...",
                                )
                                await self._determine_services()
                            except Exception as e:
                                raise ServiceDiscoveryError(self._ble_device, e) from e

                            # Subscribe to updates from the features the device supports
                            try:
                                _LOGGER.debug(
                                    "Subscribing to services offered by the light...",
                                )
                                await self._subscribe_to_light()
                            except Exception as e:
                                raise ServiceSubscriptionError(
                                    self._ble_device,
                                    e,
                                ) from e

                            # If the connection was successful, and we are paired,
                            # authenticated, and subscribed, then we no longer
                            # expect to be disconnected
                            self._expect_disconnect = False

                            # We also reset the attempts counter since we succeeded
                            self._connection_attempts = 0

                            # If we have reached here that means connecting and
                            # pairing was (probably) successful since we have now
                            # subscribed to updates
                            _LOGGER.debug(
                                f"""Successfully connected and authenticated"""
                                f""" to "{self.name}".""",
                            )

                            # We then exit the timeout context, run callbacks if
                            # required, since we have achieved a connection then return

                    except builtins.TimeoutError as e:
                        raise TimeoutError(  # noqa: TRY003
                            f"""Timed out attempting to connect to "{self.name}".""",  # noqa: EM102
                        ) from e

        except builtins.TimeoutError as e:
            raise TimeoutError(  # noqa: TRY003
                f"""Timed out waiting for connection lock for "{self.name}".""",  # noqa: EM102
            ) from e

        except Exception as e:
            raise ConnectionError(
                self._ble_device,
                e,
            ) from e

        if run_callbacks:
            self._run_state_changed_callbacks()

        return

    async def pair(self) -> None:
        """
        Pair to the device.

        This function attempts to pair to the device if the pairing
        status is not paired or unknown.

        .. warning::
            Pairing is not supported on MacOS and must be done in the operating system
            settings. In this case the function will log a warning and return.

        .. note::
            It is only possible for the program to determine if it is paired to a device
            on Linux, on other platforms this information is not available and pairing
            will be performed even if the device is already paired, but this has no
            adverse affects (pairing if you are already paired always works even if
            the light is no longer in a pairing state).

        :raises :exc:`~HueBLE.NotConnectedError`: If not connected.
        :raises :exc:`~HueBLE.PairingError`: If pairing is unsuccessful.
        """

        if self._client is None or not self._client.is_connected:
            raise NotConnectedError

        # If paired return
        if self.authenticated is True:
            _LOGGER.debug(f"""System is already paired to "{self.name}".""")
            return

        # If mac return as pairing is not supported on MacOS
        if platform.system() == "Darwin":
            _LOGGER.warning(
                "Pairing is not supported on MacOS! You must pair manually!",
            )
            return

        # Else attempt to pair with a timeout
        try:
            _LOGGER.debug(f"""Attempting to pair to "{self.name}".""")
            async with asyncio.timeout(DEFAULT_PAIR_TIMEOUT):

                if self._client.backend_id is BleakBackend.BLUEZ_DBUS:
                    _LOGGER.debug("Using bluez workaround...")
                    await self._pair_bluez()
                else:
                    await self._client.pair()

        except builtins.TimeoutError as e:
            raise PairingError(  # noqa: TRY003
                f"""Timed out attempting to pair to "{self.name}".""",  # noqa: EM102
            ) from e

        except BleakError as e:
            raise PairingError(  # noqa: TRY003
                f"""Error from BLE backend pairing to "{self.name}". E: "{e}".""",  # noqa: EM102
            ) from e

        return

    async def _pair_bluez(self) -> None:
        """
        Workaround for pairing on BlueZ Linux systems.

        There is a bug in current BlueZ versions which prevents pairing
        from working. This workaround gets around that by using some
        trickery. `See #8 <https://github.com/flip-dots/HueBLE/pull/8>`_.

        :raises :exc:`~HueBLE.NotConnectedError`: If not connected.
        :raises Exception: There are a lot of ways this can go wrong.
        """
        from dbus_fast import BusType  # noqa: PLC0415
        from dbus_fast.aio import MessageBus  # noqa: PLC0415
        from dbus_fast.service import ServiceInterface, method  # noqa: PLC0415

        if self._client is None or not self._client.is_connected:
            raise NotConnectedError

        class BluezAgent(ServiceInterface):
            """Agent for automatically accepting pairing passkeys."""

            def __init__(self) -> None:
                """Init pairing agent."""
                super().__init__("org.bluez.Agent1")

            @method()
            def RequestConfirmation(self, device: "o", passkey: "u") -> None:  # type: ignore  # noqa: F821, N802, PGH003
                _LOGGER.debug(f"Auto confirming passkey {passkey} for {device}")

            @method()
            def Cancel(self) -> None:  # noqa: N802
                _LOGGER.debug("Pairing cancelled by device")

        # Build agent
        _LOGGER.debug("Setting up pairing agent...")
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        agent = BluezAgent()
        unique_id = uuid.uuid4().hex[:8]
        agent_path = f"/com/bleak/agent/hue_ble/{unique_id}"
        bus.export(agent_path, agent)

        # Register agent
        introspection = await bus.introspect("org.bluez", "/org/bluez")
        proxy_object = bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
        agent_manager = proxy_object.get_interface("org.bluez.AgentManager1")
        await agent_manager.call_register_agent(agent_path, "KeyboardDisplay")  # type: ignore[attr-defined]
        _LOGGER.debug("Pairing agent ready!")

        async with asyncio.timeout(DEFAULT_PAIR_TIMEOUT):

            try:
                await asyncio.sleep(1)
                _LOGGER.debug("Sending pairing command...")
                await self._client.pair()
            finally:
                _LOGGER.debug("Stopping pairing agent...")
                await agent_manager.call_unregister_agent(agent_path)  # type: ignore[attr-defined]
                bus.unexport(agent_path, agent)
                bus.disconnect()

    async def _determine_services(self) -> None:
        """
        Determine available features.

        Determines what features the device supports. The data may then be
        retrieved via the supports properties.

        :raises :exc:`~HueBLE.NotConnectedError`: If not connected.
        :raises :exc:`~bleak.BleakError`: If unable to determine services offered.
        """

        # If debug mode enabled print all services offered by light as well as the
        # readable values
        if _LOGGER.isEnabledFor(logging.DEBUG):
            await self.print_services()

        if self._client is None:
            raise NotConnectedError

        self._supports_metadata_manufacturer = (
            self._client.services.get_characteristic(UUID_MANUFACTURER) is not None
        )
        self._supports_metadata_model = (
            self._client.services.get_characteristic(UUID_MODEL) is not None
        )
        self._supports_metadata_firmware = (
            self._client.services.get_characteristic(UUID_FW_VERSION) is not None
        )
        self._supports_metadata_zigbee_address = (
            self._client.services.get_characteristic(UUID_ZIGBEE_ADDRESS) is not None
        )
        self._supports_metadata_name_in_app = (
            self._client.services.get_characteristic(UUID_NAME) is not None
        )
        self._supports_metadata_capability = (
            self._client.services.get_characteristic(UUID_CAPABILITY) is not None
        )
        self._supports_on_off = (
            self._client.services.get_characteristic(UUID_POWER) is not None
        )
        self._supports_brightness = (
            self._client.services.get_characteristic(UUID_BRIGHTNESS) is not None
        )
        self._supports_colour_temp = (
            self._client.services.get_characteristic(UUID_TEMPERATURE) is not None
        )
        self._supports_colour_xy = (
            self._client.services.get_characteristic(UUID_XY_COLOUR) is not None
        )
        self._supports_effects = (
            self._client.services.get_characteristic(UUID_EFFECTS) is not None
        )

    async def disconnect(self) -> None:
        """
        Disconnect from device.

        Disconnects the program from the device, does not
        attempt reconnection, and does not run callbacks.
        """

        self._expect_disconnect = True
        # If the client does not exist return
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        except TimeoutError:
            _LOGGER.exception(
                f"""Timeout attempting to disconnect from "{self.name}".""",
            )
        except BleakError:
            _LOGGER.exception(
                f"""BleakError attempting to disconnect from "{self.name}".""",
            )

        # Throw away the client
        self._client = None

    async def poll_state(  # noqa: C901, PLR0912, PLR0915
        self,
        timeout: int = DEFAULT_POLL_STATE_TIMEOUT,  # noqa: ASYNC109
        run_callbacks_if_changed: bool = DEFAULT_POLL_STATE_CALLBACKS_IF_CHANGED,  # noqa: FBT001
    ) -> bool:
        """
        Poll all supported attributes of the device.

        Updates the local state with values from the light using polling.

        .. note::
            This will only populate the fields that the light supports (i.e it
            should not error out if your light does not support colour).
            A lock is used to only allow one state update at a time with
            a timeout. Any callbacks are run outside of the state lock but
            within the timeout lock.

        If unable to determine services offered.

        :param timeout: Maximum time to allow for polling all values.
        :param run_callbacks_if_changed: Run callbacks if the state changed.
        :returns: Has the state of the device changed.
        :raises :exc:`~HueBLE.ReadWriteError`: If reading values from the device failed.
        :raises :exc:`~asyncio.TimeoutError`: If polling timed out.
        """
        state_changed = False

        if self._state_update_lock.locked():
            _LOGGER.debug(
                f"""Waiting for state update lock of "{self.name}" to be"""
                f""" released.""",
            )

        # Timeout if waiting too long
        async with asyncio.timeout(timeout):

            # Only one device may poll at a time
            async with self._state_update_lock:
                _LOGGER.debug(f"""Processing state update request for "{self.name}".""")

                if self._supports_metadata_manufacturer:
                    if self.manufacturer != await self.poll_manufacturer(
                        write_state=True,
                    ):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling manufacturer")

                if self._supports_metadata_model:
                    if self.model != await self.poll_model(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling model")

                if self._supports_metadata_firmware:
                    if self.firmware != await self.poll_firmware(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling firmware version")

                if self._supports_metadata_zigbee_address:
                    if self.zigbee_address != await self.poll_zigbee_address(
                        write_state=True,
                    ):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling ZigBee address")

                if self._supports_metadata_name_in_app:
                    if self.name_in_app != await self.poll_light_name(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling light name")

                if self._supports_metadata_capability:
                    if (
                        self.minimum_mireds,
                        self.maximum_mireds,
                    ) != await self.poll_capability(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling capabilities")

                if self.supports_effects:
                    if self.effect != await self.poll_effects(write_state=True):
                        state_changed = True

                # If the effects API is supported then we do not need to poll the
                # other values as the effects API will contain the same info
                else:
                    _LOGGER.debug("Light does not support polling effects")

                    if self.supports_on_off:
                        if self.power_state != await self.poll_power_state(
                            write_state=True,
                        ):
                            state_changed = True
                    else:
                        _LOGGER.debug("Light does not support polling power state")

                    if self.supports_brightness:
                        if self.brightness != await self.poll_brightness(
                            write_state=True,
                        ):
                            state_changed = True
                    else:
                        _LOGGER.debug("Light does not support polling brightness")

                    if self.supports_colour_temp:
                        if self.colour_temp != await self.poll_colour_temp(
                            write_state=True,
                        ):
                            state_changed = True
                    else:
                        _LOGGER.debug("Light does not support polling colour temp")

                    if self.supports_colour_xy:
                        if self.colour_xy != await self.poll_colour_xy(
                            write_state=True,
                        ):
                            state_changed = True
                    else:
                        _LOGGER.debug("Light does not support polling XY colour")

                # Print it all out for debugging
                _LOGGER.debug(f"Light state: {self}")

            # Callbacks are run outside of the state update lock
            if run_callbacks_if_changed and state_changed:
                self._run_state_changed_callbacks()

        return state_changed

    async def _read_gatt(
        self,
        address: str,
        attempt_timeout: int = DEFAULT_READ_GATT_TIMEOUT,
        max_attempts: int = DEFAULT_READ_GATT_MAX_ATTEMPTS,
    ) -> bytearray:
        """
        Read GATT characteristic from device.

        Return the value of the address with automatic connection
        and retry on failure.

        :param address: GATT characteristic to read.
        :param attempt_timeout: Maximum amount of time for a read attempt.
        :param max_attempts: Maximum number of attempts before giving up.
        :returns: Data at address.
        :raises :exc:`~HueBLE.ReadError`: If all attempts have failed.
        """
        _LOGGER.debug(f"""Reading bytes at '{address}' from '{self.name}'...""")
        last_error = None
        for i in range(1, max_attempts + 1):
            try:
                async with asyncio.timeout(attempt_timeout):
                    if not self.connected:
                        _LOGGER.debug(
                            "Not connected. Executing connect before proceeding...",
                        )
                        await self.connect()
                    if self._client is None:
                        raise NotConnectedError  # noqa: TRY301
                    value = await self._client.read_gatt_char(address)
                    _LOGGER.debug(
                        f"Successfully read '{value.hex()}' from '{self.name}'.",
                    )
                    return value

            except Exception as e:  # noqa: BLE001
                _LOGGER.debug(
                    f"""Failed to read value from '{self.name}' on attempt"""
                    f""" {i}/{max_attempts}. Error message '{e}'.""",
                )
                last_error = e
        raise ReadError(self._ble_device, address, i, last_error) from last_error

    async def _write_gatt(
        self,
        address: str,
        data: bytes,
        attempt_timeout: int = DEFAULT_WRITE_GATT_TIMEOUT,
        max_attempts: int = DEFAULT_WRITE_GATT_MAX_ATTEMPTS,
    ) -> None:
        """
        Write GATT characteristic to device.

        Write the data to the address with automatic connection
        and retry on failure.

        :param address: GATT characteristic to write.
        :param data: Data to write to address.
        :param attempt_timeout: Maximum amount of time for a read attempt.
        :param max_attempts: Maximum number of attempts before giving up.
        :raises :exc:`~HueBLE.WriteError`: If all attempts have failed.
        """
        _LOGGER.debug(
            f"""Writing bytes "{data.hex()}" at "{address}" to "{self.name}"...""",
        )
        last_error = None
        for i in range(1, max_attempts + 1):
            try:
                async with asyncio.timeout(attempt_timeout):
                    if not self.connected:
                        _LOGGER.debug(
                            "Not connected. Executing connect before proceeding",
                        )
                        await self.connect()
                    if self._client is None:
                        raise NotConnectedError  # noqa: TRY301
                    return await self._client.write_gatt_char(
                        address,
                        data,
                        response=True,
                    )

            except Exception as e:  # noqa: BLE001
                _LOGGER.debug(
                    f"""Failed to write value to "{self.name}" on attempt"""
                    f""" {i}/{max_attempts}. Error message "{e}".""",
                )
                last_error = e
        raise WriteError(self._ble_device, address, data, i, last_error) from last_error

    async def print_services(self) -> None:
        """
        Print all available GATT services in the debug log.

        This prints all services advertised by the device in the debug log.
        Based on: `<https://github.com/hbldh/bleak/blob/develop/examples/service_explorer.py>`_.

        :raises :exc:`~HueBLE.NotConnectedError`: If not connected to device.
        """
        if self._client is None:
            raise NotConnectedError

        _LOGGER.debug("==== START SERVICES ====")
        for service in self._client.services:
            _LOGGER.debug("[Service] %s", service)

            for char in service.characteristics:
                if "read" in char.properties:
                    try:
                        value = await self._client.read_gatt_char(char.uuid)
                        extra = f", Value: {value}"
                    except BleakError as e:
                        extra = f", Error: {e}"
                else:
                    extra = ""

                _LOGGER.debug(
                    "  [Characteristic] %s (%s)%s",
                    char,
                    ",".join(char.properties),
                    extra,
                )

                for descriptor in char.descriptors:
                    try:
                        value = await self._client.read_gatt_descriptor(
                            descriptor.handle,
                        )
                        _LOGGER.debug(
                            "    [Descriptor] %s, Value: %r",
                            descriptor,
                            value,
                        )
                    except BleakError as e:
                        _LOGGER.debug("    [Descriptor] %s, Error: %s", descriptor, e)
        _LOGGER.debug("==== END SERVICES ====")

    async def poll_manufacturer(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> str:
        """
        Poll manufacturer data from device.

        Poll the manufacturer data from the device (e.g Signify Netherlands B.V.).

        :param write_state: Write returned value to internal state.
        :returns: Manufacture metadata.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_MANUFACTURER)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._manufacturer = decoded
        return decoded

    async def poll_model(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> str:
        """
        Poll model data from device.

        Poll the model data from the device (e.g LCA006).

        :param write_state: Write returned value to internal state.
        :returns: Model metadata.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_MODEL)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._model = decoded
        return decoded

    async def poll_firmware(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> str:
        """
        Poll firmware version from device.

        Poll the firmware version from the device (e.g 1.145.1).

        :param write_state: Write returned value to internal state.
        :returns: Firmware version.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_FW_VERSION)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._fw = decoded
        return decoded

    async def poll_zigbee_address(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> str:
        """
        Poll Zigbee address from device.

        Poll the Zigbee address from the device (e.g f4:2e:7f:0c:01:88:17:00).

        :param write_state: Write returned value to internal state.
        :returns: Zigbee address.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_ZIGBEE_ADDRESS)
        decoded = encoded.hex(sep=":")
        if write_state:
            self._zigbee_address = decoded
        return decoded

    async def poll_light_name(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> str:
        """
        Poll name of light.

        Poll the name of the light as shown in the Hue app (e.g Desk Right).

        :param write_state: Write returned value to internal state.
        :returns: Light name as shown in app.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_NAME)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._light_name = decoded
        return decoded

    async def poll_power_state(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> bool:
        """
        Poll on/off status of light.

        Poll the on/off status of the light (e.g true=on, off=false).

        :param write_state: Write returned value to internal state.
        :returns: Power state of device.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_POWER)
        decoded = bool(encoded[0])
        if write_state:
            self._power_on = decoded
        return decoded

    async def poll_brightness(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> int:
        """
        Poll brightness of light.

        Poll the brightness of the light (0=min, 254=max inclusive).

        :param write_state: Write returned value to internal state.
        :returns: Brightness of light.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_BRIGHTNESS)
        decoded = encoded[0]
        if write_state:
            self._brightness = decoded
        return decoded

    async def poll_colour_temp(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> int:
        """
        Poll colour temperature of the light.

        Poll the colour temperature of the light in mireds.
        The minimum is 153 and maximum is 500 for most models.

        .. note::
            Colour temperature mode is inactive if XY colour
            is (0.0, 0.0) or (1.0, 1.0).

        :param write_state: Write returned value to internal state.
        :returns: Colour temperature of the light.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        encoded = await self._read_gatt(UUID_TEMPERATURE)
        decoded = int.from_bytes(encoded, "little")
        if write_state:
            self._colour_temp = decoded
        return decoded

    async def poll_colour_xy(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> tuple[float, float]:
        """
        Poll colour of the light.

        Poll the colour of the light in the XY colour space.
        The minimum is (0.0, 0.0) and maximum is (1.0, 1.0).

        .. note::
            Is (0.0, 0.0) or (1.0, 1.0) if XY colour mode is inactive.

        :param write_state: Write returned value to internal state.
        :returns: XY colour of the light.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        buf = await self._read_gatt(UUID_XY_COLOUR)
        x, y = unpack("<HH", buf)
        x_after = x / 0xFFFF
        y_after = y / 0xFFFF
        if write_state:
            self._colour_xy = (x_after, y_after)
        return x_after, y_after

    async def poll_effects(  # noqa: C901
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> tuple[EffectType, int] | tuple[None, None]:
        """
        Poll effect state of the light.

        Poll the effect type and effect speed of the light, the
        minimum speed is 0 and maximum is 254.

        :param write_state: Write returned value to internal state.
        :returns: Effect state of light. Is tuple of None if effects are inactive.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        data = await self._read_gatt(UUID_EFFECTS)
        tlv = TLV_EFFECT.parse(data)
        _LOGGER.debug(f"Parsed effect TLV: {tlv}")

        state_difference: dict[str, tuple[Any, Any]] = {}

        power_on = tlv.get(EffectTLVTag.ON_OFF)
        if power_on != self._power_on:
            state_difference[EffectTLVTag.ON_OFF.name] = (self._power_on, power_on)
            if write_state:
                self._supports_on_off = True
                self._power_on = power_on

        brightness = tlv.get(EffectTLVTag.BRIGHTNESS)
        if brightness != self._brightness:
            state_difference[EffectTLVTag.BRIGHTNESS.name] = (
                self._brightness,
                brightness,
            )
            if write_state:
                self._supports_brightness = True
                self._brightness = brightness

        colour_temp = tlv.get(EffectTLVTag.COLOUR_TEMP)
        if colour_temp != self._colour_temp:
            state_difference[EffectTLVTag.COLOUR_TEMP.name] = (
                self._colour_temp,
                colour_temp,
            )
            if write_state:
                self._supports_colour_temp = True
                self._colour_temp = colour_temp

        colour_xy = tlv.get(EffectTLVTag.COLOUR_XY)
        if colour_xy != self._colour_xy:
            state_difference[EffectTLVTag.COLOUR_XY.name] = (
                self._colour_xy,
                colour_xy,
            )
            if write_state:
                self._supports_colour_xy = True
                self._colour_xy = colour_xy

        effect_type = tlv.get(EffectTLVTag.EFFECT_TYPE)
        if effect_type != self._effect:
            state_difference[EffectTLVTag.EFFECT_TYPE.name] = (
                self._effect,
                effect_type,
            )
            if write_state:
                self._effect = effect_type

        effect_speed = tlv.get(EffectTLVTag.EFFECT_SPEED)
        if effect_speed != self._effect_speed:
            state_difference[EffectTLVTag.EFFECT_SPEED.name] = (
                self._effect_speed,
                effect_speed,
            )
            if write_state:
                self._effect_speed = effect_speed

        return effect_type, effect_speed

    async def poll_capability(
        self,
        write_state: bool = DEFAULT_POLL_WRITES_STATE,  # noqa: FBT001
    ) -> tuple[int, int] | tuple[None, None]:
        """
        Poll capability of the light.

        In the current implementation this returns the minimum and maximum
        supported colour temperature values but may be extended in future
        to add support for reading more values as they are decoded.

        :param write_state: Write returned value to internal state.
        :returns: Minimum and maximum supported colour temperatures.
        :raises :exc:`~HueBLE.ReadError`: If unable to read from device.
        """
        data = await self._read_gatt(UUID_CAPABILITY)
        tlv = TLV_CAPABILITY.parse(data)
        _LOGGER.debug(f"Parsed capability TLV: {tlv}")

        state_difference: dict[str, tuple[Any, Any]] = {}

        min_colour_temp = tlv.get(CapabilityTLVTag.MINIMUM_COLOUR_TEMP)
        if min_colour_temp != self._minimum_mireds:
            state_difference[CapabilityTLVTag.MINIMUM_COLOUR_TEMP.name] = (
                self._minimum_mireds,
                min_colour_temp,
            )
            if write_state:
                self._supports_metadata_capability = True
                self._minimum_mireds = min_colour_temp

        max_colour_temp = tlv.get(CapabilityTLVTag.MAXIMUM_COLOUR_TEMP)
        if max_colour_temp != self._maximum_mireds:
            state_difference[CapabilityTLVTag.MAXIMUM_COLOUR_TEMP.name] = (
                self._maximum_mireds,
                max_colour_temp,
            )
            if write_state:
                self._supports_metadata_capability = True
                self._maximum_mireds = max_colour_temp

        return min_colour_temp, max_colour_temp

    async def set_light_name(self, name: str) -> None:
        """
        Write device name.

        Write a new device name to the device.

        .. warning::
            This is untested and could result in the device being bricked.
            if misused. Use at even more of your own risk.

        :param name: Name to write to device.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """

        """Sets the name of the light. Not tested, use at own risk."""
        await self._write_gatt(UUID_NAME, str.encode(name))

    async def set_power(
        self,
        on: bool,  # noqa: FBT001
        transition_ms: int | None = None,
    ) -> None:
        """
        Set the power state of the device.

        Turn the device on/off with an optional transition time.

        :param on: Turn the light on, else turn the light off.
        :param transition_ms: Transition time in milliseconds, requires effect support.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """
        if transition_ms is None:
            await self._write_gatt(UUID_POWER, bytes([1 if on else 0]))
            return

        await self.set_effect(power=on, transition=transition_ms // 100)

    async def set_brightness(
        self,
        brightness: int,
        transition_ms: int | None = None,
    ) -> None:
        """
        Set the brightness of the light.

        Set the brightness of the light with an optional transition time.

        :param brightness: Brightness to set light to (0 min, 254 max inclusive).
        :param transition_ms: Transition time in milliseconds, requires effect support.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """
        brightness = max(min(brightness, 254), 1)
        if transition_ms is None:
            await self._write_gatt(UUID_BRIGHTNESS, bytes([brightness]))
            return

        await self.set_effect(brightness=brightness, transition=transition_ms // 100)

    async def set_colour_temp(
        self,
        colour_temp: int,
        transition_ms: int | None = None,
    ) -> None:
        """
        Set the colour temperature of the light.

        Set the colour temperature of the light in mireds with an
        optional transition time. Typically a light will support
        a minimum of 153 and maximum of 500 inclusive.

        :param colour_temp: Colour temperature to set light to in mireds.
        :param transition_ms: Transition time in milliseconds, requires effect support.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """
        temp = max(min(int(colour_temp), 500), 153)
        data = temp.to_bytes(2, "little")
        if transition_ms is None:
            await self._write_gatt(UUID_TEMPERATURE, data)
            return

        await self.set_effect(colour=colour_temp, transition=transition_ms // 100)

    async def set_colour_xy(
        self,
        x: float,
        y: float,
        transition_ms: int | None = None,
    ) -> None:
        """
        Set the XY colour of the light.

        Set the colour of the light in the XY colour space with an
        optional transition time.

        :param x: The X colour coordinate (min 0.0, max 1.0).
        :param y: The Y colour coordinate (min 0.0, max 1.0).
        :param transition_ms: Transition time in milliseconds, requires effect support.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """
        data = pack("<HH", int(x * 0xFFFF), int(y * 0xFFFF))
        if transition_ms is None:
            await self._write_gatt(UUID_XY_COLOUR, data)
            return

        await self.set_effect(colour=(x, y), transition=transition_ms // 100)

    async def set_effect(  # noqa: C901, PLR0912, PLR0913, PLR0917
        self,
        power: bool | None = None,  # noqa: FBT001
        brightness: int | None = None,
        colour: int | tuple[float, float] | None = None,
        effect: EffectType | None = None,
        effect_speed: int | None = None,
        transition: int | None = None,
    ) -> None:
        """
        Set the state of the light using the effects API.

        .. note::
            This API can be used to send non-effect commands to
            the light (e.g on-off, brightness, etc).

        .. note::
           This API may not be supported by all lights.

        :param power: Optionally set the power state of the light.
        :param brightness: Optionally set brightness of the light (0-255 excl 0 & 255).
        :param colour: Optionally set the colour of the light.
        :param effect: Optionally set the effect of the light.
        :param effect_speed: Optionally set the effect speed (0-255 excl 255).
        :param transition: Optionally set the transition speed in hundredths of milliseconds (e.g 1 = 100ms).
        :raises ValueError: If an invalid/out of range argument was provided.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """  # noqa: E501
        command_args: dict[EffectTLVTag, Any] = {}

        if power is not None:
            command_args[EffectTLVTag.ON_OFF] = power

        if brightness is not None:
            if not (0 < brightness < 255):  # noqa: PLR2004
                raise ValueError(  # noqa: TRY003
                    f"Brightness was '{brightness}' but must be above 0 and below 255 (excl 0 and 255)",  # noqa: E501, EM102
                )
            command_args[EffectTLVTag.BRIGHTNESS] = brightness

        if colour is not None and type(colour) is int:
            if not (0 < colour < 1000):  # noqa: PLR2004
                raise ValueError(  # noqa: TRY003
                    f"Colour temp was '{colour}' but must be above 0 and below 1000 (excl 0 and 1000)",  # noqa: E501, EM102
                )
            command_args[EffectTLVTag.COLOUR_TEMP] = colour
        elif colour is not None and type(colour) is tuple:
            x, y = colour
            if not (0.0 < x < 1.0):
                raise ValueError(  # noqa: TRY003
                    f"X was '{x}' but must be above 0.0 and below 1.0 (excl 0.0 and 1.0)",  # noqa: E501, EM102
                )
            if not (0.0 < y < 1.0):
                raise ValueError(  # noqa: TRY003
                    f"Y was '{y}' but must be above 0.0 and below 1.0 (excl 0.0 and 1.0)",  # noqa: E501, EM102
                )
            command_args[EffectTLVTag.COLOUR_XY] = (x, y)
        elif colour is not None:
            raise ValueError(  # noqa: TRY003
                f"Expected int or tuple for colour but got '{colour}'!",  # noqa: EM102
            )

        if effect is not None:
            command_args[EffectTLVTag.EFFECT_TYPE] = effect
        if effect_speed is not None:
            if not (0 <= effect_speed < 255):  # noqa: PLR2004
                raise ValueError(  # noqa: TRY003
                    f"Effect speed was '{effect_speed}' but must be above 0 and below 255 (inc 0 excl 255)",  # noqa: E501, EM102
                )
            command_args[EffectTLVTag.EFFECT_SPEED] = effect_speed

        if transition is not None:
            if not (0 <= transition < 65535):  # noqa: PLR2004
                raise ValueError(  # noqa: TRY003
                    f"Transition speed was '{transition}' but must be above 0 and below 65535 (inc 0 excl 65535)",  # noqa: E501, EM102
                )
            command_args[EffectTLVTag.TRANSITION] = transition

        _LOGGER.debug(f"Building packet with arguments: {command_args}")
        packet = TLV_EFFECT.build(command_args)  # type: ignore[arg-type]
        _LOGGER.debug(f"Built packet bytes: {packet.hex()}")
        await self._write_gatt(UUID_EFFECTS, packet)

    async def set_colour_effect(  # noqa: PLR0913, PLR0917
        self,
        x: float,
        y: float,
        brightness: int,
        effect: EffectType,
        effect_speed: int,
        transition_ms: int | None = None,
    ) -> None:
        """
        Set XY colour, brightness, effect and effect speed.

        .. note::
            This API may not be supported by all lights.

        :param x: X colour coordinate as float between 0.0 and 1.0.
        :param y: Y colour coordinate as float between 0.0 and 1.0.
        :param brightness: brightness as an integer between 0 and 255.
        :param effect: Effect (can be EffectType.NONE for plain colour).
        :param effect_speed: Speed of the effect between 0 and 255.
        :param transition_ms: Optional transition speed in milliseconds.
        :raises ValueError: If an invalid/out of range argument was provided.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """
        await self.set_effect(
            power=True,
            brightness=brightness,
            colour=(x, y),
            effect=effect,
            effect_speed=effect_speed,
            transition=(transition_ms // 100 if transition_ms else None),
        )

    async def set_temperature_effect(
        self,
        colour_temp: int,
        brightness: int,
        effect: EffectType,
        effect_speed: int,
        transition_ms: int | None = None,
    ) -> None:
        """
        Set colour temperature, brightness, effect and effect speed.

        .. note::
            This API may not be supported by all lights.

        :param colour_temp: colour temperature between 0 and 1000.
        :param brightness: brightness as an integer between 0 and 255.
        :param effect: Effect (can be EffectType.NONE for plain colour).
        :param effect_speed: speed of the effect between 0 and 255.
        :param transition_ms: Optional transition speed in milliseconds.
        :raises ValueError: If an invalid/out of range argument was provided.
        :raises :exc:`~HueBLE.WriteError`: If unable to write value to device.
        """

        await self.set_effect(
            power=True,
            brightness=brightness,
            colour=colour_temp,
            effect=effect,
            effect_speed=effect_speed,
            transition=(transition_ms // 100 if transition_ms else None),
        )

    @property
    def connected(self) -> bool:
        """
        Is connected to device.

        Returns true if the :exc:`~bleak.BleakClient` is connected to a device.

        .. warning::
            Being connected does not necessarily mean that we are able to send
            and receive commands. Instead use :attr:`~HueBleLight.authenticated`
            for authentication status and :attr:`~HueBleLight.available` for
            ability to send/receive commands.

        :returns: Is connected.
        """
        return self._client is not None and self._client.is_connected

    @property
    def authenticated(self) -> bool | None:
        """
        Is authenticated/paired to device.

        Returns true if the device is paired, false if not, and None if status is
        unknown.

        .. note::
            It is only possible to determine if the device is paired on Linux when
            the BlueZ backend is being used. None will be returned in all other cases.

        :returns bool: True if authenticated, false if not.
        :returns None: If authentication status is unknown.
        """

        # If the platform is not Linux then as far as I know there is
        # not an easy way to know if we are paired so we will try to
        # pair even if we are already paired. And if that pairing fails
        # we will not know until we try to read/write to/from the light
        # and get a permission error. Im probably missing something
        # so I should probably take another look in the future.
        if platform.system() != "Linux":
            _LOGGER.info(
                f"Unable to determine if paired to '{self.name}' due to the platform!",
            )
            return None

        # Get Linux specific properties of our connection
        properties = self._ble_device.details.get("props")

        # If the system does not have device properties then
        # it is unknown if we are authenticated to it
        if properties is None:
            _LOGGER.info(
                f"Pairing status of '{self.name}'' unknown due to missing metadata",
            )
            return None

        # If paired return True
        if properties.get("Paired") is True:
            return True

        # If not paired return False
        if properties.get("Paired") is False:
            return False

        # If unknown return None
        _LOGGER.info(
            f"Pairing status of '{self.name}' unknown due to missing metadata. "
            f"Properties: '{properties}'.",
        )
        return None

    @property
    def available(self) -> bool:
        """
        Is the light connected and authenticated.

        Returns true if we are connected and authenticated, i.e we
        are able to send/receive commands to/from the device.

        .. note::
            On non-Linux systems it is assumed we are authenticated!.

        :returns: Device availability for sending/receiving commands.
        """
        if self.connected:
            authenticated = self.authenticated

            # If we do not know the auth status assume it is ok
            if authenticated is None:
                return True

            # If we are authenticated then we may send/receive commands
            return authenticated
        return False

    @property
    def address(self) -> str:
        """MAC address of the device."""
        return self._ble_device.address

    @property
    def manufacturer(self) -> str | None:
        """
        Manufacturer of the device.

        Example: Signify Netherlands B.V.

        :returns str: If manufacturer known.
        :returns None: If manufacturer data not polled yet or not supported.
        """
        return self._manufacturer

    @property
    def model(self) -> str | None:
        """
        Model of the device.

        Example: LCA006

        :returns str: If model known.
        :returns None: If model data not polled yet or not supported.
        """
        return self._model

    @property
    def firmware(self) -> str | None:
        """
        Firmware version of the device.

        Example: 1.145.1

        :returns str: If firmware version known.
        :returns None: If firmware version data not polled yet or not supported.
        """
        return self._fw

    @property
    def zigbee_address(self) -> str | None:
        """
        Zigbee address of the device.

        Example: f4:2e:7f:0c:01:88:17:00

        :returns str: If Zigbee address known.
        :returns None: If Zigbee address data not polled yet or not supported.
        """
        return self._zigbee_address

    @property
    def name(self) -> str | None:
        """
        Name of the device.

        Example: Desk Right

        .. note::
            This is the name of the device that the operating system
            has provided. This may differ from :attr:`~HueBleLight.name_in_app`.

        :returns str: If device name known.
        :returns None: If operating system does not know name.
        """
        return self._ble_device.name

    @property
    def name_in_app(self) -> str | None:
        """
        Name of device.

        Example: Desk Right

        .. note::
            This is the name of the device from polling device metadata
            and may differ from :attr:`~HueBleLight.name` which is the
            operating system provided value.

        :returns str: If device name known.
        :returns None: If Device name data not polled yet.
        """
        return self._light_name

    @property
    def power_state(self) -> bool | None:
        """
        Power state of the device.

        The on/off status of the device (e.g true=on, false=off).

        :returns bool: True if on, False if off.
        :returns None: If state not polled/pushed yet or feature is not supported.
        """
        if self.supports_on_off:
            return self._power_on
        return None

    @property
    def brightness(self) -> int | None:
        """
        Brightness of the light.

        Brightness of the light as an integer (0=min, 254=max inclusive).

        :returns int: Brightness of light.
        :returns None: If state not polled/pushed yet or feature is not supported.
        """
        if self.supports_brightness:
            return self._brightness
        return None

    @property
    def colour_temp(self) -> int | None:
        """
        Colour temperature of the light.

        Colour temperature of the light in mireds.
        The minimum is 153 and maximum is 500 for most models.

        .. note::
            Colour temperature mode is inactive if XY colour
            is (0.0, 0.0) or (1.0, 1.0).

        :returns int: Colour temperature of light in mireds.
        :returns None: If state not polled/pushed yet, is inactive, or not supported.
        """
        if self.supports_colour_temp:
            return self._colour_temp
        return None

    @property
    def minimum_mireds(self) -> int | None:
        """
        Minimum supported colour temperature.

        Minimum supported colour temperature of the light
        in mireds.

        .. warning::
            This value is not polled from the light and is assumed. Future
            updates may take advantage of this interface.

        :returns int: Minimum colour temperature of light in mireds.
        :returns None: If state not polled/pushed yet or feature is not supported.
        """
        if self.supports_colour_temp:
            return self._minimum_mireds
        return None

    @property
    def maximum_mireds(self) -> int | None:
        """
        Maximum supported colour temperature.

        Maximum supported colour temperature of the light
        in mireds.

        .. warning::
            This value is not polled from the light and is assumed. Future
            updates may take advantage of this interface.

        :returns int: Maximum colour temperature of light in mireds.
        :returns None: If state not polled/pushed yet or feature is not supported.
        """
        if self.supports_colour_temp:
            return self._maximum_mireds
        return None

    @property
    def colour_xy(self) -> tuple[float, float] | None:
        """
        Colour of the light.

        Colour of the light in the XY colour space.
        The minimum is (0.0, 0.0) and maximum is (1.0, 1.0).

        .. note::
            Is (0.0, 0.0) or (1.0, 1.0) if XY colour mode is inactive.

        :returns tuple[float, float]: XY colour coordinates of light.
        :returns None: If state not polled/pushed yet, is inactive, or is not supported.
        """
        if self.supports_colour_xy:
            return self._colour_xy
        return None

    @property
    def colour_temp_mode(self) -> bool | None:
        """
        Is colour temperature mode active.

        :returns bool: True if colour temperature mode active, false if inactive.
        :returns None: If feature is not supported by device.
        """
        # If the light does not support colour temp
        # it can't be in colour temp mode
        if not self.supports_colour_temp:
            return None

        # If the light does support temperature but does not support
        # XY colour then it must be in colour temperature mode.
        if not self.supports_colour_xy:
            return True

        # Else the light supports colour temperature and XY colour
        # The light is in colour temperature mode when the XY colour
        # is (0.0, 0.0) or (1.0, 1.0)
        if self._colour_xy in ((0.0, 0.0), (1.0, 1.0)):
            return True

        # If we do not know what the XY colour is but do know what the colour temp is
        # then we must be in colour temp mode
        if self._colour_xy is None and self._colour_temp is not None:
            return True

        # If we do not know the colour temp but we do know the xy colour
        # then we must be in XY colour mode
        if self._colour_xy is not None and self._colour_temp is None:
            return False

        # Otherwise we do not know
        return None

    @property
    def effect(self) -> tuple[EffectType | None, int | None] | None:
        """
        Effect of light.

        The currently active effect as a tuple of the :class:`~HueBLE.EffectType` enum
        and effect speed (min=0, max=254 inc).

        .. note::
            Effects are inactive if this returns `None` but also if the effect type
            is :attr:`~HueBLE.EffectType.NONE`.

        :returns tuple[EffectType, int]: Tuple of effect type and speed.
        :returns None: If state not polled/pushed yet or feature is not supported.
        """
        if self.supports_effects:
            return (self._effect, self._effect_speed)
        return None

    @property
    def supports_on_off(self) -> bool | None:
        """
        Does the device support switching on/off.

        Yes I know it's silly but its for forwards compatibility
        in case a BLE sensor is ever released.

        :returns bool: Bool of support status if known.
        :returns None: If support status is unknown (not connected to device yet).
        """
        return self._supports_on_off

    @property
    def supports_brightness(self) -> bool | None:
        """
        Does the device support brightness adjustment.

        Devices such as the Hue smart plug do not support brightness.

        :returns bool: Bool of support status if known.
        :returns None: If support status is unknown (not connected to device yet).
        """
        return self._supports_brightness

    @property
    def supports_colour_temp(self) -> bool | None:
        """
        Does the device support colour temperature adjustment.

        Devices such as the white only lights do not support colour
        temperature adjustments.

        :returns bool: Bool of support status if known.
        :returns None: If support status is unknown (not connected to device yet).
        """
        return self._supports_colour_temp

    @property
    def supports_colour_xy(self) -> bool | None:
        """
        Does the device support XY colour adjustment.

        Devices such as the colour temperature only lights do not support
        XY colour adjustments.

        :returns bool: Bool of support status if known.
        :returns None: If support status is unknown (not connected to device yet).
        """
        return self._supports_colour_xy

    @property
    def supports_effects(self) -> bool | None:
        """
        Does the device support the effects API.

        Its likely (though untested) that older devices such as the Go 2.0 light
        do not support the effects API.

        :returns bool: Bool of support status if known.
        :returns None: If support status is unknown (not connected to device yet).
        """
        return self._supports_effects

    def __repr__(self) -> str:
        """Representation of of the devices state for logging."""
        return (
            f"{type(self).__name__}("
            # Internals
            f"ble_device={self._ble_device!r}, "
            f"client={self._client!r}, "
            f"state_changed_callbacks={len(self._state_changed_callbacks)}, "
            f"expect_disconnect={self._expect_disconnect!r}, "
            f"connection_attempts={self._connection_attempts!r}, "
            f"connection_lock_locked={self._connection_lock.locked()!r}, "
            f"state_update_lock_locked={self._state_update_lock.locked()!r}, "
            # Light state
            f"manufacturer={self._manufacturer!r}, "
            f"model={self._model!r}, "
            f"fw={self._fw!r}, "
            f"zigbee_address={self._zigbee_address!r}, "
            f"light_name={self._light_name!r}, "
            f"power_on={self._power_on!r}, "
            f"brightness={self._brightness!r}, "
            f"colour_temp={self._colour_temp!r}, "
            f"minimum_mireds={self._minimum_mireds!r}, "
            f"maximum_mireds={self._maximum_mireds!r}, "
            f"colour_xy={self._colour_xy!r}, "
            f"effect={self._effect!r}, "
            f"effect_speed={self._effect_speed!r}, "
            # Light feature support
            f"supports_metadata_manufacturer={self._supports_metadata_manufacturer!r}, "
            f"supports_metadata_model={self._supports_metadata_model!r}, "
            f"supports_metadata_firmware={self._supports_metadata_firmware!r}, "
            f"supports_metadata_zigbee_address={self._supports_metadata_zigbee_address!r}, "  # noqa: E501
            f"supports_metadata_name_in_app={self._supports_metadata_name_in_app!r}, "
            f"supports_on_off={self._supports_on_off!r}, "
            f"supports_brightness={self._supports_brightness!r}, "
            f"supports_colour_temp={self._supports_colour_temp!r}, "
            f"supports_colour_xy={self._supports_colour_xy!r}, "
            f"supports_effects={self._supports_effects!r}"
            f")"
        )
