# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
Fixtures for tests for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
from collections.abc import Generator
from unittest import mock

import pytest


@pytest.fixture
def fast_timeouts() -> Generator:
    """Use to make asyncio.Timeout finish 100x faster."""
    original_timeout = asyncio.timeout

    def scaled_timeout(delay: int) -> asyncio.Timeout:
        return original_timeout(delay / 100 if delay else None)

    with mock.patch("asyncio.timeout", side_effect=scaled_timeout):
        yield
