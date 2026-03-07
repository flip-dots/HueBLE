"""Fixtures for tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from unittest import mock

import pytest


@pytest.fixture
def fast_timeouts():
    """Use to make asyncio.Timeout finish 100x faster."""
    original_timeout = asyncio.timeout

    def scaled_timeout(delay):
        return original_timeout(delay / 100 if delay else None)

    with mock.patch("asyncio.timeout", side_effect=scaled_timeout):
        yield
