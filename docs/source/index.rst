HueBLE
======

.. figure:: https://raw.githubusercontent.com/flip-dots/HueBLE/master/hue_ble.png
    :target: https://github.com/flip-dots/HueBLE
    :alt: HueBLE Logo
    :scale: 50%

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
- ❔ Light state (power/brightness/temp/colour)
- ⚙️ Light configuration (name)
- 📊 Light metadata (manufacturer/model/zigbee address)
- 🤜 Supports push & polling models
- 🔂 Simple structure
- 📜 Mediocre documentation
- ✔️ More emojis than strictly necessary


Requirements
------------

- 🐍 Python 3.10+
- 📶 Bleak 0.19.0+
- 📶 bleak-retry-connector


Supported Operating Systems
---------------------------

- 🐧 Linux (BlueZ)

  - ✔️ Ubuntu Desktop
  - ✔️ Arch (HomeAssistant OS)

- 🏢 Windows

  - ✔️ Windows 10 

- 💾 Mac OSX

  - ❓ Maybe?

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
