# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from .constructs import EffectType
from .exceptions import (
    CallbackError,
    ConnectionError,  # noqa: A004
    HueBleError,
    InitialConnectionError,
    NotConnectedError,
    PairingError,
    ReadError,
    ReadWriteError,
    ServiceDiscoveryError,
    ServicesError,
    ServiceSubscriptionError,
    TimeoutError,  # noqa: A004
    WriteError,
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
    "ReadError",
    "ReadWriteError",
    "ServiceDiscoveryError",
    "ServiceSubscriptionError",
    "ServicesError",
    "TimeoutError",
    "WriteError",
    "discover_lights",
]
