"""Opt-in live pipeline check using synthetic speech, never customer documents.

This verifies providers and report/PDF output. It does not verify browser audio,
Supabase sign-in, hosted persistence, or microphone-to-speaker interruption.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from src.config import config
from src.context.analyzer import analyze_context_document
from src.debate.engine import DebateEngine
from src.debate.pdf_generator import generate_executive_pdf
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.rime_stream import RimeStreamingTTSClient

ANSWERS = {
    "vc_pitch": "We sell accounting software to small businesses. We have forty paying customers and our monthly price is one hundred dollars.",
    "salary_negotiation": "I led the product launch and reduced support response time by twenty percent. I want compensation that reflects those results.",
    "hostile_cross_exam": "I saw the document on Tuesday. I did not write it and I cannot confirm who changed it before that date.",
    "senior_interview": "I would start with a single database and measure the bottlenecks. I would add replicas when read traffic requires them.",
    "sales_objections": "We should run a small pilot and measure the time your team spends on exceptions before you decide to switch tools.",
    "media_crisis": "We have confirmed the incident and restricted access. We are investigating the cause and will share verified updates tomorrow.",
    "hostile_boardroom": "The plan addresses our two largest cost drivers. We will review progress each month and change the plan if the assumptions fail.",
    "custom_debate": "Remote work can improve hiring access. I would measure delivery quality and retention before making it the default for every team.",
}


async def collect_audio(client, text, **kwargs):
    chunks = []
    async with contextlib.aclosing(client.stream_audio_chunks(text, **kwargs)) as stream:
        async for chunk in stream:
            chunks.append(chunk)
    pcm = b"".join(chunks)
    if len(pcm) < 128 or not any(pcm):
        raise RuntimeError("The live voice provider returned no audible PCM.")
    return pcm


async def check_scenario(scenario, answer, dossier=None, turns=1):
    engine = DebateEngine(scenario_id=scenario, difficulty="medium",
        topic="The merits of remote work" if scenario == "custom_debate" else None,
        context_dossier=dossier)
    # Request the speech provider's 16 kHz PCM output directly for the STT input.
    user_voice = RimeStreamingTTSClient(sample_rate=16000)
    opponent_voice = RimeStreamingTTSClient(speaker=engine.persona.speaker)
    spoken = []
    stt = AssemblyAIStreamingClient(api_key=config.assemblyai_api_key,
        on_final=lambda text, _: spoken.append(text))
    try:
        if engine.llm_client.provider == "mock":
            raise RuntimeError("A live model is required for this check.")
        opening = engine.start_debate()
        opening_audio = await collect_audio(opponent_voice, opening)
        response_audio_bytes = 0
        for turn in range(turns):
            if turn:
                # New recognition connection isolates the next synthetic answer.
                stt = AssemblyAIStreamingClient(api_key=config.assemblyai_api_key,
                    on_final=lambda text, _: spoken.append(text))
            previous_count = len(spoken)
            user_pcm = await collect_audio(user_voice, answer)
            if not await stt.connect():
                raise RuntimeError("Speech recognition did not begin.")
            for start in range(0, len(user_pcm), 3200):
                chunk = user_pcm[start:start + 3200]
                await stt.send_audio_chunk(chunk)
                await asyncio.sleep(len(chunk) / 32000)
            await stt.flush_final_turn(timeout=8)
            await stt.stop()
            if len(spoken) == previous_count:
                raise RuntimeError("Synthetic speech was not transcribed.")
            engine.record_user_turn(" ".join(spoken[previous_count:]), duration_sec=len(user_pcm) / 32000)
            response = " ".join([clause async for clause in engine.generate_adversary_clauses()])
            if not response:
                raise RuntimeError("The live adversary returned no response.")
            response_audio_bytes += len(await collect_audio(opponent_voice, response))
        report = await engine.generate_llm_debrief_report()
        if report["rounds_completed"] != turns or report["assessment_method"] != "ai":
            raise RuntimeError("The live model did not return a scored report.")
        if turns >= 3 and report["assessment_status"] != "complete":
            raise RuntimeError("A full round must produce a complete assessment.")
        pdf = generate_executive_pdf(report)
        if not pdf.startswith(b"%PDF"):
            raise RuntimeError("PDF output was invalid.")
        return {
            "scenario": scenario, "passed": True, "context": bool(dossier),
            "transcribed_turns": len(spoken), "opening_audio_bytes": len(opening_audio),
            "rounds_completed": turns, "response_audio_bytes": response_audio_bytes, "assessment_method": report["assessment_method"],
            "assessment_status": report["assessment_status"], "pdf_bytes": len(pdf),
        }
    finally:
        await stt.stop()
        await user_voice.close()
        await opponent_voice.close()
        await engine.llm_client.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="allow synthetic speech/model calls that use provider quota")
    parser.add_argument("--output", default="data/demo-flow-results.json")
    parser.add_argument("--scenario", choices=list(ANSWERS), help="check one scenario instead of all eight plus context")
    parser.add_argument("--turns", type=int, choices=range(1, 6), default=1)
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to authorize provider calls.")
    # Do not print provider bodies, URLs containing tokens, or synthetic transcripts.
    logging.disable(logging.CRITICAL)
    results = []
    for scenario, answer in ANSWERS.items():
        if args.scenario and scenario != args.scenario:
            continue
        try:
            result = await asyncio.wait_for(check_scenario(scenario, answer, turns=args.turns), timeout=100 * args.turns)
        except Exception as error:
            result = {"scenario": scenario, "passed": False, "error_type": type(error).__name__}
        results.append(result)
        print(json.dumps(result), flush=True)
    if args.scenario:
        path = Path(args.output).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"verification_scope": "live providers with synthetic speech; browser/auth/deployment unverified", "results": results}, indent=2), encoding="utf-8")
        if any(not result["passed"] for result in results):
            raise SystemExit(1)
        return
    try:
        from src.debate.llm_client import LLMClient
        context_client = LLMClient()
        try:
            dossier = await analyze_context_document(
                "Synthetic demo company. Monthly price: $100. Paying customers: 40. Monthly revenue: $4000.",
                filename="synthetic-demo-notes.txt", llm_client=context_client)
        finally:
            await context_client.close()
        result = await asyncio.wait_for(check_scenario("vc_pitch", ANSWERS["vc_pitch"], dossier.to_dict()), timeout=100)
    except Exception as error:
        result = {"scenario": "vc_pitch", "context": True, "passed": False, "error_type": type(error).__name__}
    results.append(result)
    print(json.dumps(result), flush=True)
    path = Path(args.output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"verification_scope": "live providers with synthetic speech; browser/auth/deployment unverified", "results": results}, indent=2), encoding="utf-8")
    print(f"Results saved to {path}", flush=True)
    if any(not result["passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
