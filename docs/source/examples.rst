========
Examples
========

.. _basic_example:

Basic Example
-------------

Simple blinky light example demonstrating making a connection to a light
from its MAC address and making it turn off then on again.

.. literalinclude:: ../../examples/example.py
    :language: python
    :linenos:


.. _complex_example:

Complex Example
---------------

Demonstration program which implements the majority of the features of 
the module using a push based approach.

- ✔️ Scanning and detection of Hue lights
- ✔️ Connecting to the light
- ✔️ Reading values from the light
- ✔️ Setting parameters of the light
    - 💡 Power
    - 🌗 Brightness
    - 🌡️ Colour Temp
    - 🌈 XY Colour
- ✔️ Notifications of state changes to the light via push approach

.. literalinclude:: ../../examples/demo.py
    :language: python
    :linenos:
