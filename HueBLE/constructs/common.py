# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
Common construct helpers of HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from enum import IntEnum
from typing import Any

from construct import ListContainer


class TLVListContainer(ListContainer):
    """
    Container of TLV values to allow for dictionary-like access.
    """

    def get(self, key: IntEnum) -> Any | None:  # noqa: ANN401
        """Return the value of the TLV tag or None if not present."""
        for item in self:
            if int(item.tag) == key.value:
                return item.value
        return None
