"""HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .constructs import EffectType
from .exceptions import (
    CallbackError,
    ConnectionError,
    HueBleError,
    InitialConnectionError,
    NotConnectedError,
    PairingError,
    ReadWriteError,
    ServicesError,
    TimeoutError,
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
    "NotConnectedError",
    "PairingError",
    "ReadWriteError",
    "ServicesError",
    "TimeoutError",
    "discover_lights",
]
