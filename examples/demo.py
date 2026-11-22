# Copyright (c) 2026 Harvey Lelliott  # noqa: INP001
# SPDX-License-Identifier: MIT
"""
Demonstration program for HueBLE.

.. moduleauthor:: Harvey Lelliott (flip-dots) <harveylelliott@duck.com>

"""

import asyncio
import logging
from enum import Enum
from typing import TypeAlias, TypeVar

import bleak

# Enables use of the console
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.table import Table

from HueBLE import EffectType, HueBleLight, discover_lights

# Types
Number: TypeAlias = int | float
T = TypeVar("T")


class Actions(Enum):
    """Actions the user may take."""

    ON = "Turn on"
    OFF = "Turn off"
    BRIGHTNESS = "Set brightness"
    COLOUR_TEMP = "Set colour temperature"
    COLOUR_XY = "Set XY colour"
    EFFECT_TEMP = "Set colour temperature effect"
    EFFECT_XY = "Set XY colour effect"
    VIEW = "View device information"
    POLL = "Poll device information"
    EXIT = "Exit"


# Global variable for the console
console = Console()

# Global variable for the device
light: HueBleLight = None  # type: ignore[assignment]


async def print_str(message: object) -> None:
    """Print a string to the console asynchronously."""
    await asyncio.to_thread(
        console.print,
        message,
    )


async def async_prompt_str(message: str) -> str:
    """Prompt user for input while not blocking async runtime."""
    return await asyncio.to_thread(Prompt.ask, message, console=console)


async def async_prompt_bool(
    message: str,
    default: bool = False,  # noqa: FBT001, FBT002
) -> bool:
    """Prompt user for confirmation of an action."""
    return await asyncio.to_thread(
        Confirm.ask,
        message,
        console=console,
        default=default,
    )


async def range_check(value: Number, minimum: Number, maximum: Number) -> bool:
    """Return True if the value is in the range, else log the issue and return false."""
    if value < minimum:
        await print_str(f"Value must be above {minimum}!")
        return False
    if value > maximum:
        await print_str(f"Value must be below {maximum}!")
        return False
    return True


async def async_prompt_int(message: str, minimum: int, maximum: int) -> int:
    """Prompt user for an integer."""
    while True:
        response = await asyncio.to_thread(
            IntPrompt.ask,
            message,
            console=console,
        )
        if await range_check(response, minimum, maximum):
            return response


async def async_prompt_float(message: str, minimum: float, maximum: float) -> float:
    """Prompt user for a float."""
    while True:
        response = await asyncio.to_thread(
            FloatPrompt.ask,
            message,
            console=console,
        )
        if await range_check(response, minimum, maximum):
            return response


async def async_prompt_dict(
    message: str,
    options: dict[str, T],
    default: str | None = None,
) -> T:
    """Prompt the user to select an item from a dictionary."""

    keys = list(options.keys())
    default_idx = str(keys.index(default) + 1) if default in keys else None

    for idx, label in enumerate(keys, 1):
        tag = " [dim](default)[/dim]" if str(idx) == default_idx else ""
        console.print(f"  [bold cyan]{idx}.[/bold cyan] {label}{tag}")

    selected = await asyncio.to_thread(
        Prompt.ask,
        message,
        choices=[str(i) for i in range(1, len(keys) + 1)],
        default=default_idx,
        show_choices=False,
        console=console,
    )
    try:
        return options[keys[int(selected) - 1]]  # type: ignore[arg-type]
    except TypeError:
        await print_str("Invalid selection, try again!")
        return await async_prompt_dict(message, options, default)


async def background_progress(message: str, time: float) -> None:
    """Show a progress indicator."""
    with Progress(console=console, transient=True) as progress:
        task = progress.add_task(message, total=time)
        while not progress.finished:
            await asyncio.sleep(0.1)
            progress.update(task, advance=0.1)


def light_state_callback() -> None:
    """
    State change callback executed on state change of the device.
    """

    async def print_state_change() -> None:

        global light  # noqa: PLW0602

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold cyan")

        rows = [
            (
                "Power State:",
                "[green]ON[/green]" if light.power_state else "[red]OFF[/red]",
            ),
            (
                "Brightness:",
                f"{(light.brightness / 254.0) * 100 if light.brightness else None}%",
            ),
            ("Colour Temperature Mode:", "Yes" if light.colour_temp_mode else "No"),
            ("Colour Temperature:", f"{light.colour_temp} mireds"),
            ("XY Colour:", str(light.colour_xy)),
            ("Effect / Speed:", str(light.effect or "None")),
        ]
        for label, val in rows:
            grid.add_row(label, val)

        await print_str(
            Panel(
                grid,
                title="[yellow]Remote State Change[/yellow]",
                border_style="yellow",
                expand=False,
            ),
        )

    asyncio.run_coroutine_threadsafe(print_state_change(), asyncio.get_running_loop())


