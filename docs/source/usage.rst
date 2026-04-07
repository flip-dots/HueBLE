=====
Usage
=====

.. _bleak: https://bleak.readthedocs.io/en/latest/usage.html/
.. _BLEDevice: https://bleak.readthedocs.io/en/latest/api/index.html#bleak.backends.device.BLEDevice/


It is recommended you read through the :doc:`examples <examples>` first to obtain an
understanding of the intended usage before diving into the documentation.

General approach
----------------

This library can use either a :ref:`poll <poll>` or :ref:`push <push>` 
approach.

State updates from the light are stored in the :py:class:`.HueBleLight` object
and can be queried on demand without causing I/O operations. 
This internal state will be asynchronously updated when the light
notifies us of what has changed. Alternatively a polling approach
can be used by directly calling the :ref:`poll <poll>` methods.


Methods
-------

Automatic detection of Hue lights
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Hue lights can be automatically detected by the 
:py:meth:`discover_lights() <HueBLE.discover_lights>`
method which looks for 
:py:attr:`UUID_HUE_IDENTIFIER <HueBLE.UUID_HUE_IDENTIFIER>`
in the Bluetooth service data. This method returns a list of
`BLEDevice`_, each of which have been detected as Hue lights.

``devices = await HueBLE.discover_lights()``


.. note::

    This mechanism may not be reliable as it has only been tested with model
    ``LCA006`` on FW ``1.104.2``. If automatic detection does not work, you can
    alternatively obtain a `BLEDevice`_ object via the 
    `Bleak`_ library, this is demonstrated in the 
    :ref:`basic example <basic_example>`.


Initializing a light
^^^^^^^^^^^^^^^^^^^^

In order to control a light you must initialize a
:py:class:`.HueBleLight` object.

``light = HueBleLight(ble_device)``

.. note::

    This method creates a :py:class:`.HueBleLight` object but does *not*
    automatically connect to the light.


Connecting to a light
^^^^^^^^^^^^^^^^^^^^^

The module will automatically connect to the light if it is not already
connected when a poll or control method is called. 
(e.g :py:meth:`.poll_brightness` or 
:py:meth:`.set_power`).

On a successful *connection* (not instantiation) the program will
:py:meth:`subscribe <HueBLE.HueBleLight._subscribe_to_light>` to future updates
of the lights state which may be accessed by the :ref:`properties <push>` of
the :py:class:`.HueBleLight` object.

.. note::

    On connection the internal state of the :py:class:`.HueBleLight` object
    is *not* updated, meaning values will remain at defaults until either a state change
    causes the attributes to be updated or the :py:meth:`.poll_state` method is called.


.. note::

    The ``@property`` methods (e.g :py:attr:`.power_state`) will not 
    automatically establish a connection.


You may manually establish a connection to the light by using the 
:py:meth:`.connect` function and cause the values in the internal state to be populated
by subsequently calling the :py:meth:`.poll_state` method.

``await light.connect()``

``await light.poll_state()``


.. _pairing_label:

Pairing
^^^^^^^

On connection to a light this module will attempt to pair to the light
if it is not already paired. To pair with a light it **must** be in pairing mode,
unconfigured lights are in pairing mode by default but this can also be achieved by
using the `voice assistant pairing feature <https://www.philips-hue.com/en-us/explore-hue/works-with/amazon-alexa/set-up>`_
in the Phillips Hue App (`Android <https://play.google.com/store/apps/details?id=com.philips.lighting.hue2>`_
/`iOS <https://apps.apple.com/us/app/philips-hue/id1055281310>`_) or by 
`factory resetting <https://www.philips-hue.com/en-us/support/article/how-to-factory-reset-philips-hue-lights/000004>`_ 
the light.

``Settings -> Voice Assistants -> 
Amazon Alexa or Google Home -> Make Discoverable``

.. note::

    If you `factory reset <https://www.philips-hue.com/en-us/support/article/how-to-factory-reset-philips-hue-lights/000004>`_ the light
    its Bluetooth address will change as it is randomly generated.

.. note::

    Pairing automatically is `not supported <https://bleak.readthedocs.io/en/latest/backends/macos.html#pairing>`_ on MacOS, you
    will be prompted to pair to the light by the OS upon first connection. Further connections will not
    require this unless the light is reset.


Full state updates
^^^^^^^^^^^^^^^^^^

Some attributes of the light are not possible to obtain via :ref:`push <push>`,
such as the :py:attr:`.manufacturer`, :py:attr:`.model`, and :py:attr:`.firmware` 
properties. The :py:meth:`.poll_state` method may be used to poll all of the 
values from the light which will be written to the internal state of the 
:py:class:`.HueBleLight` object, the state can then be accessed by the 
:ref:`properties <push>` of the :py:class:`.HueBleLight` object.

