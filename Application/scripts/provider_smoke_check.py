"""Optional smoke check that makes live requests to configured speech providers."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from src.config import config
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.rime_stream import RimeStreamingTTSClient


async def verify_assemblyai() -> None:
    client = AssemblyAIStreamingClient(api_key=config.assemblyai_api_key)
    token = await client.fetch_token()
    if not token:
        raise RuntimeError("AssemblyAI returned an empty streaming token.")
    print("AssemblyAI streaming token request succeeded.")


async def verify_rime() -> None:
    client = RimeStreamingTTSClient()
    chunks_received = 0
    try:
        async for chunk in client.stream_audio_chunks("Miles provider smoke check."):
            if chunk:
                chunks_received += 1
            if chunks_received >= 2:
                break
    finally:
        await client.close()

    if not chunks_received:
        raise RuntimeError("Rime returned no audio chunks.")
    print(f"Rime returned {chunks_received} audio chunk(s).")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="allow requests to AssemblyAI and Rime (may use provider quota)",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("provider checks make live requests; pass --live to continue")

    missing = [
        name
        for name, value in (
            ("ASSEMBLYAI_API_KEY", config.assemblyai_api_key),
            ("RIME_API_KEY", config.rime_api_key),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Configure the required provider keys first: {', '.join(missing)}")

    await verify_assemblyai()
    await verify_rime()


if __name__ == "__main__":
    asyncio.run(main())
