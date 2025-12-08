=======
Backend
=======

All internal and external functions of the module


HueBleLight class
-----------------

.. autoclass:: HueBLE.HueBleLight
   :members:
   :special-members: __init__
   :private-members:
   :no-index:


Static methods
--------------

.. automodule:: HueBLE
   :members: discover_lights
   :no-index:


Module constants
----------------

.. automodule:: HueBLE
   :members: UUID_MANUFACTURER, UUID_MODEL, UUID_FW_VERSION, UUID_ZIGBEE_ADDRESS, UUID_NAME, UUID_POWER, UUID_BRIGHTNESS, UUID_TEMPERATURE, UUID_XY_COLOUR, UUID_HUE_IDENTIFIER, MIN_MIREDS, MAX_MIREDS, DEFAULT_METADATA_STRING, DEFAULT_CONNECTION_ATTEMPTS_MAX, DEFAULT_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_WAIT_TIMEOUT, DEFAULT_PAIR_DELAY, DEFAULT_POLL_STATE_TIMEOUT, DEFAULT_READ_GATT_TIMEOUT, DEFAULT_READ_GATT_MAX_ATTEMPTS, DEFAULT_WRITE_GATT_TIMEOUT, DEFAULT_WRITE_GATT_MAX_ATTEMPTS, DEFAULT_POLL_WRITES_STATE, DEFAULT_DISCOVER_TIME   
   :no-index:


Exceptions
----------------

.. automodule:: HueBLE
   :members: HueBleError, ConnectionError, InitialConnectionError, PairingError, ReadWriteError, ServicesError, CallbackError
   :no-index:
