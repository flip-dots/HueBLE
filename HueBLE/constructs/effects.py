# Copyright (c) 2026 Harvey Lelliott
# SPDX-License-Identifier: MIT
"""
Effect data constructs for HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

from __future__ import annotations

import logging
from enum import IntEnum

from construct import (
    Container,
    ExprAdapter,
    Flag,
    GreedyBytes,
    GreedyRange,
    Int8ul,
    Int16ul,
    Prefixed,
    Struct,
    Switch,
)
from construct import (
    Enum as ConstructEnum,
)

from .common import TLVListContainer

_LOGGER = logging.getLogger(__name__)


class EffectType(IntEnum):
    """
    The effects supported by Hue lights.
    """

    NONE = 0
    CANDLE = 1
    FIREPLACE = 2
    PRISM = 3
    SUNRISE = 9
    SPARKLE = 10
    OPAL = 11
    GLISTEN = 12
    SUNSET = 13
    UNDERWATER = 14
    COSMOS = 15
    SUNBEAM = 16
    ENCHANT = 17

    @classmethod
    def _missing_(cls, value: object) -> EffectType:
        """Return default value when effect unknown.."""
        _LOGGER.warning(
            f"Unknown effect type: '{value}' reported by light, using default of none!",
        )
        return cls.NONE


class EffectTLVTag(IntEnum):
    """
    The TLV tag in Hue effect API messages which specifies what data the value contains.
    """

    ON_OFF = 1
    BRIGHTNESS = 2
    COLOUR_TEMP = 3
    COLOUR_XY = 4
    TRANSITION = 5
    EFFECT_TYPE = 6
    EFFECT_SPEED = 8


"""The TLV construct for effect API messages made up of a list of TLVs."""
TLV_EFFECT = ExprAdapter(
    GreedyRange(
        Struct(
            "tag" / ConstructEnum(Int8ul, EffectTLVTag),
            "value"
            / Prefixed(
                Int8ul,
                Switch(
                    lambda ctx: int(ctx.tag),
                    {
                        EffectTLVTag.ON_OFF: Flag,
                        EffectTLVTag.BRIGHTNESS: Int8ul,
                        EffectTLVTag.COLOUR_TEMP: Int16ul,
                        EffectTLVTag.COLOUR_XY: ExprAdapter(
                            Struct("x" / Int16ul, "y" / Int16ul),
                            decoder=lambda c, _: (c["x"] / 0xFFFF, c["y"] / 0xFFFF),
                            encoder=lambda v, _: Container(
                                x=int(v[0] * 0xFFFF),
                                y=int(v[1] * 0xFFFF),
                            ),
                        ),
                        EffectTLVTag.TRANSITION: Int16ul,
                        EffectTLVTag.EFFECT_TYPE: ExprAdapter(
                            Int8ul,
                            decoder=lambda val, _: EffectType(val),
                            encoder=lambda obj, _: int(obj),
                        ),
                        EffectTLVTag.EFFECT_SPEED: Int8ul,
                    },
                    default=GreedyBytes,
                ),
            ),
        ),
    ),
    # Wrap the parsed list in custom container for tag lookup and debug logging
    decoder=lambda obj, _: TLVListContainer(obj),
    # Use encoder to allow for building messages flat
    encoder=lambda obj, _: (
        [{"tag": k, "value": v} for k, v in sorted(obj.items())]
        if isinstance(obj, dict)
        else obj
    ),
)
