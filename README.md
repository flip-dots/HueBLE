# HueBLE

![HueBLE logo](https://raw.githubusercontent.com/flip-dots/HueBLE/main/hue_ble.png)

[![PyPI Status](https://img.shields.io/pypi/v/HueBLE.svg)](https://pypi.python.org/pypi/HueBLE)
[![Documentation Status](https://readthedocs.org/projects/hueble/badge/?version=latest)](https://hueble.readthedocs.io/en/latest/?badge=latest)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Python module for controlling Bluetooth Philips Hue lights.
 - 👌 Free software: MIT license
 - 🍝 Sauce: https://github.com/flip-dots/HueBLE
 - 🖨️ Documentation: https://hueble.readthedocs.io/en/latest/
 - 📦 PIP: https://pypi.org/project/HueBLE/


This Python module enables you to control Philips Hue Bluetooth lights directly
from your computer, without the need for a Hue bridge or ZigBee dongle.
It leverages the Bleak library to interact with Bluetooth Philips Hue lights.


## Features

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


## Requirements

- 🐍 Python 3.11+
- 📶 Bleak 0.19.0+
- 📶 bleak-retry-connector


## Supported Operating Systems

- 🐧 Linux (BlueZ)
  - Ubuntu Desktop (24.04)
  - Arch 
  - Buildroot (HomeAssistant OS)
- 🏢 Windows
  - Windows 10 
- 💾 Mac OSX
  - Sequoia (15.7)
- 🛜 ESPHome (Bluetooth Proxy)
  - ESP32-C3-Super-Mini
  - ESP32-C5-N4R2


## Documentation

https://hueble.readthedocs.io/en/latest/


## Installation


### PIP

```
pip install HueBLE
```


### Manual

HueBLE consists of a single file (HueBLE.py) which you can simply put in the
same directory as your program. If you are using manual installation make sure
the dependencies are installed as well.

```
pip install bleak bleak-retry-connector dbus-fast
```


## Examples


### Quick start example

Example code from example.py

> [!NOTE]
> Do not forget to put the light in [pairing mode](https://hueble.readthedocs.io/en/latest/usage.html#pairing) before first connection!

```python
import asyncio
from bleak import BleakScanner
import HueBLE


async def main():

    # Address of light to connect to
    address = "F6:9B:48:A4:D2:D8"

    # Obtain the BLEDevice from bleak
    device = await BleakScanner.find_device_by_address(address)

    # Initialize the light object
    light = HueBLE.HueBleLight(device)

    # Optionally we could call connect but it will be called automatically
    # on the first request to the light. You might want to call this if
    # you want to subscribe to state changes without changing the lights state.
    # await light.connect()

    # Will automatically connect to the light and turn it off
    await light.set_power(False)

    # Wait
    await asyncio.sleep(5)

    # Turn the light back on again
    await light.set_power(True)

if __name__ == "__main__":
    asyncio.run(main())

```


### Demo program

A more fully featured demo program can be found in  ``` examples/demo.py ``` which demonstrates all of the implemented features.
