"""HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import base64
import binascii
import hashlib
import hmac
import logging
import os
import platform
import re
import uuid
from bleak import BleakClient, BleakError, BleakScanner
from bleak.backends import BleakBackend
from bleak.backends.client import BaseBleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from struct import pack, unpack
from typing import Callable
from enum import Enum
from dataclasses import dataclass

try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
except ImportError:
    X25519PrivateKey = None
    X25519PublicKey = None
    AESCCM = None

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
UUID_LIGHT_CONTROL_INFO = "932c32bd-0001-47a2-835a-a8d455b859dd"

UUID_POWER = "932c32bd-0002-47a2-835a-a8d455b859dd"

#: Brightness of light. Int 0-255. Handle 52.
UUID_BRIGHTNESS = "932c32bd-0003-47a2-835a-a8d455b859dd"

#: Temperature of light. Int 153-500. 0xFFFF when colour enabled. Handle 55.
UUID_TEMPERATURE = "932c32bd-0004-47a2-835a-a8d455b859dd"

#: XY colour of light. Two 16-bit ints. 0xFFFFFFFF when CW/WW. Handle 58.
UUID_XY_COLOUR = "932c32bd-0005-47a2-835a-a8d455b859dd"

#: new colour change and effect enpoint
UUID_EFFECTS = "932c32bd-0007-47a2-835a-a8d455b859dd"

UUID_ZD_AUTHENTICATE = "29144af4-0002-4481-bfe9-6d0299b429e3"
UUID_DLC_KEY = "97fe6561-2005-4f62-86e9-b71ee2da3d22"
DLC_ALS_METHOD_TLV = bytes.fromhex("64 04 0b 10 00 02 f4")


#: This is a UUID that as far as I know only hue lights use and it shows up
#: under BLE Device details and as such does not require connecting to check
#: for. The UUID also has the following service data. I am not sure what it
#: means but it is the same for both of my colour lights with model no LCA006.
#: \x02\x10\x0e\xbe\x02
UUID_HUE_IDENTIFIER = "0000fe0f-0000-1000-8000-00805f9b34fb"

#: Fallback minimum colour temperature when the light does not expose a range.
MIN_MIREDS = 153

#: Fallback maximum colour temperature when the light does not expose a range.
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

#: Default of if making a successful connection to the light triggers
#: callbacks to be run.
DEFAULT_ON_CONNECT_RUN_CALLBACKS = True

#: Default time to wait for a pairing request to complete.
DEFAULT_PAIR_TIMEOUT = 15

#: Default max time before a call to poll state times out.
DEFAULT_POLL_STATE_TIMEOUT = 45

#: Default of if callbacks should be executed on a call to poll_state
#: where the state changed.
DEFAULT_POLL_STATE_CALLBACKS_IF_CHANGED = True

#: Default max time before a single read attempt to the light times out and it
#: will try again. This must be large enough to allow for a connection attempt
#: if the light is not already connected.
DEFAULT_READ_GATT_TIMEOUT = 20

#: Default max light read attempts before raising an exception.
DEFAULT_READ_GATT_MAX_ATTEMPTS = 3

#: Default max time before a single write attempt to the light times out and it
#: will try again. This must be large enough to allow for a connection attempt
#: if the light is not already connected.
DEFAULT_WRITE_GATT_TIMEOUT = 20

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

#: data stream unpack format string for decoding colour with effect (effect API)
UNPACK_EFFECT_API_COLOUR_WITH_EFFECT = "<xxBxxBxxHHxxBxxB"

#: data stream unpack format string for decoding plain colour without effect (effect API)
UNPACK_EFFECT_API_COLOUR_WITHOUT_EFFECT = "<xxBxxBxxHH"

#: data stream unpack format string for decoding temperature with effect (effect API)
UNPACK_EFFECT_API_TEMPERATURE_WITH_EFFECT = "<xxBxxBxxHxxBxxB"

#: data stream unpack format string for decoding plain temperature without effect (effect API)
UNPACK_EFFECT_API_TEMPERATURE_WITHOUT_EFFECT = "<xxBxxBxxH"


_LOGGER = logging.getLogger(__name__)


#: Enum describing the different avaibale effects with their corresponding id
class EffectType(Enum):
    NONE = 0x00
    CANDLE = 0x01
    FIREPLACE = 0x02
    PRISM = 0x03
    SUNRISE = 0x09
    SPARKLE = 0x0A
    OPAL = 0x0B
    GLISTEN = 0x0C
    SUNSET = 0x0D
    UNDERWATER = 0x0E
    COSMOS = 0x0F
    SUNBEAM = 0x10
    ENCHANT = 0x11

    @classmethod
    def _missing_(cls, value):
        _LOGGER.warning(
            f"Unknown effect type: '{value}' reported by light, using default of none!"
        )
        return cls.NONE


#: EFFECT_COMMANDS (hex string) for the Effect Characteristic endpoint containing one byte id and one byte data length
class EffectCommands(Enum):
    ONOFF = "0101"
    BRIGHTNESS = "0201"
    TEMPERATURE = "0302"
    COLOURXY = "0404"
    TRANSITION_TIME = "0502"
    EFFECT = "0601"
    EFFECT_SPEED = "0801"


def _transition_tlv(transition_ms: int) -> bytes:
    if not isinstance(transition_ms, int):
        raise TypeError("transition_ms must be an integer")
    if transition_ms < 0 or transition_ms % 100 != 0:
        raise ValueError("transition_ms must be a non-negative multiple of 100")

    units = transition_ms // 100
    if units > 0xFFFF:
        raise ValueError("transition_ms is too large")

    return bytes.fromhex(EffectCommands.TRANSITION_TIME.value) + units.to_bytes(
        2, "little"
    )


class HueBleError(Exception):
    """
    Base exception of HueBLE.
    """

    pass


class ConnectionError(HueBleError):
    """
    Exception raised when connecting to a device fails.
    """

    pass


class InitialConnectionError(HueBleError):
    """
    Exception raised when the initial pre-pair pre-communication connect call fails.
    """

    pass


class PairingError(HueBleError):
    """
    Exception raised when pairing to a device fails.
    """

    pass


class ReadWriteError(HueBleError):
    """
    Exception raised when reading or writing a GATT attribute fails.
    """

    pass


class ServicesError(HueBleError):
    """
    Exception raised when service discovery/subscription fails.
    """

    pass


class CallbackError(HueBleError):
    """
    Exception raised when a callback raises an error.
    """

    pass


class DlcError(HueBleError):
    pass


@dataclass(frozen=True)
class _DlcCredentials:
    key: bytes
    zigbee_eui64: bytes
    name: str | None = None


@dataclass
class _AlsSession:
    key: bytes
    ieee_init: bytes
    ieee_resp: bytes
    tx_counter: int = 0
    rx_counter: int = 0


_DLC_PLAINTEXT_UUIDS = {
    "00002a29-0000-1000-8000-00805f9b34fb",
    "00002a24-0000-1000-8000-00805f9b34fb",
    "00002a28-0000-1000-8000-00805f9b34fb",
    "00002a00-0000-1000-8000-00805f9b34fb",
    "00002a01-0000-1000-8000-00805f9b34fb",
    "00002a05-0000-1000-8000-00805f9b34fb",
    "00002b29-0000-1000-8000-00805f9b34fb",
    "00002b2a-0000-1000-8000-00805f9b34fb",
    "97fe6561-0001-4f62-86e9-b71ee2da3d22",
    "97fe6561-2001-4f62-86e9-b71ee2da3d22",
    "97fe6561-2002-4f62-86e9-b71ee2da3d22",
    "97fe6561-a002-4f62-86e9-b71ee2da3d22",
    "29144af4-0002-4481-bfe9-6d0299b429e3",
    "89e6c2bd-0001-4f1e-aee0-2fa77c87cf7c",
    "18ee2ef5-263d-4559-959f-4f9c429f9d11",
    "18ee2ef5-263d-4559-959f-4f9c429f9d12",
    "64630238-8772-45f2-b87d-748a83218f04",
}


def _parse_tlvs(data: bytes) -> list[tuple[int, bytes]]:
    result = []
    offset = 0
    while offset < len(data):
        if offset + 2 > len(data):
            raise DlcError("Truncated DLC TLV")
        tag, length = data[offset : offset + 2]
        offset += 2
        end = offset + length
        if end > len(data):
            raise DlcError("Invalid DLC TLV length")
        result.append((tag, data[offset:end]))
        offset = end
    return result


def _parse_dlc_uri(uri: str) -> _DlcCredentials:
    prefix = "hue://dlc?"
    if not uri.startswith(prefix):
        raise DlcError("DLC URI must start with hue://dlc?")

    encoded = uri[len(prefix) :].strip()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except binascii.Error as e:
        raise DlcError("Invalid DLC URI") from e

    outer = dict(_parse_tlvs(raw))
    if 0x00 not in outer:
        raise DlcError("DLC URI has no shared-light record")

    fields = dict(_parse_tlvs(outer[0x00]))
    key = fields.get(0x0C)
    eui = fields.get(0x0D)

    if key is None or len(key) != 16:
        raise DlcError("DLC key must be 16 bytes")
    if eui is None or len(eui) != 8:
        raise DlcError("DLC Zigbee EUI must be 8 bytes")

    name = fields.get(0x0B)
    return _DlcCredentials(
        key=bytes(key),
        zigbee_eui64=bytes(eui),
        name=name.decode("utf-8", "replace") if name else None,
    )


def _zd_tlv(tag: int, value: bytes) -> bytes:
    return bytes((tag, len(value) - 1)) + value


def _parse_zd_tlvs(data: bytes) -> list[tuple[int, bytes]]:
    result = []
    offset = 0
    while offset < len(data):
        if offset + 2 > len(data):
            raise DlcError("Truncated Zigbee Direct TLV")
        tag = data[offset]
        length = data[offset + 1] + 1
        offset += 2
        end = offset + length
        if end > len(data):
            raise DlcError("Invalid Zigbee Direct TLV length")
        result.append((tag, data[offset:end]))
        offset = end
    return result


def _x25519(private_key: bytes, public_key: bytes) -> bytes:
    private = X25519PrivateKey.from_private_bytes(private_key)
    public = X25519PublicKey.from_public_bytes(public_key)
    return private.exchange(public)


def _zvd_address(device_id: str) -> bytes:
    value = re.sub(r"[^0-9A-Fa-f]", "", device_id).lower()
    if not value:
        raise DlcError("Unable to derive Zigbee Direct address")
    return bytes.fromhex(value.ljust(16, "c")[:16])[::-1]


def _compare_ieee(a: bytes, b: bytes) -> int:
    for i in range(7, -1, -1):
        if a[i] != b[i]:
            return -1 if a[i] < b[i] else 1
    return 0


def _session_identifier(
    ieee_init: bytes,
    ieee_resp: bytes,
    public_init: bytes,
    public_resp: bytes,
) -> bytes:
    if _compare_ieee(ieee_resp, ieee_init) <= 0:
        return ieee_resp + public_resp + ieee_init + public_init
    return ieee_init + public_init + ieee_resp + public_resp


def _derive_session_key(
    psk: bytes,
    ieee_init: bytes,
    ieee_resp: bytes,
    private_init: bytes,
    public_init: bytes,
    public_resp: bytes,
) -> bytes:
    generator = hashlib.sha256(psk).digest()
    shared = _x25519(private_init, public_resp)
    identifier = _session_identifier(ieee_init, ieee_resp, public_init, public_resp)
    intermediate = hashlib.sha256(shared + identifier + generator).digest()
    return hmac.new(intermediate, b"\x01", hashlib.sha256).digest()[:16]


def _confirmation_mac(
    initiator: bool,
    session_key: bytes,
    ieee_init: bytes,
    ieee_resp: bytes,
    public_init: bytes,
    public_resp: bytes,
) -> bytes:
    label = b"KC_2_U" if initiator else b"KC_2_V"
    data = label + ieee_resp + public_resp + ieee_init + public_init
    return hmac.new(session_key, data, hashlib.sha256).digest()


def _uuid_bytes(value: str) -> bytes:
    return bytes.fromhex(value.replace("-", ""))


def _associated_data(service_uuid: str, characteristic_uuid: str) -> bytes:
    return (
        _uuid_bytes(service_uuid) + b"\x00" + _uuid_bytes(characteristic_uuid) + b"\x00"
    )


def _nonce(ieee: bytes, counter: int) -> bytes:
    return ieee + counter.to_bytes(4, "little") + b"\x05"


def _parse_light_control_info(data: bytes) -> tuple[int | None, int | None]:
    minimum = None
    maximum = None
    i = 0

    while i + 2 <= len(data):
        field = data[i]
        length = data[i + 1]
        start = i + 2
        end = start + length

        if end > len(data):
            break

        value = data[start:end]

        if field == 0x01 and length == 2:
            minimum = int.from_bytes(value, "little")
        elif field == 0x02 and length == 2:
            maximum = int.from_bytes(value, "little")

        i = end

    return minimum, maximum


class HueBleLight(object):
    """Philips Hue BLE Light object."""

    def __init__(self, ble_device: BLEDevice, dlc_uri: str | None = None):
        """Initialise light object. dlc_uri enables shared-light authentication."""

        _LOGGER.debug(
            f"""Initializing Hue light "{ble_device.name}" with"""
            f""" address "{ble_device.address}" and details"""
            f""" "{ble_device.details}"."""
        )

        self._ble_device = ble_device
        self._client: BleakClient = None
        self._dlc_credentials = _parse_dlc_uri(dlc_uri) if dlc_uri else None
        self._als_session: _AlsSession | None = None

        if self._dlc_credentials is not None and AESCCM is None:
            raise DlcError("DLC support requires the cryptography package")
        self._manufacturer = None
        self._model = None
        self._fw = None
        self._zigbee_address = None
        self._light_name = None
        self._power_on = False
        self._brightness = None
        self._colour_temp = None
        self._minimum_mireds = MIN_MIREDS
        self._maximum_mireds = MAX_MIREDS
        self._colour_xy = None
        self._effect = None
        self._effect_speed = None

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
        """Executes all registered callbacks for a state change. Exceptions are caught and re-raised."""
        for function in self._state_changed_callbacks:
            try:
                function()
            except Exception as e:
                raise CallbackError(
                    f"""Exception executing state changed callback on "{self.name}". Function: "{function.__name__}". E: "{e}"."""
                ) from e

    def _disconnect_callback(self, client: BaseBleakClient) -> None:
        """Private method. Updates program state and will attempt reconnect
        if the disconnect was unexpected.
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
                f""" gave us "{client}". Ignoring disconnect event."""
            )
            return

        self._als_session = None

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
            asyncio.create_task(self.reconnect())

        else:
            _LOGGER.warning(
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

    async def _wait_for_als_packet(
        self, queue: asyncio.Queue[bytes], opcode: int, timeout: float = 8.0
    ) -> bytes:
        async with asyncio.timeout(timeout):
            while True:
                packet = await queue.get()
                if packet and packet[0] == opcode:
                    return packet

    async def _authorize_dlc(self) -> None:
        creds = self._dlc_credentials
        if creds is None:
            return

        if self._client.services.get_characteristic(UUID_ZD_AUTHENTICATE) is None:
            raise DlcError("Light does not expose Zigbee Direct authentication")

        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def notify(_, data: bytearray):
            queue.put_nowait(bytes(data))

        ieee_init = _zvd_address(self.address)
        private_init = os.urandom(32)
        generator = hashlib.sha256(creds.key).digest()
        public_init = _x25519(private_init, generator)

        await self._client.start_notify(UUID_ZD_AUTHENTICATE, notify)
        try:
            message = (
                b"\x01" + DLC_ALS_METHOD_TLV + _zd_tlv(0x02, ieee_init + public_init)
            )
            await self._client.write_gatt_char(
                UUID_ZD_AUTHENTICATE, message, response=True
            )

            response = await self._wait_for_als_packet(queue, 0x02)
            tlvs = _parse_zd_tlvs(response[1:])
            point = next((value for tag, value in tlvs if tag == 0x02), None)
            if point is None or len(point) != 40:
                raise DlcError("Invalid ALS public-point response")

            ieee_resp, public_resp = point[:8], point[8:]
            session_key = _derive_session_key(
                creds.key,
                ieee_init,
                ieee_resp,
                private_init,
                public_init,
                public_resp,
            )

            mac_i = _confirmation_mac(
                True,
                session_key,
                ieee_init,
                ieee_resp,
                public_init,
                public_resp,
            )
            expected_mac_r = _confirmation_mac(
                False,
                session_key,
                ieee_init,
                ieee_resp,
                public_init,
                public_resp,
            )

            await self._client.write_gatt_char(
                UUID_ZD_AUTHENTICATE,
                b"\x03" + _zd_tlv(0x04, mac_i),
                response=True,
            )

            response = await self._wait_for_als_packet(queue, 0x04)
            tlvs = _parse_zd_tlvs(response[1:])
            mac_r = next((value for tag, value in tlvs if tag == 0x04), None)
            if mac_r is None or not hmac.compare_digest(mac_r, expected_mac_r):
                raise DlcError("ALS responder authentication failed")

            self._als_session = _AlsSession(
                key=session_key,
                ieee_init=ieee_init,
                ieee_resp=ieee_resp,
            )
        finally:
            try:
                await self._client.stop_notify(UUID_ZD_AUTHENTICATE)
            except Exception:
                pass

    def _secure_characteristic(self, characteristic_uuid: str) -> bool:
        return (
            self._als_session is not None
            and characteristic_uuid.lower() not in _DLC_PLAINTEXT_UUIDS
        )

    def _service_uuid(self, characteristic_uuid: str) -> str:
        target = characteristic_uuid.lower()
        for service in self._client.services:
            for characteristic in service.characteristics:
                if characteristic.uuid.lower() == target:
                    return service.uuid
        raise DlcError(f"Unknown characteristic {characteristic_uuid}")

    def _decrypt_gatt(self, characteristic_uuid: str, data: bytes) -> bytes:
        if not self._secure_characteristic(characteristic_uuid):
            return bytes(data)
        if len(data) < 8:
            raise DlcError("Encrypted GATT value is too short")

        session = self._als_session
        counter = int.from_bytes(data[:4], "little")
        aad = _associated_data(
            self._service_uuid(characteristic_uuid), characteristic_uuid
        )
        plaintext = AESCCM(session.key, tag_length=4).decrypt(
            _nonce(session.ieee_resp, counter), data[4:], aad
        )
        if counter > session.rx_counter:
            session.rx_counter = counter
        return plaintext

    def _encrypt_gatt(self, characteristic_uuid: str, data: bytes) -> bytes:
        if not self._secure_characteristic(characteristic_uuid):
            return bytes(data)

        session = self._als_session
        session.tx_counter += 1
        counter = session.tx_counter
        aad = _associated_data(
            self._service_uuid(characteristic_uuid), characteristic_uuid
        )
        encrypted = AESCCM(session.key, tag_length=4).encrypt(
            _nonce(session.ieee_init, counter), bytes(data), aad
        )
        return counter.to_bytes(4, "little") + encrypted

    async def _subscribe_to_light(self) -> None:
        """Subscribes to the state of the light.
        Automatically called on connect.
        :raises Exception: If unable to subscribe to supported features.
        """

        # If turning off an on is supported :|
        if self.supports_on_off:

            def report(cHandle: int, data: bytearray) -> None:
                data = self._decrypt_gatt(UUID_POWER, data)
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
                data = self._decrypt_gatt(UUID_BRIGHTNESS, data)
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
                data = self._decrypt_gatt(UUID_TEMPERATURE, data)
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
                data = self._decrypt_gatt(UUID_XY_COLOUR, data)
                x, y = unpack("<HH", data)
                self._colour_xy = (x / 0xFFFF, y / 0xFFFF)
                _LOGGER.debug(
                    f"""Light "{self.name}" has informed us of a new"""
                    f""" XY colour state of ({self.colour_xy})"""
                )
                self._run_state_changed_callbacks()

            _LOGGER.debug("Subscribing to XY colour UUID")
            await self._client.start_notify(UUID_XY_COLOUR, report)

        # If Effects is supported
        if self.supports_effects:

            def report(cHandle: int, data: bytearray) -> None:
                data = self._decrypt_gatt(UUID_EFFECTS, data)
                # since we have all the other callbacks already in place, we only call the state changed callbacks if the effect data changed
                effect_state_changed = False

                # since the endpoint can/is used for all modes of the bulb, we get different size reports based on the current operating mode
                if len(data) == 18:
                    # we got a colour effect report containing onoff, brightness, colour and effect data
                    onoff, brightness, x, y, effect_raw, speed = unpack(
                        UNPACK_EFFECT_API_COLOUR_WITH_EFFECT, data
                    )
                    effect = EffectType(effect_raw)

                    if (self._effect is not effect) or (self._effect_speed != speed):
                        effect_state_changed = True

                    self._colour_xy = (x / 0xFFFF, y / 0xFFFF)
                    self._brightness = brightness
                    self._effect = effect
                    self._effect_speed = speed
                    self._power_on = bool(onoff)

                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" Effect state of ({self.effect})"""
                    )
                elif len(data) == 16:
                    # we got a temperature effect report containing onoff, brightness, temperature and effect data
                    onoff, brightness, temperature, effect_raw, speed = unpack(
                        UNPACK_EFFECT_API_TEMPERATURE_WITH_EFFECT, data
                    )
                    effect = EffectType(effect_raw)

                    if (self._effect is not effect) or (self._effect_speed != speed):
                        effect_state_changed = True

                    self._colour_temp = temperature
                    self._brightness = brightness
                    self._effect = effect
                    self._effect_speed = speed
                    self._power_on = bool(onoff)

                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" Effect state of ({self.effect})"""
                    )
                elif len(data) == 12:
                    # bulb is in colour mode, we got onoff, brightness and colourxy data
                    onoff, brightness, x, y = unpack(
                        UNPACK_EFFECT_API_COLOUR_WITHOUT_EFFECT, data
                    )
                    self._colour_xy = (x / 0xFFFF, y / 0xFFFF)
                    self._brightness = brightness
                    self._power_on = bool(onoff)

                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" XY colour state of ({self.colour_xy}) and brightness ({self.brightness})"""
                    )
                elif len(data) == 10:
                    # bulb is in temperature mode, we got onoff, brightness and temperature
                    onoff, brightness, colour_temp = unpack(
                        UNPACK_EFFECT_API_TEMPERATURE_WITHOUT_EFFECT, data
                    )
                    self._colour_temp = colour_temp
                    self._brightness = brightness
                    self._power_on = bool(onoff)

                    _LOGGER.debug(
                        f"""Light "{self.name}" has informed us of a new"""
                        f""" colour temp state of ({self.colour_temp})"""
                    )
                else:
                    # so far unkown
                    _LOGGER.warning(
                        "unrecognized effect response with length {len(data)}: {data}"
                    )

                if effect_state_changed:
                    self._run_state_changed_callbacks()

            _LOGGER.debug("Subscribing to Effects UUID")
            await self._client.start_notify(UUID_EFFECTS, report)

    async def connect(
        self,
        max_attempts: int = DEFAULT_CONNECTION_ATTEMPTS_MAX,
        connection_timeout: int = DEFAULT_CONNECTION_TIMEOUT,
        wait_timeout: int = DEFAULT_CONNECTION_WAIT_TIMEOUT,
        run_callbacks: bool = DEFAULT_ON_CONNECT_RUN_CALLBACKS,
    ) -> None:
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

        Registered callbacks will be run if a connection is achieved
        unless disabled.

        This function raises ConnectionError on failure.
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
                            try:
                                self._als_session = None
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
                                    raise Exception(
                                        f"""Not connected to "{self.name}"."""
                                    )

                            except Exception as e:
                                raise InitialConnectionError(
                                    f"""Failed to make an initial connection to the light "{self.name}". E: "{e}"."""
                                ) from e

                            if self._dlc_credentials is not None:
                                _LOGGER.debug("Authorizing DLC session...")
                                await self._authorize_dlc()
                            else:
                                _LOGGER.debug("Attempting to pair to the light...")
                                await self.pair()

                            # Determine what features the light supports
                            try:
                                _LOGGER.debug(
                                    "Determining services offered by the light..."
                                )
                                await self._determine_services()
                            except Exception as e:
                                raise ServicesError(
                                    f"""Failed to determine what services the light "{self.name}" offers. E: "{e}"."""
                                ) from e

                            # Subscribe to state updates from the features the light supports
                            try:
                                _LOGGER.debug(
                                    "Subscribing to services offered by the light..."
                                )
                                await self._subscribe_to_light()
                            except Exception as e:
                                raise ServicesError(
                                    f"""Failed to subscribe to services offered by the light "{self.name}". E: "{e}"."""
                                ) from e

                            # If the connection was successful, and we are paired,
                            # authenticated, and subscribed, then we no longer
                            # expect to be disconnected
                            self._expect_disconnect = False

                            # We also reset the attempts counter since we succeeded
                            self._connection_attempts = 0

                            # If we have reached here that means connecting and
                            # pairing was (probably) successful since we have now queried
                            # values and subscribed to updates
                            _LOGGER.debug(
                                f"""Successfully connected and authenticated"""
                                f""" to "{self.name}"."""
                            )

                            # We then exit the timeout context, run callbacks if required,
                            # since we have achieved a connection, a state change, then
                            # return

                    except asyncio.TimeoutError as e:
                        raise Exception(
                            f"""Timed out attempting to connect to "{self.name}"."""
                        ) from e

        except asyncio.TimeoutError as e:
            raise ConnectionError(
                f"""Timed out waiting for connection lock for "{self.name}"."""
            ) from e

        except Exception as e:
            raise ConnectionError(
                f"""Exception connecting to light "{self.name}". E: "{e}"."""
            ) from e

        if run_callbacks:
            self._run_state_changed_callbacks()

    async def pair(self):
        """Pair to light if not paired and raise PairingError on failure."""

        if self._dlc_credentials is not None:
            return

        # If paired return
        if self.authenticated is True:
            _LOGGER.debug(f"""System is already paired to "{self.name}".""")
            return

        # If mac return as pairing is not supported on MacOS
        if platform.system() == "Darwin":
            _LOGGER.warning(
                "Pairing is not supported on MacOS! You must pair manually!"
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

        except asyncio.TimeoutError as e:
            raise PairingError(
                f"""Timed out attempting to pair to "{self.name}"."""
            ) from e

        except BleakError as e:
            raise PairingError(
                f"""Error from Bluetooth backend when attempting to pair to "{self.name}". E: "{e}"."""
            ) from e

    async def _pair_bluez(self):
        """Workaround for bluez authentication issues."""
        from dbus_fast.aio import MessageBus
        from dbus_fast.service import ServiceInterface, method
        from dbus_fast import BusType

        class BluezAgent(ServiceInterface):
            """Agent for automatically accepting pairing passkeys."""

            def __init__(self):
                super().__init__("org.bluez.Agent1")

            @method()
            def RequestConfirmation(self, device: "o", passkey: "u"):
                _LOGGER.debug(f"Auto confirming passkey {passkey} for {device}")
                return

            @method()
            def Cancel(self):
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
        await agent_manager.call_register_agent(agent_path, "KeyboardDisplay")
        _LOGGER.debug("Pairing agent ready!")

        async with asyncio.timeout(DEFAULT_PAIR_TIMEOUT):

            try:
                await asyncio.sleep(1)
                _LOGGER.debug("Sending pairing command...")
                await self._client.pair()
            finally:
                _LOGGER.debug("Stopping pairing agent...")
                await agent_manager.call_unregister_agent(agent_path)
                bus.unexport(agent_path, agent)
                bus.disconnect()

    async def _determine_services(self) -> None:
        """Determines what features the light supports.
        The data may then be retrieved via the supports properties.
        :raises BleakError: If unable to determine services offered.
        """

        # If debug mode enabled print all services offered by light as well as the readable values
        if _LOGGER.isEnabledFor(logging.DEBUG):
            await self.print_services()

        # Determine available services
        if self._client.services.get_characteristic(UUID_MANUFACTURER):
            self._manufacturer = DEFAULT_METADATA_STRING
        else:
            _LOGGER.warning(
                f"""Light "{self.name}" does not appear to """
                f"""support polling the manufacturer metadata."""
            )
        if self._client.services.get_characteristic(UUID_MODEL):
            self._model = DEFAULT_METADATA_STRING
        else:
            _LOGGER.warning(
                f"""Light "{self.name}" does not appear to """
                f"""support polling the model metadata."""
            )
        if self._client.services.get_characteristic(UUID_FW_VERSION):
            self._fw = DEFAULT_METADATA_STRING
        else:
            _LOGGER.warning(
                f"""Light "{self.name}" does not appear to """
                f"""support polling the firmware version metadata."""
            )
        if self._client.services.get_characteristic(UUID_ZIGBEE_ADDRESS):
            self._zigbee_address = DEFAULT_METADATA_STRING
        else:
            _LOGGER.warning(
                f"""Light "{self.name}" does not appear to """
                f"""support polling the ZigBee address metadata."""
            )
        if self._client.services.get_characteristic(UUID_NAME):
            self._light_name = DEFAULT_METADATA_STRING
        else:
            _LOGGER.warning(
                f"""Light "{self.name}" does not appear to """
                f"""support polling the light name."""
            )
        if (
            self._client.services.get_characteristic(UUID_LIGHT_CONTROL_INFO)
            is not None
        ):
            try:
                info = await self._read_gatt(UUID_LIGHT_CONTROL_INFO)
                minimum, maximum = _parse_light_control_info(info)

                if minimum is not None:
                    self._minimum_mireds = minimum
                if maximum is not None:
                    self._maximum_mireds = maximum
            except Exception as e:
                _LOGGER.debug(f"Unable to read light control info: {e}")

        if self._client.services.get_characteristic(UUID_POWER) is not None:
            self._power_on = False
        else:
            _LOGGER.error(
                f"""Light "{self.name}" does not appear to """
                f"""support turning on and off."""
            )
            self._power_on = None
        if self._client.services.get_characteristic(UUID_BRIGHTNESS) is not None:
            self._brightness = 0
        else:
            _LOGGER.debug(
                f"""Light "{self.name}" does not appear to """
                f"""support changing the brightness."""
            )
            self._brightness = None
        if self._client.services.get_characteristic(UUID_TEMPERATURE) is not None:
            self._colour_temp = 0
        else:
            _LOGGER.debug(
                f"""Light "{self.name}" does not appear to """
                f"""support changing the colour temp."""
            )
            self._colour_temp = None
        if self._client.services.get_characteristic(UUID_XY_COLOUR) is not None:
            self._colour_xy = (0.0, 0.0)
        else:
            _LOGGER.debug(
                f"""Light "{self.name}" does not appear to """
                f"""support changing the XY colour."""
            )
            self._colour_xy = None
        if self._client.services.get_characteristic(UUID_EFFECTS) is not None:
            self._effect = EffectType.NONE
            self._effect_speed = 0
        else:
            _LOGGER.debug(
                f"""Light "{self.name}" does not appear to """
                f"""support changing effects."""
            )
            self._effect = None
            self._effect_speed = None

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
            _LOGGER.exception(
                f"""Timeout attempting to disconnect from "{self.name}"."""
            )
        except BleakError:
            _LOGGER.exception(
                f"""BleakError attempting to disconnect from "{self.name}"."""
            )

        self._als_session = None

        # Throw away the client
        self._client = None

    async def poll_state(
        self,
        timeout=DEFAULT_POLL_STATE_TIMEOUT,
        run_callbacks_if_changed=DEFAULT_POLL_STATE_CALLBACKS_IF_CHANGED,
    ) -> bool:
        """Updates the local state with values from the light using polling.
        This will only populate the fields that the light supports (i.e it
        should not error out if your light does not support colour).
        A lock is used to only allow one state update at a time with
        a timeout. Any callbacks are run outside of the state lock but
        within the timeout lock. asyncio.TimeoutError raised on timeout.
        Returns true/false if the state changed. Passes through any raised exceptions.
        """
        state_changed = False

        if self._state_update_lock.locked():
            _LOGGER.debug(
                f"""Waiting for state update lock of "{self.name}" to be"""
                f""" released."""
            )

        # Timeout if waiting too long
        async with asyncio.timeout(timeout):

            # Only one device may poll at a time
            async with self._state_update_lock:
                _LOGGER.debug(f"""Processing state update request for "{self.name}".""")

                if self._manufacturer:
                    prev = self.manufacturer
                    if prev != await self.poll_manufacturer(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling manufacturer")

                if self._model:
                    prev = self.model
                    if prev != await self.poll_model(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling model")

                if self._fw:
                    prev = self.firmware
                    if prev != await self.poll_firmware(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling firmware version")

                if self._zigbee_address:
                    prev = self.zigbee_address
                    if prev != await self.poll_zigbee_address(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling ZigBee address")

                if self._light_name:
                    prev = self.name_in_app
                    if prev != await self.poll_light_name(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling light name")

                if self.supports_on_off:
                    prev = self.power_state
                    if prev != await self.poll_power_state(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling power state")

                if self.supports_brightness:
                    prev = self.brightness
                    if prev != await self.poll_brightness(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling brightness")

                if self.supports_colour_temp:
                    prev = self.colour_temp
                    if prev != await self.poll_colour_temp(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling colour temp")

                if self.supports_colour_xy:
                    prev = self.colour_xy
                    if prev != await self.poll_colour_xy(write_state=True):
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling XY colour")

                if self.supports_effects:
                    prev_effect_speed = self._effect_speed
                    prev_effect = self._effect

                    effect, effect_speed = await self.poll_effects(write_state=True)
                    if prev_effect != effect or prev_effect_speed != effect_speed:
                        state_changed = True
                else:
                    _LOGGER.debug("Light does not support polling effects")

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
                    f"""Colour XY: "{self.colour_xy}"\n"""
                    f"""Effects: "{self._effect}"\n"""
                    f"""Effect speed: "{self._effect_speed}"."""
                )

            # Callbacks are run outside of the state update lock
            if run_callbacks_if_changed and state_changed:
                self._run_state_changed_callbacks()

        return state_changed

    async def _read_gatt(
        self,
        property: str,
        attempt_timeout: int = DEFAULT_READ_GATT_TIMEOUT,
        max_attempts: int = DEFAULT_READ_GATT_MAX_ATTEMPTS,
    ) -> bytearray:
        """Reads a GATT attribute from the light.
        If there is an error an exception will be thrown.
        """
        last_error = None
        for i in range(1, max_attempts + 1):
            try:
                async with asyncio.timeout(attempt_timeout):
                    await self.connect()
                    data = await self._client.read_gatt_char(property)
                    return self._decrypt_gatt(property, data)

            except Exception as e:
                _LOGGER.debug(
                    f"""Failed to read value from "{self.name}" on attempt"""
                    f""" {i}/{max_attempts}. Error message "{e}"."""
                )
                last_error = e
        raise ReadWriteError(
            f"""Unable to read from "{self.name}" after"""
            f""" {max_attempts} attempts"""
        ) from last_error

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
        last_error = None
        for i in range(1, max_attempts + 1):
            try:
                async with asyncio.timeout(attempt_timeout):
                    await self.connect()
                    payload = self._encrypt_gatt(property, data)
                    return await self._client.write_gatt_char(
                        property, payload, response=True
                    )

            except Exception as e:
                _LOGGER.debug(
                    f"""Failed to write value to "{self.name}" on attempt"""
                    f""" {i}/{max_attempts}. Error message "{e}"."""
                )
                last_error = e
        raise ReadWriteError(
            f"""Unable to write to "{self.name}" after"""
            f""" {max_attempts} attempts"""
        ) from last_error

    async def print_services(self) -> None:
        """
        Prints all available GATT services in the debug log.
        See: `original <https://github.com/hbldh/bleak/blob/develop/examples/service_explorer.py>`_
        """

        for service in self._client.services:
            _LOGGER.debug("[Service] %s", service)

            for char in service.characteristics:
                if char.uuid.lower() == UUID_DLC_KEY:
                    extra = ", Value: <redacted>"
                elif "read" in char.properties:
                    try:
                        value = await self._client.read_gatt_char(char.uuid)
                        value = self._decrypt_gatt(char.uuid, value)
                        extra = f", Value: {value}"
                    except Exception as e:
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
                            descriptor.handle
                        )
                        _LOGGER.debug(
                            "    [Descriptor] %s, Value: %r", descriptor, value
                        )
                    except Exception as e:
                        _LOGGER.debug("    [Descriptor] %s, Error: %s", descriptor, e)

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

    async def poll_effects(
        self, write_state: bool = DEFAULT_POLL_WRITES_STATE
    ) -> tuple[EffectType, int]:
        """Gets the effect type and effect speed as enum and int between 0 and 255."""
        buf = await self._read_gatt(UUID_EFFECTS)

        effect = EffectType.NONE
        effect_speed = 0

        # if an effect is active, more data is returned
        if len(buf) == 18:
            onoff, brightness, x, y, effect_raw, speed = unpack(
                UNPACK_EFFECT_API_COLOUR_WITH_EFFECT, buf
            )
            x_after = x / 0xFFFF
            y_after = y / 0xFFFF
            effect = EffectType(effect_raw)
            effect_speed = speed
            if write_state:
                self._colour_xy = (x_after, y_after)
                self._brightness = brightness
                self._effect = effect
                self._effect_speed = speed
                self._power_on = bool(onoff)
        elif len(buf) == 16:
            onoff, brightness, temperature, effect_raw, speed = unpack(
                UNPACK_EFFECT_API_TEMPERATURE_WITH_EFFECT, buf
            )
            effect = EffectType(effect_raw)
            effect_speed = speed
            if write_state:
                self._colour_temp = temperature
                self._brightness = brightness
                self._effect = effect
                self._effect_speed = speed
                self._power_on = bool(onoff)
        elif len(buf) == 12:
            # it is colour and bightness
            onoff, brightness, x, y = unpack(
                UNPACK_EFFECT_API_COLOUR_WITHOUT_EFFECT, buf
            )
            x_after = x / 0xFFFF
            y_after = y / 0xFFFF
            if write_state:
                self._colour_xy = (x_after, y_after)
                self._brightness = brightness
                self._power_on = bool(onoff)
        elif len(buf) == 10:
            # it is temperature mode
            onoff, brightness, colour_temp = unpack(
                UNPACK_EFFECT_API_TEMPERATURE_WITHOUT_EFFECT, buf
            )
            if write_state:
                self._colour_temp = colour_temp
                self._power_on = bool(onoff)
        else:
            # so far unkown
            _LOGGER.warning(
                f"unrecognized effect response with length {len(buf)}: {buf}"
            )

        return effect, effect_speed

    async def set_light_name(self, name: str):
        """Sets the name of the light. Not tested, use at own risk."""
        await self._write_gatt(UUID_NAME, str.encode(name))

    async def set_power(self, on: bool, transition_ms: int | None = None):
        """Sets the power state of the light."""
        if transition_ms is None:
            await self._write_gatt(UUID_POWER, bytes([1 if on else 0]))
            return

        buf = (
            bytes.fromhex(EffectCommands.ONOFF.value)
            + bytes([1 if on else 0])
            + _transition_tlv(transition_ms)
        )
        await self._write_gatt(UUID_EFFECTS, buf)

    async def set_brightness(
        self, brightness: int, transition_ms: int | None = None
    ):
        """Sets the brightness from an integer between 0 and 255"""
        brightness = max(min(brightness, 254), 1)
        if transition_ms is None:
            await self._write_gatt(UUID_BRIGHTNESS, bytes([brightness]))
            return
        buf = (
            bytes.fromhex(EffectCommands.BRIGHTNESS.value)
            + bytes([brightness])
            + _transition_tlv(transition_ms)
        )
        await self._write_gatt(UUID_EFFECTS, buf)

    async def set_colour_temp(
        self, colour_temp: int, transition_ms: int | None = None
    ):
        """Sets the colour temperature in mireds within the light's supported range."""
        temp = max(
            min(int(colour_temp), self._maximum_mireds),
            self._minimum_mireds,
        )
        data = temp.to_bytes(2, "little")
        if transition_ms is None:
            await self._write_gatt(UUID_TEMPERATURE, data)
            return

        buf = (
            bytes.fromhex(EffectCommands.TEMPERATURE.value)
            + data
            + _transition_tlv(transition_ms)
        )
        await self._write_gatt(UUID_EFFECTS, buf)

    async def set_colour_xy(
        self, x: float, y: float, transition_ms: int | None = None
    ):
        """Sets the XY colour coordinates from floats between 0.0 and 1.0."""
        data = pack("<HH", int(x * 0xFFFF), int(y * 0xFFFF))
        if transition_ms is None:
            await self._write_gatt(UUID_XY_COLOUR, data)
            return

        buf = (
            bytes.fromhex(EffectCommands.COLOURXY.value)
            + data
            + _transition_tlv(transition_ms)
        )
        await self._write_gatt(UUID_EFFECTS, buf)

    async def set_colour_effect(
        self,
        x: float,
        y: float,
        brightness: int,
        effect: EffectType,
        effect_speed: int,
        transition_ms: int | None = None,
    ):
        """
        Sets XY colour, brightness, effect and effect speed.

        :param x: X colour coordinate as float between 0.0 and 1.0
        :param y: Y colour coordinate as float between 0.0 and 1.0
        :param brightness: brightness as an integer between 0 and 255
        :param effect: Effect of Type EffectType (can be EffectType.NONE for plain colour)
        :param effect_speed: speed of the effect between 0 and 255
        """
        if effect is not EffectType.NONE:
            buf = pack(
                "<2sB2sB2sHH2sB2sB",
                bytes.fromhex(EffectCommands.ONOFF.value),
                0x1,
                bytes.fromhex(EffectCommands.BRIGHTNESS.value),
                max(min(brightness, 254), 1),
                bytes.fromhex(EffectCommands.COLOURXY.value),
                int(x * 0xFFFF),
                int(y * 0xFFFF),
                bytes.fromhex(EffectCommands.EFFECT.value),
                max(min(effect.value, 254), 1),
                bytes.fromhex(EffectCommands.EFFECT_SPEED.value),
                max(min(effect_speed, 255), 0),
            )
        else:
            # if no effect is selected we can just operate in colourxy mode and ommit the effect data in the transfer
            buf = pack(
                "<2sB2sB2sHH",
                bytes.fromhex(EffectCommands.ONOFF.value),
                0x1,
                bytes.fromhex(EffectCommands.BRIGHTNESS.value),
                max(min(brightness, 254), 1),
                bytes.fromhex(EffectCommands.COLOURXY.value),
                int(x * 0xFFFF),
                int(y * 0xFFFF),
            )
        if transition_ms is not None:
            buf += _transition_tlv(transition_ms)
        await self._write_gatt(UUID_EFFECTS, buf)

    async def set_temperature_effect(
        self,
        colour_temp: int,
        brightness: int,
        effect: EffectType,
        effect_speed: int,
        transition_ms: int | None = None,
    ):
        """
        Sets colour temperature, brightness, effect and effect speed.

        :param colour_temp: colour temperature between 153 and 500
        :param brightness: brightness as an integer between 0 and 255
        :param effect: Effect of Type EffectType (can be EffectType.NONE for plain colour)
        :param effect_speed: speed of the effect between 0 and 255
        """
        temperature = max(min(int(colour_temp), 500), 153)

        if effect is not EffectType.NONE:
            buf = pack(
                "<2sB2sB2sH2sB2sB",
                bytes.fromhex(EffectCommands.ONOFF.value),
                0x1,
                bytes.fromhex(EffectCommands.BRIGHTNESS.value),
                max(min(brightness, 254), 1),
                bytes.fromhex(EffectCommands.TEMPERATURE.value),
                temperature,
                bytes.fromhex(EffectCommands.EFFECT.value),
                max(min(effect.value, 254), 1),
                bytes.fromhex(EffectCommands.EFFECT_SPEED.value),
                max(min(effect_speed, 255), 0),
            )
        else:
            # if no effect is selected we can just operate in colourxy mode and ommit the effect data in the transfer
            buf = pack(
                "<2sB2sB2sH",
                bytes.fromhex(EffectCommands.ONOFF.value),
                0x1,
                bytes.fromhex(EffectCommands.BRIGHTNESS.value),
                max(min(brightness, 254), 1),
                bytes.fromhex(EffectCommands.TEMPERATURE.value),
                temperature,
            )
        if transition_ms is not None:
            buf += _transition_tlv(transition_ms)
        await self._write_gatt(UUID_EFFECTS, buf)

    @property
    def connected(self) -> bool:
        """Returns true if the client is connected to a light.
        This does not however mean that we are able to send
        and receive commands. Use the "available" property for that.
        """
        return self._client and self._client.is_connected

    @property
    def authenticated(self) -> bool | None:
        """Returns true if the light is paired.
        This only works on Linux. Returns None if unable
        to determine if device is authenticated.
        """

        # If the platform is not Linux then as far as I know there is
        # not an easy way to know if we are paired so we will try to
        # pair even if we are already paired. And if that pairing fails
        # we will not know until we try to read/write to/from the light
        # and get a permission error. Im probably missing something
        # so I should probably take another look in the future.
        if platform.system() != "Linux":
            _LOGGER.info(
                f"""Unable to determine if paired to "{self.name}" due to the platform!"""
            )
            return None

        # Get Linux specific properties of our connection
        properties = self._ble_device.details.get("props")

        # If the system does not have device properties then
        # it is unknown if we are authenticated to it
        if properties is None:
            _LOGGER.info(
                f"""Unable to determine if paired to "{self.name}" as that metadata was missing"""
            )
            return None

        # If paired return True
        if properties.get("Paired") is True:
            return True

        # If not paired return False
        elif properties.get("Paired") is False:
            return False

        # If unknown return None
        else:
            _LOGGER.info(
                f"""Unable to determine if paired to "{self.name}" as that section of the metadata was missing. Properties: {properties}" """
            )
            return None

    @property
    def available(self) -> bool:
        """Is the light connected and authenticated.
        Meaning are we able to send/receive commands to/from the light.
        On non-Linux systems it is assumed we are authenticated!.
        """
        if self.connected:
            if self._dlc_credentials is not None:
                return self._als_session is not None

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
    def manufacturer(self) -> str | None:
        """Manufacturer of the light."""
        return self._manufacturer

    @property
    def model(self) -> str | None:
        """Model of the light."""
        return self._model

    @property
    def firmware(self) -> str | None:
        """Firmware of the light."""
        return self._fw

    @property
    def zigbee_address(self) -> str | None:
        """Zigbee address of the light."""
        return self._zigbee_address

    @property
    def name(self) -> str:
        """Bluetooth name of the light.
        Should not but may differ from value from poll_light_name().
        """
        return self._ble_device.name

    @property
    def name_in_app(self) -> str | None:
        """Name of light in Hue app.
        Should not but may differ from the name (bluetooth) property.
        """
        return self._light_name

    @property
    def power_state(self) -> bool | None:
        """Is the light running?, you better go catch it."""
        if self.supports_on_off:
            return self._power_on
        else:
            return None

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
        """Minimum supported colour temperature in mireds."""
        if self.supports_colour_temp:
            return self._minimum_mireds
        else:
            return None

    @property
    def maximum_mireds(self) -> int | None:
        """Maximum supported colour temperature in mireds."""
        if self.supports_colour_temp:
            return self._maximum_mireds
        else:
            return None

    @property
    def colour_xy(self) -> tuple[float, float] | None:
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
            return None

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
    def effect(self) -> tuple[EffectType, int] | None:
        """Effect as tuple of EffectType enum and effect speed.
        Returns None if the feature is not supported by the light.
        """
        if self.supports_effects:
            return (self._effect, self._effect_speed)
        else:
            None

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

    @property
    def supports_effects(self) -> bool:
        """Does the light support effect control."""
        return self._effect is not None


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
