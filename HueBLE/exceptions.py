"""Exceptions for HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""


class HueBleError(Exception):
    """
    Base exception of HueBLE.
    """


class ConnectionError(HueBleError):
    """
    Exception raised when connecting to a device fails.
    """


class InitialConnectionError(HueBleError):
    """
    Exception raised when the initial pre-pair pre-communication connect call fails.
    """


class PairingError(HueBleError):
    """
    Exception raised when pairing to a device fails.
    """


class ReadWriteError(HueBleError):
    """
    Exception raised when reading or writing a GATT attribute fails.
    """


class ServicesError(HueBleError):
    """
    Exception raised when service discovery/subscription fails.
    """


class CallbackError(HueBleError):
    """
    Exception raised when a callback raises an error.
    """
