"""Basic usage example."""

import argparse
import asyncio
import getpass
import logging

from pyjetkvm.client import JetKVMClient

# Configure logging
logging.basicConfig(level=logging.WARNING)

async def main() -> None:
    """Run the basic usage example."""
    parser = argparse.ArgumentParser(description="Async JetKVM usage example")
    parser.add_argument(
        "url", help="Base URL of the JetKVM instance (e.g. http://jetkvm.local)"
    )
    args = parser.parse_args()

    async with JetKVMClient(args.url) as client:
        if not await client.is_setup():
            print("🔧 Device is not set up. Please open /welcome in your browser.")
            return

        password = getpass.getpass("🔐 Enter your JetKVM password: ")
        await client.login(password)
        print("✅ Login successful.")

        device_info = await client.get_device_info()
        print("📟 Device Info:")
        for k, v in device_info.items():
            print(f"  {k}: {v}")

        print("🔌 Setting up WebSocket connection...")
        await client.setup_ws()

        print("🔌 Setting up WebRTC connection...")
        await client.setup_webrtc()

        print("🌐 WebRTC connection established.")

        print("💬 Send JSON RPC messages")
        video = await client.get_video_state()
        print("Video State:", video)

        usb = await client.get_usb_state()
        print("USB State:", usb)

        storage_space = await client.get_storage_space()
        print("Storage Space:", storage_space)

        active_extension = await client.get_active_extension()
        print("Active Extension:", active_extension)

        if active_extension == "dc-power":
            dc_power_state = await client.get_dc_power_state()
            print("DC Power State:", dc_power_state)



if __name__ == "__main__":
    asyncio.run(main())
