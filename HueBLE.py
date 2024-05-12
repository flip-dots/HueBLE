"""HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
import platform
from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends.client import BaseBleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from struct import pack, unpack
from typing import Callable


#: String containing manufacturer. Handle 15.
UUID_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"

#: String containing model number. Handle 17
UUID_MODEL = "00002a24-0000-1000-8000-00805f9b34fb"

#: String containing firmware version. Handle 19.
UUID_FW_VERSION = "00002a28-0000-1000-8000-00805f9b34fb"

#: String containing Zigbee address. Handle 22.
UUID_ZIGBEE_ADDRESS = "97fe6561-0001-4f62-86e9-b71ee2da3d22"

#: String containing light name. Handle 24
UUID_NAME = "97fe6561-0003-4f62-86e9-b71ee2da3d22"

#: Power state of light. Is subscribable. x00 and x01. Handle 49.
UUID_POWER = "932c32bd-0002-47a2-835a-a8d455b859dd"

#: Brightness of light. Int 0-255. Handle 52.
UUID_BRIGHTNESS = "932c32bd-0003-47a2-835a-a8d455b859dd"

#: Temperature of light. Int 153-500. 0xFFFF when colour enabled. Handle 55.
UUID_TEMPERATURE = "932c32bd-0004-47a2-835a-a8d455b859dd"

#: XY colour of light. Two 16-bit ints. 0xFFFFFFFF when CW/WW. Handle 58.
UUID_XY_COLOUR = "932c32bd-0005-47a2-835a-a8d455b859dd"

#: This is a UUID that as far as I know only hue lights use and it shows up
#: under BLE Device details and as such does not require connecting to check
#: for. The UUID also has the following service data. I am not sure what it
#: means but it is the same for both of my colour lights with model no LCA006.
#: \x02\x10\x0e\xbe\x02
UUID_HUE_IDENTIFIER = "0000fe0f-0000-1000-8000-00805f9b34fb"

#: The assumed minimum colour temperature of the light in mireds.
#: Constant as it us unknown if/where the light exposes this data.
MIN_MIREDS = 153

#: The assumed maximum colour temperature of the light in mireds.
#: Constant as it us unknown if/where the light exposes this data.
MAX_MIREDS = 500

#: Default string of light metadata light address, model, and firmware.
DEFAULT_METADATA_STRING = "Unknown"

#: Default max connection attempts in the connect function.
DEFAULT_CONNECTION_ATTEMPTS_MAX = 3

#: Default max time for all connection attempts in connect function.
DEFAULT_CONNECTION_TIMEOUT = 30

#: Default max time before a call to connect times out waiting for
#: another call to connect to finish its attempt.
DEFAULT_CONNECTION_WAIT_TIMEOUT = 120

#: Default time to wait after pairing to check if it was successful.
DEFAULT_PAIR_DELAY = 1

#: Default max time before a call to poll state times out.
DEFAULT_POLL_STATE_TIMEOUT = 30

#: Default max time before a single read attempt to the light times out and it
#: will try again. This must be large enough to allow for a connection attempt
#: if the light is not already connected.
DEFAULT_READ_GATT_TIMEOUT = 15

#: Default max light read attempts before raising an exception.
DEFAULT_READ_GATT_MAX_ATTEMPTS = 3

#: Default max time before a single write attempt to the light times out and it
#: will try again. This must be large enough to allow for a connection attempt
#: if the light is not already connected.
DEFAULT_WRITE_GATT_TIMEOUT = 15

#: Default max light write attempts before raising an exception.
DEFAULT_WRITE_GATT_MAX_ATTEMPTS = 3

#: Default of all polls to the light updating the light objects internal state.
DEFAULT_POLL_WRITES_STATE = True

#: Default amount of time to scan for a light for in the discovery method.
DEFAULT_DISCOVER_TIME = 5

#: Default time to wait in the reconnect method between connecting and disconnecting.
DEFAULT_RECONNECT_DELAY = 3

#: Maximum amount of automatic reconnection attempts the program will make.
DEFAULT_MAX_RECONNECT_ATTEMPTS = -1


_LOGGER = logging.getLogger(__name__)


class HueBleLight(object):
    """Philips Hue BLE Light object."""

    def __init__(self, ble_device: BLEDevice):
        """Initialise light object. Does not connect automatically."""

        _LOGGER.debug(
            f"""Initializing Hue light "{ble_device.name}" with"""
            f""" address "{ble_device.address}" and details"""
            f""" "{ble_device.details}"."""
        )

        self._ble_device = ble_device
        self._client: BleakClient = None
        self._manufacturer = DEFAULT_METADATA_STRING
        self._model = DEFAULT_METADATA_STRING
        self._fw = DEFAULT_METADATA_STRING
        self._zigbee_address = DEFAULT_METADATA_STRING
        self._light_name = DEFAULT_METADATA_STRING
        self._power_on = False
        self._brightness = None
        self._colour_temp = None
        self._minimum_mireds = MIN_MIREDS
        self._maximum_mireds = MAX_MIREDS
        self._colour_xy = None

        self._state_changed_callbacks: list[Callable[[], None]] = []
        self._expect_disconnect = True
        self._connection_attempts = 0
        self._connection_lock: asyncio.Lock = asyncio.Lock()
        self._state_update_lock: asyncio.Lock = asyncio.Lock()

    def add_callback_on_state_changed(self, function: Callable[[], None]) -> None:
        """Register a callback to be run on light state changes. Triggers
        include changes to power, brightness, temp, colour, and connection
        status. These triggers are not dependant on the request being made
        by this program. (e.g If a ZigBee switch or Hue app commands the
        light off the callback will still be run)
        """
        self._state_changed_callbacks.append(function)

    def remove_callback(self, function: Callable[[], None]) -> None:
        """Remove a registered state change callback.
        Raises ValueError if does not exist.
        """
        self._state_changed_callbacks.remove(function)

    def _run_state_changed_callbacks(self) -> None:
        """Executes all registered callbacks for a state change."""
        for function in self._state_changed_callbacks:
            function()

    def _disconnect_callback(self, client: BaseBleakClient) -> None:
        """Private method. Updates program state and will attempt reconnect
        if the disconnect was unexpected.
        """
        # Warn about weird edge case. This doesn't seem to cause any issues
        # anymore but it's still weird that this happens so im leaving it here
        # to help future me in case it bugs out again.
        if client != self._client:
            _LOGGER.warn(
                f"""The disconnect came from an unexpected client. The class"""
                f""" client is "{self._client}", but the callback"""
                f""" gave us "{client}". Will run disconnect anyway."""
            )

        # If we expected the disconnect then we don't try to reconnect.
        if self._expect_disconnect:
            _LOGGER.info(f"""Received expected disconnect from "{client}".""")
            return

        _LOGGER.warn(
            f"""Unexpected disconnect from "{client}"."""
        )

        # Run callbacks if we did not expect the disconnect
        self._run_state_changed_callbacks()

        if (DEFAULT_MAX_RECONNECT_ATTEMPTS == -1
            or self._connection_attempts < DEFAULT_MAX_RECONNECT_ATTEMPTS):

            # Try and reconnect
            asyncio.create_task(self.reconnect)

        else:
            _LOGGER.warn(
                f"""Maximum re-connect attempts to "{client}". exceeded."""
                """ Will NOT attempt reconnect."""
            )


    async def reconnect(self, reconnect_delay: int = DEFAULT_RECONNECT_DELAY):
        """Disconnects then reconnects to the device.
        Simply calls disconnect then calls connect.
        """

        _LOGGER.debug(f"""Disconnecting then reconnecting to "{self.address}".""")

        # There *should* be no harm in calling disconnect even if we are
        # already disconnected. We could call self.connected but
        # it might be possible for that to return inaccurate values
        # if the OS starts being silly. Might make sense to do that in the
        # future though, so heads up future me or other equally cool person.
        await self.disconnect()
        await asyncio.sleep(reconnect_delay)
        await self.connect()

    async def _subscribe_to_light(self) -> bool:
        """Subscribes to the state of the light.
        Automatically called on connect.
        Returns true if succeeded.
        """

        try:

            # If turning off an on is supported :|
            if self.supports_on_off:

                def report(cHandle: int, data: bytearray) -> None:
                    self._power_on = bool(data[0])
                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" power state of ({self.power_state})"""
                    )
                    self._run_state_changed_callbacks()

                _LOGGER.debug("Subscribing to power state UUID")
                await self._client.start_notify(UUID_POWER, report)

            # If brightness is supported
            if self.supports_brightness:

                def report(cHandle: int, data: bytearray) -> None:
                    self._brightness = data[0]
                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" brightness state of ({self.brightness})"""
                    )
                    self._run_state_changed_callbacks()

                _LOGGER.debug("Subscribing to brightness UUID")
                await self._client.start_notify(UUID_BRIGHTNESS, report)

            # If colour temperature is supported
            if self.supports_colour_temp:

                def report(cHandle: int, data: bytearray) -> None:
                    self._colour_temp = int.from_bytes(data, "little")
                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" colour temp state of ({self.colour_temp})"""
                    )
                    self._run_state_changed_callbacks()

                _LOGGER.debug("Subscribing to colour temperature UUID")
                await self._client.start_notify(UUID_TEMPERATURE, report)

            # If XY colour is supported
            if self.supports_colour_xy:

                def report(cHandle: int, data: bytearray) -> None:
                    x, y = unpack("<HH", data)
                    self._colour_xy = (x / 0xFFFF, y / 0xFFFF)
                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" XY colour state of ({self.colour_xy})"""
                    )
                    self._run_state_changed_callbacks()

                _LOGGER.debug("Subscribing to XY colour UUID")
                await self._client.start_notify(UUID_XY_COLOUR, report)

            return True

        except Exception as e:
            _LOGGER.error(
                f"""Failed to subscribe to services of light "{self.name}"."""
                f""" Error: "{e}"."""
            )
            return False

    async def connect(
        self,
        max_attempts: int = DEFAULT_CONNECTION_ATTEMPTS_MAX,
        connection_timeout: int = DEFAULT_CONNECTION_TIMEOUT,
        wait_timeout: int = DEFAULT_CONNECTION_WAIT_TIMEOUT,
    ) -> bool:
        """Connects to the light using bluetooth. This can be manually called
        but it will also be run automatically if the light is not
        connected when the light is polled or set.

        On connection it will attempt to pair to the light if not already
        paired but this only seems to work on Linux, so you might need to
        pair using your OS.

        Connecting will NOT automatically cause all values to be polled
        and put in the internal state.

        Connection timeout is the maximum time for a connection attempt
        once a lock has been acquired.

        Wait timeout is the maximum amount of time that the method will
        wait to acquire a lock to attempt to perform a connection.
        """

        # If we are already connected then do nothing
        if self.connected:
            _LOGGER.debug(f"""Already connected to "{self.name}" Nothing to do here.""")
            return True

        # Print warning that the connection is already in progress by
        # another method.
        if self._connection_lock.locked():
            _LOGGER.debug(
                f"""Connection already in progress to "{self.name}"."""
                f""" Waiting for it to complete..."""
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
                            f""" for lock release"""
                        )
                        return True

                    _LOGGER.debug(
                        f"""Connecting to "{self.name}" with address"""
                        f""" "{self.address}"."""
                    )

                    # Increment attempts
                    self._connection_attempts += 1

                    # Maximum time to make a connection
                    try:
                        async with asyncio.timeout(connection_timeout):

                            # Make a fresh bleak client and connect
                            self._client = await establish_connection(
                                BleakClient,
                                device=self._ble_device,
                                name=self.address,
                                max_attempts=max_attempts,
                                disconnected_callback=self._disconnect_callback,
                            )

                            _LOGGER.debug(
                                f"""Using client "{self._client}" with """
                                f"""backend "{self._client._backend}"."""
                            )

                            # If we failed to connect
                            if not self._client.is_connected:
                                _LOGGER.error(
                                    f"""Failed to connect to "{self.name}"."""
                                )
                                if _LOGGER.isEnabledFor(_LOGGER.debug):
                                    await self.print_services()
                                return False

                            # Check if the light is paired and trusted
                            # If we are not using a Linux system then we don't
                            # know if we are paired with the device.
                            # We assume we are not paired and attempt to pair.
                            authenticated = self.authenticated

                            # If we dont know if we are paired and trusted then
                            # pair and assume it worked (non Linux systems)
                            if authenticated is None:

                                # Pair. If not successful return false
                                if not await self.pair():
                                    _LOGGER.error(
                                        f"""Failed paring to "{self.name}"."""
                                    )
                                    return False

                            # If we are not paired then pair
                            elif not authenticated:

                                # Pair. If not successful return false
                                if not await self.pair():
                                    _LOGGER.error(
                                        f"""Failed paring to "{self.name}"."""
                                    )
                                    return False

                            # If we have reached here that means connecting and
                            # pairing was (probably) successful
                            _LOGGER.debug(
                                f"""Successfully connected and authenticated"""
                                f""" to "{self.name}"."""
                            )

                            # If we cant find out what the light supports
                            # then we have failed
                            if not await self._determine_services():
                                return False

                          
                            # If we failed to subscribe to the lights state updates
                            if not await self._subscribe_to_light():

                                _LOGGER.debug(
                                    f""" Failed to subscribe to services"""
                                    f""" offered by light "{self.name}"."""
                                )

                                return False
                               
                            # If the connection was successful, and we are paired, 
                            # authenticated, and subscribed, then we no longer
                            # expect to be disconnected
                            self._expect_disconnect = False

                            # We also reset the attempts counter since we succeeded
                            self._connection_attempts = 0
                           
                            return True

                    except asyncio.TimeoutError as e:
                        _LOGGER.error(
                            f"""Timed out attempting to connect to"""
                            f""" "{self.name}". Error "{e}"."""
                        )

        except asyncio.TimeoutError as e:
            _LOGGER.error(
                f"""Timed out waiting for connection lock for"""
                f""" "{self.name}". Error "{e}"."""
            )
        except Exception as e:
            _LOGGER.error(
                f"""Exception connecting to light"""
                f""" "{self.name}". Error "{e}"."""
            )

        return False

    async def pair(self) -> bool:
        """Attempts to pair to the light and returns the result.
        Return value defaults to true on non-Linux systems.
        """

        _LOGGER.debug(f"""Attempting to pair to "{self.name}".""")

        # If we are not connected then we cannot send a pair request
        if not self.connected:
            _LOGGER.error(f"""Not connected to "{self.name}", therefore cannot pair.""")
            return False

        try:
            # Request pair using bleak
            await self._client.pair()
            # Wait a little
            await asyncio.sleep(DEFAULT_PAIR_DELAY)

            # If we are still connected
            if self.connected:

                authenticated = self.authenticated
                # If we do not know the result of pairing due to
                # to the platform then assume all is well
                if authenticated is None:
                    return True
                else:
                    return authenticated

        except asyncio.TimeoutError:
            _LOGGER.error(f"""Timed out attempting to pair to "{self.name}".""")
        except BleakError as err:
            _LOGGER.error(
                f"""Unexpected error attempting to pair to "{self.name}"."""
                f""" Error message "{err}" """
            )
        return False

    async def _determine_services(self) -> bool:
        """Determines what features the light supports.
        The data may then be retrieved via the supports properties.
        Returns True if successful and False on error.
        """

        try:
            services = self._client.services
            for id, service in services.services.items():

                _LOGGER.debug(
                    f"Service: {service}, " f"description: {service.description}"
                )

                if service.characteristics is None:
                    continue

                for char in service.characteristics:
                    _LOGGER.debug(
                        f"Characteristic: {char}, "
                        f"description: {char.description}, "
                        f"descriptors: {char.descriptors}"
                    )

            if services.get_characteristic(UUID_POWER) is not None:
                self._power_on = False
            else:
                _LOGGER.error(
                    f"""Light "{self.name}" does not appear to """
                    f"""support turning on and off."""
                )
                self._power_on = None

            if services.get_characteristic(UUID_BRIGHTNESS) is not None:
                self._brightness = 0
            else:
                _LOGGER.debug(
                    f"""Light "{self.name}" does not appear to """
                    f"""support changing the brightness."""
                )
                self._brightness = None

            if services.get_characteristic(UUID_TEMPERATURE) is not None:
                self._colour_temp = 0
            else:
                _LOGGER.debug(
                    f"""Light "{self.name}" does not appear to """
                    f"""support changing the colour temp."""
                )
                self._colour_temp = None

            if services.get_characteristic(UUID_XY_COLOUR) is not None:
                self._colour_xy = (0.0, 0.0)
            else:
                _LOGGER.debug(
                    f"""Light "{self.name}" does not appear to """
                    f"""support changing the XY colour."""
                )
                self._colour_xy = None

            return True

        except BleakError:
            _LOGGER.error(
                f"""Unable to determine what features light"""
                f""" "{self.name}" supports."""
            )
            return False

    async def disconnect(self) -> None:
        """Disconnects the program from the light.
        Callbacks are not triggered.
        """

        self._expect_disconnect = True
        # If the client does not exist return
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        except asyncio.TimeoutError:
            _LOGGER.error(f"""Timeout attempting to disconnect from "{self.name}".""")
        except BleakError as err:
            _LOGGER.error(
                f"""Error attempting to disconnect from "{self.name}"."""
                f""" Error message "{err}"."""
            )

        # Throw away the client
        self._client = None

    async def poll_state(
        self, timeout=DEFAULT_POLL_STATE_TIMEOUT, run_callbacks=True
    ) -> tuple[bool, list[Exception]]:
        """Updates the local state with values from the light using polling.
        A lock is used to only allow one state update at a time with
        a timeout. Any callbacks are run outside of the state lock but
        within the timeout lock. asyncio.TimeoutError raised on timeout.
        Returns true/false if the state changed and a list of exceptions.
        """

        state_changed = False
        exceptions = []

        if self._state_update_lock.locked():

            _LOGGER.debug(
                f"""Waiting for state update lock of "{self.name}" to be"""
                f""" released."""
            )
        
        try:

            # Timeout if waiting too long
            async with asyncio.timeout(timeout):

                # Only one device may poll at a time
                async with self._state_update_lock:

                    _LOGGER.debug(
                        f"""Processing state update request for""" f""" "{self.name}"."""
                    )

                    # Exceptions are added to the log and a list of them is
                    # returned by the method but they are otherwise ignored.
                    try:
                        prev = self.manufacturer
                        if prev != await self.poll_manufacturer(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.model
                        if prev != await self.poll_model(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.firmware
                        if prev != await self.poll_firmware(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.zigbee_address
                        if prev != await self.poll_zigbee_address(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self._light_name
                        if prev != await self.poll_light_name(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.power_state
                        if prev != await self.poll_power_state(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.brightness
                        if prev != await self.poll_brightness(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.colour_temp
                        if prev != await self.poll_colour_temp(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)
                    try:
                        prev = self.colour_xy
                        if prev != await self.poll_colour_xy(write_state=True):
                            state_changed = True
                    except Exception as e:
                        exceptions.append(e)

                    # Print it all out for debugging
                    _LOGGER.debug(
                        f"""Data from light "{self.name}"\n"""
                        f"""MAC address "{self.address}"\n"""
                        f"""Name in Hue app: "{self.name_in_app}"\n"""
                        f"""Manufacturer: "{self.manufacturer}"\n"""
                        f"""Model: "{self.model}"\n"""
                        f"""Firmware: "{self.firmware}"\n"""
                        f"""ZigBee Address: "{self.zigbee_address}"\n"""
                        f"""Power state: "{self.power_state}"\n"""
                        f"""Brightness: "{self.brightness}"\n"""
                        f"""Colour temp: "{self.colour_temp}"\n"""
                        f"""Colour XY: "{self.colour_xy}"."""
                    )

                # Callbacks are run outside of the state update lock
                if run_callbacks and state_changed:
                    self._run_state_changed_callbacks()

        except asyncio.TimeoutError as e:
            exceptions.append(e)
            _LOGGER.error(
                f"""Timed out waiting for poll_state lock for"""
                f""" "{self.name}". Error "{e}"."""
            )
        except Exception as e:
            exceptions.append(e)
            _LOGGER.error(
                f"""Exception polling state of light"""
                f""" "{self.name}". Error "{e}"."""
            )

        return state_changed, exceptions

    async def _read_gatt(
        self,
        property: str,
        attempt_timeout: int = DEFAULT_READ_GATT_TIMEOUT,
        max_attempts: int = DEFAULT_READ_GATT_MAX_ATTEMPTS,
    ) -> bytearray:
        """Reads a GATT attribute from the light.
        If there is an error an exception will be thrown.
        """
        for i in range(1, max_attempts + 1):
            try:
                async with asyncio.timeout(attempt_timeout):
                    if not self.connected:
                        if not await self.connect():
                            raise Exception("Cannot connect!")
                    return await self._client.read_gatt_char(property)

            except Exception as e:
                _LOGGER.debug(
                    f"""Failed to read value from "{self.name}" on attempt"""
                    f""" {i}/{max_attempts}. Error message "{e}"."""
                )
        raise Exception(
            f"""Unable to read from "{self.name}" after"""
            f""" {max_attempts} attempts"""
        )

    async def _write_gatt(
        self,
        property: str,
        data: bytes,
        attempt_timeout: int = DEFAULT_WRITE_GATT_TIMEOUT,
        max_attempts: int = DEFAULT_WRITE_GATT_MAX_ATTEMPTS,
    ) -> bytearray:
        """Writes a GATT attribute to a light.
        Will attempt to connect if not already connected.
        Will throw an exception on error.
        """
        for i in range(1, max_attempts + 1):
            try:
                async with asyncio.timeout(attempt_timeout):
                    if not self.connected:
                        if not await self.connect():
                            raise Exception("Cannot connect!")
                    return await self._client.write_gatt_char(
                        property, data, response=True
                    )

            except Exception as e:
                _LOGGER.debug(
                    f"""Failed to write value to "{self.name}" on attempt"""
                    f""" {i}/{max_attempts}. Error message "{e}"."""
                )
        raise Exception(
            f"""Unable to write to "{self.name}" after"""
            f""" {max_attempts} attempts"""
        )

    async def poll_manufacturer(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> str:
        """Returns the manufacturer of the light."""
        encoded = await self._read_gatt(UUID_MANUFACTURER)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._manufacturer = decoded
        return decoded

    async def poll_model(self, write_state: bool = DEFAULT_POLL_WRITES_STATE) -> str:
        """Returns the model of the light."""
        encoded = await self._read_gatt(UUID_MODEL)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._model = decoded
        return decoded

    async def poll_firmware(self, write_state: bool = DEFAULT_POLL_WRITES_STATE) -> str:
        """Returns the firmware version of the light."""
        encoded = await self._read_gatt(UUID_FW_VERSION)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._fw = decoded
        return decoded

    async def poll_zigbee_address(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> str:
        """Returns the Zigbee address of the light."""
        encoded = await self._read_gatt(UUID_ZIGBEE_ADDRESS)
        decoded = encoded.hex(sep=":")
        if write_state:
            self._zigbee_address = decoded
        return decoded

    async def poll_light_name(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> str:
        """Returns the name of the light as shown in the Hue app.
        This may differ from the light objects name property.
        """
        encoded = await self._read_gatt(UUID_NAME)
        decoded = encoded.decode("ascii", "ignore")
        if write_state:
            self._light_name = decoded
        return decoded

    async def poll_power_state(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> bool:
        """Gets the current power state of the light."""
        encoded = await self._read_gatt(UUID_POWER)
        decoded = bool(encoded[0])
        if write_state:
            self._power_on = decoded
        return decoded

    async def poll_brightness(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> int:
        """Gets the current brightness as an integer between 0 and 255."""
        encoded = await self._read_gatt(UUID_BRIGHTNESS)
        decoded = encoded[0]
        if write_state:
            self._brightness = decoded
        return decoded

    async def poll_colour_temp(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> int:
        """Gets the current colour temperature as an integer
        between 153 and 500. Uses mireds.
        """
        encoded = await self._read_gatt(UUID_TEMPERATURE)
        decoded = int.from_bytes(encoded, "little")
        if write_state:
            self._colour_temp = decoded
        return decoded

    async def poll_colour_xy(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> tuple[float, float]:
        """Gets the XY colour coordinates as floats between 0.0 and 1.0."""
        buf = await self._read_gatt(UUID_XY_COLOUR)
        x, y = unpack("<HH", buf)
        x_after = x / 0xFFFF
        y_after = y / 0xFFFF
        if write_state:
            self._colour_xy = (x_after, y_after)
        return x_after, y_after

    async def set_light_name(self, name: str):
        """Sets the name of the light. Not tested, use at own risk."""
        await self._write_gatt(UUID_NAME, str.encode(name))

    async def set_power(self, on: bool):
        """Sets the power state of the light."""
        await self._write_gatt(UUID_POWER, bytes([1 if on else 0]))

    async def set_brightness(self, brightness: int):
        """Sets the brightness from an integer between 0 and 255"""
        await self._write_gatt(UUID_BRIGHTNESS, bytes([max(min(brightness, 254), 1)]))

    async def set_colour_temp(self, colour_temp: int):
        """Sets the temperature from an int between 153 and 500.
        Uses mireds."""
        temp = max(min(int(colour_temp), 500), 153)
        y = temp.to_bytes(2, "little")
        await self._write_gatt(UUID_TEMPERATURE, y)

    async def set_colour_xy(self, x: float, y: float):
        """Sets the XY colour coordinates from floats between 0.0 and 1.0."""
        buf = pack("<HH", int(x * 0xFFFF), int(y * 0xFFFF))
        await self._write_gatt(UUID_XY_COLOUR, buf)

    @property
    def connected(self) -> bool:
        """Returns true if the client is connected to a light.
        This does not however mean that we are able to send
        and receive commands. Use the "available" property for that.
        """
        return self._client and self._client.is_connected

    @property
    def authenticated(self) -> bool | None:
        """Returns true if the light is paired and trusted.
        This only works on Linux. On other platforms this
        returns None.
        """

        # If the platform is not Linux then as far as I know there is
        # not an easy way to know if we are paired so we will try to
        # pair even if we are already paired. And if that pairing fails
        # we will not know until we try to read/write to/from the light
        # and get a permission error. Im probably missing something
        # so I should probably take another look in the future.
        if platform.system() != "Linux":
            return None

        # Get Linux specific properties of our connection
        properties = self._ble_device.details.get("props")

        # If we are paired and trusted by the light we are good
        if properties.get("Paired") is True:
            if properties.get("Trusted") is True:
                return True

            else:
                _LOGGER.error(
                    f"""Not paired to "{self.name}". Device""" f""" not trusted."""
                )

        else:
            _LOGGER.error(
                f"""Not paired to "{self.name}".""" f""" Device was not paired."""
            )

        return False

    @property
    def available(self) -> bool:
        """Is the light connected and authenticated.
        Meaning are we able to send/receive commands to/from the light.
        On non-Linux systems it is assumed we are authenticated!.
        """
        if self.connected:
            authenticated = self.authenticated

            # If we do not know the auth status assume it is ok
            if authenticated is None:
                return True
            else:
                # If we are authenticated then we may send/receive commands
                return authenticated
        return False

    @property
    def address(self) -> str:
        """MAC address of the light."""
        return self._ble_device.address

    @property
    def manufacturer(self) -> str:
        """Manufacturer of the light."""
        return self._manufacturer

    @property
    def model(self) -> str:
        """Model of the light."""
        return self._model

    @property
    def firmware(self) -> str:
        """Firmware of the light."""
        return self._fw

    @property
    def zigbee_address(self) -> str:
        """Zigbee address of the light."""
        return self._zigbee_address

    @property
    def name(self) -> str:
        """Bluetooth name of the light.
        Should not but may differ from value from poll_light_name().
        """
        return self._ble_device.name

    @property
    def name_in_app(self) -> str:
        """Name of light in Hue app.
        Should not but may differ from the name (bluetooth) property.
        """
        return self._light_name

    @property
    def power_state(self) -> bool | None:
        """Is the light running?, you better go catch it."""
        return self._power_on

    @property
    def brightness(self) -> int | None:
        """Brightness of the light. Int 0-255.
        Returns None if the feature is not supported by the light.
        """
        if self.supports_brightness:
            return self._brightness
        else:
            return None

    @property
    def colour_temp(self) -> int | None:
        """Colour temperature of the light in mireds. Int 153-500.
        Returns None if the feature is not supported by the light.
        """
        if self.supports_colour_temp:
            return self._colour_temp
        else:
            return None

    @property
    def minimum_mireds(self) -> int | None:
        """Minimum mireds colour temperature supported.
        Returns None if the feature is not supported by the light.
        This value is assumed and not actually polled from the light.
        """
        if self.supports_colour_temp:
            return self._minimum_mireds
        else:
            return None

    @property
    def maximum_mireds(self) -> int | None:
        """Maximum mireds colour temperature supported.
        Returns None if the feature is not supported by the light.
        This value is assumed and not actually polled from the light.
        """
        if self.supports_colour_temp:
            return self._maximum_mireds
        else:
            return None

    @property
    def colour_xy(self) -> tuple[int, int] | None:
        """Colour in XY coordinates. (0.0, 0.0) - (1.0, 1.0).
        Returns None if the feature is not supported by the light.
        """
        if self.supports_colour_xy:
            return self._colour_xy
        else:
            return None

    @property
    def colour_temp_mode(self) -> bool | None:
        """True if the light is in colour temperature mode, else false.
        Returns None if the feature is not supported by the light.
        """
        # If the light does not support colour temp
        # it can't be in colour temp mode
        if not self.supports_colour_temp:
            return False

        # If the light does support temperature but does not support
        # XY colour then it must be in colour temperature mode.
        elif not self.supports_colour_xy:
            return True

        # Else the light supports colour temperature and XY colour
        # The light is in colour temperature mode when the XY colour
        # is (0.0, 0.0) or (1.0, 1.0)
        else:
            return self._colour_xy == (0.0, 0.0) or self._colour_xy == (1.0, 1.0)

    @property
    def supports_on_off(self) -> bool:
        """Does the light support turning on and off.
        Yes I know it's silly but its for forwards compatibility
        in case a bluetooth sensor is ever released.
        """
        return self._power_on is not None

    @property
    def supports_brightness(self) -> bool:
        """Does the light support brightness control."""
        return self._brightness is not None

    @property
    def supports_colour_temp(self) -> bool:
        """Does the light support colour temperature control."""
        return self._colour_temp is not None

    @property
    def supports_colour_xy(self) -> bool:
        """Does the light support XY (RGB) colour control."""
        return self._colour_xy is not None


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
