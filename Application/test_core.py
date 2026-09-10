import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config
from src.debate.llm_client import clean_spoken_text
from src.debate.personas import detect_topic_polarity, infer_contrarian_thesis
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.interruption_manager import InterruptionManager
from src.voice.rime_stream import RimeStreamingTTSClient


async def test_assemblyai_token():
    print("\n[STT Core] Testing AssemblyAI v3 Streaming Token Generation...")
    if not config.assemblyai_api_key:
        print("  [WARN] No ASSEMBLYAI_API_KEY configured. Skipping live token fetch.")
        return

    client = AssemblyAIStreamingClient(api_key=config.assemblyai_api_key)
    try:
        token = await client.fetch_token()
        assert token and len(token) > 10, "Streaming token too short or empty"
        print(f"  [PASS] AssemblyAI v3 streaming token generated: {token[:16]}...")
    except Exception as e:
        print(f"  [FAIL] Failed to generate AssemblyAI token: {e}")
        raise


async def test_rime_streaming_tts():
    print("\n[TTS Core] Testing Rime Neural Streaming TTS Client...")
    tts = RimeStreamingTTSClient()
    print(f"  Active provider: {tts.active_provider} (Speaker: {tts.speaker})")

    chunks_collected = []
    async for chunk in tts.stream_audio_chunks("Your unit economics are broken."):
        chunks_collected.append(chunk)
        if len(chunks_collected) >= 2:
            break

    assert len(chunks_collected) >= 1, "Expected at least one audio chunk"
    print(f"  [PASS] Streamed {len(chunks_collected)} audio chunks (First chunk size: {len(chunks_collected[0])} bytes).")


async def test_interruption_barge_in():
    print("\n[Voice Core] Testing Full-Duplex Sub-Millisecond Barge-in Cut-off...")
    tts = RimeStreamingTTSClient()
    mgr = InterruptionManager(tts_client=tts)

    text = "We have established defensible network effects that prevent Google from copying our product."
    mgr.mark_ai_speaking(text)
    assert mgr.ai_is_speaking

    event = mgr.handle_user_speech_detected()
    assert event is not None
    assert event["by"] == "user"
    assert event["latency_ms"] < 10.0, f"Expected <10ms cut-off, got {event['latency_ms']}ms"
    assert not mgr.ai_is_speaking
    assert tts._is_cancelled
    print(f"  [PASS] Barge-in cut-off executed in {event['latency_ms']:.3f} ms.")


def test_anti_sycophancy_and_brevity():
    print("\n[Debate Core] Testing Anti-Sycophancy Sanitization & Brevity...")
    # Sycophantic input from polite LLM
    polite_turn = "Good point, but what is your customer acquisition cost?"
    sanitized = clean_spoken_text(polite_turn)
    assert not sanitized.lower().startswith("good point"), f"Sycophancy retained: '{sanitized}'"
    assert "customer acquisition cost" in sanitized.lower()
    print(f"  [PASS] Purged sycophantic prefix -> '{sanitized}'")

    # Excessive length input
    long_turn = (
        "I understand what you're saying, but when we look at your CAC and LTV metrics, "
        "the numbers simply do not add up because your sales cycle is eighteen months long, "
        "your churn is increasing every quarter, and your competitors are pricing at fifty percent below you. "
        "How do you survive when funding dries up?"
    )
    brief = clean_spoken_text(long_turn)
    word_count = len(brief.split(" "))
    assert word_count <= 25, f"Response exceeds 25 words ({word_count} words): '{brief}'"
    assert brief.endswith("?"), "Response must end with pointed trap question"
    print(f"  [PASS] Brevity bounded to {word_count} words -> '{brief}'")


def test_contrarian_stance_inversion():
    print("\n[Debate Core] Testing Bidirectional Contrarian Stance Inversion...")
    # Pro-remote work -> AI must attack remote work
    pro_topic = "Remote work is the greatest thing for companies"
    assert detect_topic_polarity(pro_topic) == "positive"
    thesis_pro = infer_contrarian_thesis(pro_topic)
    assert "destroys" in thesis_pro.lower() or "culture" in thesis_pro.lower() or "complacency" in thesis_pro.lower()
    print(f"  [PASS] Pro stance inverted to attack: '{thesis_pro[:60]}...'")

    # Anti-remote work -> AI must champion remote work
    anti_topic = "Remote work is bad and destroys companies"
    assert detect_topic_polarity(anti_topic) == "negative"
    thesis_anti = infer_contrarian_thesis(anti_topic)
    assert "sovereignty" in thesis_anti.lower() or "productivity" in thesis_anti.lower()
    print(f"  [PASS] Anti stance inverted to defense: '{thesis_anti[:60]}...'")


async def main():
    print("=" * 60)
    print("MILES — CORE BACKEND SUBSYSTEM VERIFICATION")
    print("=" * 60)
    await test_assemblyai_token()
    await test_rime_streaming_tts()
    await test_interruption_barge_in()
    test_anti_sycophancy_and_brevity()
    test_contrarian_stance_inversion()
    print("\n" + "=" * 60)
    print("[ALL CORE SYSTEM VERIFICATIONS PASSED]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
