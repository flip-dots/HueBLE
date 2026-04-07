HueBLE
======

.. figure:: https://raw.githubusercontent.com/flip-dots/HueBLE/main/hue_ble.png
    :target: https://github.com/flip-dots/HueBLE
    :alt: HueBLE Logo
    :scale: 50%

.. image:: https://img.shields.io/pypi/v/HueBLE.svg
    :target: https://pypi.python.org/pypi/HueBLE

.. image:: https://readthedocs.org/projects/hueble/badge/?version=latest
    :target: https://hueble.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status
      
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Black

Python module for controlling Bluetooth Philips Hue lights

 - 👌 Free software: MIT license
 - 🍝 Sauce: https://github.com/flip-dots/HueBLE
 - 📦 PIP: https://pypi.org/project/HueBLE/

This Python module enables you to control Philips Hue Bluetooth lights directly
from your computer, without the need for a Hue bridge or ZigBee dongle. It
leverages the Bleak library to interact with Bluetooth Philips Hue lights.

Features
--------

- 💡 On/Off control
- 🌗 Brightness control
- 🌡️ Colour temp control 
- 🌈 XY colour control
- 🌟 Effect control
- ❔ Light state (power/brightness/temp/colour)
- ⚙️ Light configuration (name)
- 📊 Light metadata (manufacturer/model/zigbee address)
- 🤜 Supports push & polling models
- 🔂 Simple structure
- 📜 Mediocre documentation
- ✔️ More emojis than strictly necessary


Requirements
------------

- 🐍 Python 3.11+
- 📶 Bleak 0.19.0+
- 📶 bleak-retry-connector


Supported Operating Systems
---------------------------

- 🐧 Linux (BlueZ)

  - ✔️ Ubuntu Desktop (24.04)
  - ✔️ Arch 
  - ✔️ Buildroot (HomeAssistant OS)

- 🏢 Windows

  - ✔️ Windows 10 

- 💾 Mac OSX

  - ✔️ Sequoia (15.7)
  
- 🛜 ESPHome (Bluetooth Proxy)

  - ESP32-C3-Super-Mini
  - ESP32-C5-N4R2


Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   usage
   examples
   api/index
   source
   history