``await light.poll_state()``


Subscribing to changes
^^^^^^^^^^^^^^^^^^^^^^

Using the :py:meth:`.add_callback_on_state_changed` method you may register a
callback which will be called whenever the state of the light changes,
including connection and disconnection events. An example usage of this can
be found in the :ref:`complex example <complex_example>`.

``light.add_callback_on_state_changed(my_method)``

.. note::

    Expected disconnects caused by the calling of :py:meth:`.disconnect` will
    not cause callbacks to be executed.


Querying information
^^^^^^^^^^^^^^^^^^^^

There are multiple ways to obtain the lights current state.


.. _push:

Local push
""""""""""

The lights current state is stored inside the :py:class:`.HueBleLight` object
and once connected the light notifies us of any state changes which are then
used to update the local state.

This is the recommended approach as it allows for the value to be frequently
queried for no I/O cost, allowing for use in systems such as Home Assistant.

The local state can be queried using the following ``@property`` methods.

- :py:attr:`.connected`
- :py:attr:`.available`
- :py:attr:`.address`
- :py:attr:`.manufacturer`
- :py:attr:`.model`
- :py:attr:`.firmware`
- :py:attr:`.zigbee_address`
- :py:attr:`.name`
- :py:attr:`.name_in_app`
- :py:attr:`.power_state`
- :py:attr:`.brightness`
- :py:attr:`.colour_temp`
- :py:attr:`.minimum_mireds`
- :py:attr:`.maximum_mireds`
- :py:attr:`.colour_xy`
- :py:attr:`.colour_temp_mode`
- :py:attr:`.effect`
- :py:attr:`.supports_on_off`
- :py:attr:`.supports_brightness`
- :py:attr:`.supports_colour_xy`
- :py:attr:`.supports_colour_temp`
- :py:attr:`.supports_effects`





.. _poll:

Local polling
"""""""""""""

If you wish to directly poll the values from the light then the following
methods can be used. The usage of these methods is strongly discouraged as
improper usage can result in heavy I/O usage, especially if you are using
multiple instances of this library to control many lights at the same time.
I trust you to be responsible ;)

- :py:meth:`.poll_state`
- :py:meth:`.poll_manufacturer`
- :py:meth:`.poll_model`
- :py:meth:`.poll_firmware`
- :py:meth:`.poll_zigbee_address`
- :py:meth:`.poll_light_name`
- :py:meth:`.poll_power_state`
- :py:meth:`.poll_brightness`
- :py:meth:`.poll_colour_temp`
- :py:meth:`.poll_colour_xy`
- :py:meth:`.poll_effects`


Light Control 
^^^^^^^^^^^^^

The following methods can be used to change the current state of the light.

- :py:meth:`.set_light_name`
- :py:meth:`.set_power`
- :py:meth:`.set_brightness`
- :py:meth:`.set_colour_temp`
- :py:meth:`.set_colour_xy`
- :py:meth:`.set_colour_effect`
- :py:meth:`.set_temperature_effect`


Effect Control
^^^^^^^^^^^^^^
With newer firmware, the Hue bulbs support a range of effects like candle, fireplace and much more.
Those can be set with the following methods. With the new BLE endpoint used for the effects, it is now possible to set
everything at once. Therefore, these methods also takes colour/temperature, brightness. The effect itself is defined by
a enum of possible effects and the effect speed as a number between 0 and 255. The default speed used by philips is 117.

- :py:meth:`.set_effect`
- :py:meth:`.set_temperature_effect`



Automatic Reconnection 
^^^^^^^^^^^^^^^^^^^^^^

This module implements two forms of automatic re-connection. The module
listens for disconnection events and only once the light has successfully 
been connected to will it attempt to automatically re-establish a connection
if it is lost. The delay to wait between attempts and maximum number of attempts
are defined as module constants which may be overridden.

The other mechanism will attempt to re-establish a connection whenever a method 
which requires a connection is called.


Other neat things
^^^^^^^^^^^^^^^^^

- You can set attributes such as colour while the light is in the off state 
  without turning the light on.

- Hue lights connected using Zigbee are still discoverable and controllable by 
  this module, even if they are connected to another Zigbee network or bound
  to a Zigbee switch. This means you can use Zigbee and Bluetooth at the same time.
  This can be done by pairing the light to the Zigbee hub or switch and then using
  the Hue app in Bluetooth mode to connect to the light over Bluetooth using the
  QR code on the side of the light and then using the Alexa/Google pairing steps.

  .. note::

    The Hue app will not let you setup a light using Bluetooth if it is already
    connected to a Hue hub that the app is aware of, the workaround is to remove
    the Hub from the Hue app or use a fresh install/device that is not paired with the hub.

