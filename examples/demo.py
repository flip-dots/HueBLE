import asyncio
import bleak
import logging
import sys

# Allows for reading and writing to the console at the same time
# pip3 install aioconsole
from aioconsole import ainput
from HueBLE import HueBleLight, discover_lights


# Ask if debug log is wanted
while True:

    print("Show debug info? [Y/N]")
    response = input().lower()

    if response == "y":
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
        break

    elif response == "n":
        break

# Global variable for the light
light = None


def light_state_callback():
    """Callback which is run when the light notified us of a state change."""
    global light

    print("==== REMOTE STATE CHANGE DETECTED ====")
    print(f"Light power state: {light.power_state}")
    print(f"Light brightness: {light.brightness}")
    print(f"Is colour temp mode active: {light.colour_temp_mode}")
    print(f"Light colour temperature: {light.colour_temp}")
    print(f"Light XY colour: {light.colour_xy}")
    print("==== END OF STATE CHANGE REPORT ====")


async def main():
    """Main program loop."""
    global light

    print("Looking for lights...")
    # scanner = BleakScanner()
    lights = await discover_lights()

    # If we have found any lights
    if (len(lights)) != 0:

        # Ask the user to select a light
        print("Which light would you like to connect to?")
        for i in range(1, len(lights) + 1):
            light = lights[i - 1]
            print(f"""{i}. "{light.name}" with MAC "{light.address}""")

        # Connect to the selected light
        ble_device = lights[int(await ainput("> ")) - 1]
        light = HueBleLight(ble_device)
        await light.connect()

        # Subscribe to state changes
        light.add_callback_on_state_changed(light_state_callback)

        # Prompt user for action
        while True:
            print("What action would you like to perform?")
            print(
                "1. Turn On\n"
                "2. Turn Off\n"
                "3. Set brightness\n"
                "4. Set colour temp\n"
                "5. Set XY colour\n"
                "6. View info\n"
                "7. Exit"
            )

            action = int(await ainput("> ")) - 1

            # Perform requested action
            try:
                match action:

                    # Turn on
                    case 0:
                        await light.set_power(True)

                    # Turn off
                    case 1:
                        await light.set_power(False)

                    # Set brightness
                    case 2:
                        print("Enter brightness value (0-255)")
                        await light.set_brightness(int(input()))

                    # Set colour temp
                    case 3:
                        print("Enter colour temp (153-500)")
                        await light.set_colour_temp(int(input()))

                    # Set XY colour
                    case 4:
                        print("Enter X value of color (0.0-1.0)")
                        x = float(input())
                        print("Enter Y value of color (0.0-1.0)")
                        y = float(input())
                        await light.set_colour_xy(x, y)
                    # Print all light metadata
                    case 5:
                        # Poll all values from the light
                        await light.poll_state()
                        print(f"Light name: {light.name}")
                        print(f"Light address: {light.address}")
                        print(f"Light manufacturer: {light.manufacturer}")
                        print(f"Light model: {light.model}")
                        print(f"Supports on/off: {light.supports_on_off}")
                        print(f"Supports brightness:" f" {light.supports_brightness}")
                        print(f"Supports colour temp:" f" {light.supports_colour_temp}")
                        print(f"Supports XY color: {light.supports_colour_xy}")
                        print(f"Light firmware: {light.firmware}")
                        print(f"Light Zigbee address: {light.zigbee_address}")
                        print(f"Light power state: {light.power_state}")
                        print(f"Light brightness: {light.brightness}")
                        print(
                            f"Is colour temp mode active:" f" {light.colour_temp_mode}"
                        )
                        print(f"Light colour temperature: {light.colour_temp}")
                        print(f"Light minimum mireds: {light.minimum_mireds}")
                        print(f"Light maximum mireds: {light.maximum_mireds}")
                        print(f"Light color XY: {light.colour_xy}")

                    case 6:
                        break

            # Warn about pairing errors.
            except bleak.BleakError as bleak_error:
                if "Insufficient Authentication" in str(bleak_error):
                    print(
                        "Failed to pair to light. Make sure light is"
                        " in pairing mode!\n"
                        "If this does not resolve the issue try pairing"
                        " using your OS."
                    )

    else:
        print("No lights found!")

    print("Goodbye :)")


if __name__ == "__main__":
    asyncio.run(main())
