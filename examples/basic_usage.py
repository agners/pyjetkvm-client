"""Basic usage example."""

import argparse
import asyncio
import getpass

from pyjetkvm.client import JetKVMClient


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
        dc_power_state = await client.get_dc_power_state()
        print("DC Power State:", dc_power_state)

if __name__ == "__main__":
    asyncio.run(main())
