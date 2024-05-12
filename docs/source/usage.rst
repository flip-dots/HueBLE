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


Pairing
^^^^^^^

On connection to a light this module will attempt to pair to the light
if it is not already paired. To pair with a light it must be in pairing mode,
this can be activated in the Philips Hue app.

``Settings -> Voice Assistants -> 
Amazon Alexa or Google Home -> Make Discoverable``

.. note::

    If you are not using Linux automatic pairing may not be possible and you
    will have to pair the lights in your OS.


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
- :py:attr:`.supports_on_off`
- :py:attr:`.supports_brightness`
- :py:attr:`.supports_colour_temp`
- :py:attr:`.supports_colour_xy`





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


Light Control 
^^^^^^^^^^^^^

The following methods can be used to change the current state of the light.

- :py:meth:`.set_light_name`
- :py:meth:`.set_power`
- :py:meth:`.set_brightness`
- :py:meth:`.set_colour_temp`
- :py:meth:`.set_colour_xy`


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
