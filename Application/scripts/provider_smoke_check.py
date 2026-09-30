"""Optional smoke check that makes live requests to configured speech providers."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from src.config import config
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.rime_stream import RimeStreamingTTSClient
from src.debate.llm_client import LLMClient


async def verify_assemblyai() -> None:
    client = AssemblyAIStreamingClient(api_key=config.assemblyai_api_key)
    try:
        if not await asyncio.wait_for(client.connect(), timeout=20):
            raise RuntimeError("AssemblyAI did not begin a streaming session.")
        print("AssemblyAI streaming session began successfully.")
    finally:
        await client.stop()


async def verify_rime() -> None:
    client = RimeStreamingTTSClient()
    chunks_received = 0
    try:
        async with contextlib.aclosing(client.stream_audio_chunks("Miles provider smoke check.")) as stream:
            async for chunk in stream:
                if chunk and any(chunk):
                    chunks_received += 1
                if chunks_received >= 2:
                    break
    finally:
        await client.close()

    if not chunks_received:
        raise RuntimeError("Rime returned no audio chunks.")
    print(f"Rime returned {chunks_received} audio chunk(s).")


async def verify_llm() -> None:
    client = LLMClient()
    try:
        if client.provider == "mock":
            raise RuntimeError("No live conversation provider is configured.")
        response = await asyncio.wait_for(client.generate_turn(
            [{"role": "user", "content": "Our company sells accounting software. Ask one investor question."}],
            "You are a skeptical investor. Ask one short question.", max_tokens=45,
        ), timeout=25)
        if not response:
            raise RuntimeError("The conversation provider returned no text.")
        print("Live conversation provider returned a response.")
    finally:
        await client.close()


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

    failed = False
    for name, check in (("AssemblyAI", verify_assemblyai), ("Rime", verify_rime), ("Conversation", verify_llm)):
        try:
            await asyncio.wait_for(check(), timeout=35)
        except Exception as error:
            print(f"{name} check failed ({type(error).__name__}). No credentials or provider response bodies are printed.")
            failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
