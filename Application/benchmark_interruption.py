from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.voice.interruption_manager import InterruptionManager
from src.voice.rime_stream import RimeStreamingTTSClient


async def run_barge_in_trial(trial_num: int) -> float:
    """Execute a single barge-in latency trial."""
    tts = RimeStreamingTTSClient()
    mgr = InterruptionManager(tts_client=tts)

    long_adversarial_salvo = (
        "Your customer acquisition cost has quadrupled over the past two quarters, "
        "and your churn rate indicates that your product has zero organic defensibility. "
        "Explain why an enterprise customer would not replace your software tomorrow."
    )

    # Begin streaming audio
    stream_task = asyncio.create_task(
        _consume_stream_with_playback_simulation(tts, mgr, long_adversarial_salvo)
    )

    # Allow stream to start and audio frames to begin flowing
    await asyncio.sleep(0.15)
    assert mgr.ai_is_speaking, "Expected AI to be actively speaking before interruption"

    # Measure exact barge-in cut-off and stream termination duration
    t_start = time.perf_counter()
    event = mgr.handle_user_speech_detected()
    t_cut = time.perf_counter()
    await stream_task
    t_task_end = time.perf_counter()

    software_cut_ms = (t_cut - t_start) * 1000.0
    task_termination_ms = (t_task_end - t_start) * 1000.0

    assert event is not None, "Expected barge-in event to be returned"
    assert not mgr.ai_is_speaking, "AI speaking state must be False immediately after barge-in"
    assert tts._is_cancelled, "TTS client must have cancellation flag set"

    print(
        f"  Trial {trial_num:02d}: Command Latency = {software_cut_ms:.3f} ms | "
        f"Task Exit = {task_termination_ms:.3f} ms | "
        f"Spoken heard: '{event['spoken_before_cut']}'"
    )
    return task_termination_ms


async def _consume_stream_with_playback_simulation(
    tts: RimeStreamingTTSClient,
    mgr: InterruptionManager,
    text: str,
):
    mgr.mark_ai_speaking(text)
    try:
        async for _ in tts.stream_audio_chunks(text):
            if tts._is_cancelled or tts._cancel_event.is_set():
                break
            try:
                await asyncio.wait_for(tts._cancel_event.wait(), timeout=0.015)
                break
            except asyncio.TimeoutError:
                pass
    finally:
        if mgr.ai_is_speaking and not tts._is_cancelled:
            mgr.mark_ai_finished()


async def main():
    print("=" * 70)
    print("MILES — FULL-DUPLEX BARGE-IN LATENCY BENCHMARK")
    print("DataForge Pathway x Rime Hackathon Verification Suite")
    print("=" * 70)
    print(f"Target Threshold: Sub-100.00 ms cut-off latency\n")

    trials = 10
    latencies = []

    for i in range(1, trials + 1):
        lat = await run_barge_in_trial(i)
        latencies.append(lat)
        await asyncio.sleep(0.05)

    avg_lat = sum(latencies) / len(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]

    print("\n" + "-" * 70)
    print("BENCHMARK RESULTS SUMMARY:")
    print(f"  Trials Conducted   : {trials}")
    print(f"  Average Latency    : {avg_lat:.3f} ms")
    print(f"  Min Latency        : {min_lat:.3f} ms")
    print(f"  Max Latency        : {max_lat:.3f} ms")
    print(f"  95th Percentile    : {p95_lat:.3f} ms")
    print("-" * 70)

    # Acceptance assertion
    assert avg_lat < 100.0, f"Benchmark FAILED: Average latency {avg_lat:.2f}ms exceeds 100ms limit!"
    print("\n[VERDICT: PASSED]")
    print("Barge-in cut-off operates well within the 100ms human conversational threshold.")
    print("Ready for submission evidence recording.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