async def main() -> None:  # noqa: C901, PLR0912, PLR0915
    """
    Demonstration program.

    This program prompts the user to connect to a device and then
    provides an interactive interface for sending commands and
    polling information from the device.
    """

    global light  # noqa: PLW0603

    log_level = (
        logging.DEBUG
        if await async_prompt_bool("Show debug info? [Y/N]?", default=True)
        else logging.INFO
    )
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

    # Look for devices
    devices: list = []
    while not devices:
        wait_task = asyncio.create_task(
            background_progress("[cyan]Looking for devices...", 5),
        )
        devices = await discover_lights()
        await wait_task

    ble_device = await async_prompt_dict(
        "Select device to connect to!",
        {f"{d.name} ({d.address})": d for d in devices},
    )

    light = HueBleLight(ble_device)
    await print_str("[green]Connecting to device...")
    await light.connect()

    # Subscribe to state changes
    light.add_callback_on_state_changed(light_state_callback)

    # Prompt user for action once connected
    try:
        while True:

            action = Actions(
                await async_prompt_dict(
                    "What action would you like to perform?",
                    {x.value: x.value for x in Actions},
                ),
            )
            match action:

                # Turn on
                case Actions.ON:
                    await light.set_power(True)

                # Turn off
                case Actions.OFF:
                    await light.set_power(False)

                # Set brightness
                case Actions.BRIGHTNESS:
                    brightness = await async_prompt_int(
                        "Enter brightness value (0-254)",
                        0,
                        254,
                    )
                    await light.set_brightness(brightness)

                # Set colour temp
                case Actions.COLOUR_TEMP:
                    colour_temp = await async_prompt_int(
                        "Enter colour temperature in mireds (typ 153-500)",
                        0,
                        1000,
                    )
                    await light.set_colour_temp(colour_temp)

                # Set XY colour
                case Actions.COLOUR_XY:
                    x = await async_prompt_float(
                        "Enter X colour coordinate (0.0-1.0)",
                        0.0,
                        1.0,
                    )
                    y = await async_prompt_float(
                        "Enter Y colour coordinate (0.0-1.0)",
                        0.0,
                        1.0,
                    )
                    await light.set_colour_xy(x, y)
                # Set Colour Effect
                case Actions.EFFECT_XY:
                    brightness = await async_prompt_int(
                        "Enter brightness value (0-254)",
                        0,
                        254,
                    )
                    x = await async_prompt_float(
                        "Enter X colour coordinate (0.0-1.0)",
                        0.0,
                        1.0,
                    )
                    y = await async_prompt_float(
                        "Enter Y colour coordinate (0.0-1.0)",
                        0.0,
                        1.0,
                    )
                    effect = EffectType(
                        await async_prompt_dict(
                            "Select effect",
                            {e.name: e.value for e in EffectType},
                        ),
                    )
                    effect_speed = await async_prompt_int(
                        "Enter effect speed (0-254)",
                        0,
                        254,
                    )
                    transition_speed = await async_prompt_int(
                        "Enter transition speed (ms)",
                        0,
                        6553500,
                    )
                    await light.set_colour_effect(
                        x,
                        y,
                        brightness,
                        effect,
                        effect_speed,
                        transition_speed,
                    )
                # Set Temperature Effect
                case Actions.EFFECT_TEMP:
                    brightness = await async_prompt_int(
                        "Enter brightness value (0-254)",
                        0,
                        254,
                    )
                    colour_temp = await async_prompt_int(
                        "Enter colour temperature in mireds (typ 153-500)",
                        0,
                        1000,
                    )
                    effect = EffectType(
                        await async_prompt_dict(
                            "Select effect",
                            {e.name: e.value for e in EffectType},
                        ),
                    )
                    effect_speed = await async_prompt_int(
                        "Enter effect speed (0-254)",
                        0,
                        254,
                    )
                    transition_speed = await async_prompt_int(
                        "Enter transition speed (ms)",
                        0,
                        6553500,
                    )
                    await light.set_temperature_effect(
                        colour_temp,
                        brightness,
                        effect,
                        effect_speed,
                        transition_speed,
                    )
                # Print all light metadata
                case Actions.VIEW:
                    await print_str(light)

                case Actions.POLL:
                    await light.poll_state()
                    await print_str(light)

                case Actions.EXIT:
                    break

    # Warn about pairing errors.
    except bleak.BleakError as bleak_error:
        if "Insufficient Authentication" in str(bleak_error):
            await print_str(
                "Failed to pair to light. Make sure light is"
                " in pairing mode!\n"
                "If this does not resolve the issue try pairing"
                " using your OS.",
            )

    await print_str("[green]Goodbye :)")


if __name__ == "__main__":
    asyncio.run(main())
