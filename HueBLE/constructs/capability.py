# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
Control constructs for HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from __future__ import annotations

from enum import IntEnum

from construct import (
    Enum as ConstructEnum,
)
from construct import (
    ExprAdapter,
    GreedyBytes,
    GreedyRange,
    Int8ul,
    Int16ul,
    Prefixed,
    Struct,
    Switch,
)

from .common import TLVListContainer


class CapabilityTLVTag(IntEnum):
    """
    The TLV tag in Hue capability messages which specifies what data the value contains.
    """

    MINIMUM_COLOUR_TEMP = 1
    MAXIMUM_COLOUR_TEMP = 2


"""The TLV construct for capability API messages made up of a list of TLVs."""
TLV_CAPABILITY = ExprAdapter(
    GreedyRange(
        Struct(
            "tag" / ConstructEnum(Int8ul, CapabilityTLVTag),
            "value"
            / Prefixed(
                Int8ul,
                Switch(
                    lambda ctx: int(ctx.tag),
                    {
                        CapabilityTLVTag.MINIMUM_COLOUR_TEMP: Int16ul,
                        CapabilityTLVTag.MAXIMUM_COLOUR_TEMP: Int16ul,
                    },
                    default=GreedyBytes,
                ),
            ),
        ),
    ),
    # Wrap the parsed list in custom container for tag lookup and debug logging
    decoder=lambda obj, _: TLVListContainer(obj),
    encoder=lambda obj, _: obj,
)
