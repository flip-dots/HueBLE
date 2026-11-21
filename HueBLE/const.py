"""Constants for HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

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

#: new colour change and effect enpoint
UUID_EFFECTS = "932c32bd-0007-47a2-835a-a8d455b859dd"

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
