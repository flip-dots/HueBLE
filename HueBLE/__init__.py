"""HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .constructs import EffectType
from .exceptions import (
    CallbackError,
    ConnectionError,
    HueBleError,
    InitialConnectionError,
    PairingError,
    ReadWriteError,
    ServicesError,
)
from .light import HueBleLight
from .scan import discover_lights

__all__ = [
    "CallbackError",
    "ConnectionError",
    "EffectType",
    "HueBleError",
    "HueBleLight",
    "InitialConnectionError",
    "PairingError",
    "ReadWriteError",
    "ServicesError",
    "discover_lights",
]
