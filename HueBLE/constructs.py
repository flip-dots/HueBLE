"""Data constructs for HueBLE module.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import logging
from enum import IntEnum
from typing import Any

from construct import (
    Container,
    Default,
    ExprAdapter,
    Flag,
    GreedyBytes,
    GreedyRange,
    Int8ul,
    Int16ul,
    ListContainer,
    Prefixed,
    Struct,
    Switch,
)
from construct import (
    Enum as ConstructEnum,
)

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
    def _missing_(cls, value):
        _LOGGER.warning(
            f"Unknown effect type: '{value}' reported by light, using default of none!"
        )
        return cls.NONE


class TLVTag(IntEnum):
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


class TLVListContainer(ListContainer):
    """
    Container of TLV values to allow for dictionary-like access.
    """

    def get(self, key: TLVTag) -> Any | None:
        """Return the value of the TLV tag or None if not present."""
        for item in self:
            if int(item.tag) == key.value:
                return item.value
        return None


"""The TLV construct for effect API messages made up of a list of TLVs."""
TLV_EFFECT = ExprAdapter(
    GreedyRange(
        Struct(
            "tag" / ConstructEnum(Int8ul, TLVTag),
            "value"
            / Prefixed(
                Int8ul,
                Switch(
                    lambda ctx: int(ctx.tag),
                    {
                        TLVTag.ON_OFF: Flag,
                        TLVTag.BRIGHTNESS: Int8ul,
                        TLVTag.COLOUR_TEMP: Int16ul,
                        TLVTag.COLOUR_XY: ExprAdapter(
                            Struct("x" / Int16ul, "y" / Int16ul),
                            decoder=lambda c, ctx: (c["x"] / 0xFFFF, c["y"] / 0xFFFF),
                            encoder=lambda v, ctx: Container(
                                x=int(v[0] * 0xFFFF), y=int(v[1] * 0xFFFF)
                            ),
                        ),
                        TLVTag.TRANSITION: Int16ul,
                        TLVTag.EFFECT_TYPE: ExprAdapter(
                            Int8ul,
                            decoder=lambda val, ctx: EffectType(val),
                            encoder=lambda obj, ctx: int(obj),
                        ),
                        TLVTag.EFFECT_SPEED: Int8ul,
                        Default: Struct("Unknown" / GreedyBytes),
                    },
                ),
            ),
        )
    ),
    # Wrap the parsed list in custom container for tag lookup and debug logging
    decoder=lambda obj, ctx: TLVListContainer(obj),
    # Use encoder to allow for building messages flat
    encoder=lambda obj, ctx: (
        [{"tag": k, "value": v} for k, v in sorted(obj.items())]
        if isinstance(obj, dict)
        else obj
    ),
)
