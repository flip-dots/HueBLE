# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
Exceptions for HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from collections.abc import Callable

from bleak.backends.device import BLEDevice


class HueBleError(Exception):
    """
    Base exception of HueBLE.
    """


class ConnectionError(HueBleError):  # noqa: A001
    """
    Exception raised when connecting to a device fails.
    """

    def __init__(self, device: BLEDevice, error: Exception) -> None:
        """Return new :exc:`~HueBLE.ConnectionError`."""
        self.device = device
        self.error = error
        message = (
            "Exception connecting to device "
            f"'{device.name} ({device.address})'. "
            f"E: '{error}'."
        )
        super().__init__(message)


class InitialConnectionError(HueBleError):
    """
    Exception raised when the initial pre-pair pre-communication connect call fails.
    """

    def __init__(self, device: BLEDevice, error: Exception) -> None:
        """Return new :exc:`~HueBLE.InitialConnectionError`."""
        self.device = device
        self.error = error
        message = (
            "Failed to make an initial connection to the device "
            f"'{device.name} ({device.address})'. "
            f"E: '{error}'."
        )
        super().__init__(message)


class PairingError(HueBleError):
    """
    Exception raised when pairing to a device fails.
    """


class TimeoutError(HueBleError):  # noqa: A001
    """
    Exception raised when an operation timed out.
    """


class NotConnectedError(HueBleError):
    """
    Exception raised when not connected to the device for something which requires it.
    """


class ReadWriteError(HueBleError):
    """
    Exception raised when reading or writing a GATT attribute fails.
    """


class ReadError(ReadWriteError):
    """
    Exception raised when reading a GATT attribute fails.
    """

    def __init__(
        self,
        device: BLEDevice,
        address: str,
        attempt: int,
        error: Exception | None,
    ) -> None:
        """Return new :exc:`~HueBLE.ReadError`."""
        self.device = device
        self.address = address
        self.attempt = attempt
        self.error = error
        message = (
            f"Failed to read '{address}' from "
            f"'{device.name} ({device.address})' after "
            f"{attempt} attempts. E: '{error}'."
        )
        super().__init__(message)


class WriteError(ReadWriteError):
    """
    Exception raised when writing a GATT attribute fails.
    """

    def __init__(
        self,
        device: BLEDevice,
        address: str,
        data: bytes,
        attempt: int,
        error: Exception | None,
    ) -> None:
        """Return new :exc:`~HueBLE.WriteError`."""
        self.device = device
        self.address = address
        self.data = data
        self.attempt = attempt
        self.error = error
        message = (
            f"Failed to write '{data.hex()}' at '{address}' to "
            f"'{device.name} ({device.address})' after "
            f"{attempt} attempts. E: '{error}'."
        )
        super().__init__(message)


class ServicesError(HueBleError):
    """
    Exception raised when service discovery/subscription fails.
    """


class ServiceDiscoveryError(ServicesError):
    """
    Exception raised when service discovery fails.
    """

    def __init__(self, device: BLEDevice, error: Exception) -> None:
        """Return new :exc:`~HueBLE.ServiceDiscoveryError`."""
        self.device = device
        self.error = error
        message = (
            "Failed to determine what services the device "
            f"'{device.name} ({device.address})' offers. "
            f"E: '{error}'."
        )
        super().__init__(message)


class ServiceSubscriptionError(ServicesError):
    """
    Exception raised when service subscription fails.
    """

    def __init__(self, device: BLEDevice, error: Exception) -> None:
        """Return new :exc:`~HueBLE.ServiceSubscriptionError`."""
        self.device = device
        self.error = error
        message = (
            "Failed to subscribe to services offered by the device "
            f"'{device.name} ({device.address})'. "
            f"E: '{error}'."
        )
        super().__init__(message)


class CallbackError(HueBleError):
    """
    Exception raised when a callback raises an error.
    """

    def __init__(self, device: BLEDevice, function: Callable, error: Exception) -> None:
        """Return new :exc:`~HueBLE.CallbackError`."""
        self.device = device
        self.function = function
        self.error = error
        message = (
            "Exception executing state changed callback on "
            f"'{device.name} ({device.address})'. "
            f"Function: '{function.__name__}'. E: '{error}'."
        )
        super().__init__(message)
