import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rocky.config import detect_hardware_profile

async def main():
    profile = await detect_hardware_profile()
    print(f"[*] Detected Hardware Profile: {profile.name} ({profile.value})")

if __name__ == "__main__":
    asyncio.run(main())
