import asyncio
import pytest
from src.context.analyzer import ContextDossier, NumericMetric
from src.context.store import get_context_store
from src.debate.llm_client import LLMClient
from src.meeting.meeting_engine import MeetingEngineCoordinator
from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus
from src.meeting.provider import MockMeetingBotProvider
from src.voice.rime_stream import RimeStreamingTTSClient


@pytest.mark.asyncio
async def test_meeting_engine_lifecycle_with_facts(tmp_path):
    # 1. Setup sample context dossier
    dossier = ContextDossier(
        context_id="ctx_acme_123",
        title="Acme Pitch Deck",
        filename="acme.pdf",
        doc_type="pitch_deck",
        executive_summary="Acme AI Series A pitch deck",
        target_role_or_company="Acme AI",
        core_claims=["Leading AI platform", "84% gross margins"],
        numeric_metrics=[
            NumericMetric(
                name="ARR",
                numeric_value=1200000.0,
                raw_value="$1.2M",
                unit="USD",
                category="financial",
                context="Annual Recurring Revenue reached $1.2M in Q4.",
            ),
            NumericMetric(
                name="CAC",
                numeric_value=45.0,
                raw_value="$45",
                unit="USD",
                category="financial",
                context="Blended customer acquisition cost is $45.",
            ),
        ],
        vulnerabilities=[{"metric": "churn", "note": "High enterprise churn"}],
        cross_exam_traps=["Why did CAC spike last quarter?"],
    )
    store = get_context_store()
    store.save_context(dossier)

    session = MeetingSession(
        meet_url="https://meet.google.com/test-meet-123",
        context_id=dossier.context_id,
        persona_id="vc_pitch",
        difficulty="hard",
        config=MeetingConfig(max_duration_seconds=600, audio_only=True),
    )

    mock_bot = MockMeetingBotProvider()
    tts_client = RimeStreamingTTSClient(api_key=None)  # Uses system/offline fallback
    coordinator = MeetingEngineCoordinator(
        session=session,
        bot_provider=mock_bot,
        tts_client=tts_client,
    )
    coordinator.engine.llm_client = LLMClient(provider="mock")

    # 2. Start meeting
    opening = await coordinator.start()
    assert opening is not None
    assert session.status == MeetingStatus.IN_CALL
    assert coordinator.channel is not None
    assert coordinator.channel.is_active()

    # 3. Simulate user turn citing accurate number
    await coordinator.handle_user_turn("Our ARR is at $1.2M right now.", confidence=0.98)
    audit = coordinator.engine.fact_auditor.get_audit_summary()
    assert audit["verified_count"] >= 1

    # 4. Simulate user turn bluffing/contradicting context
    await coordinator.handle_user_turn("Actually our CAC is around $300.", confidence=0.95)
    audit2 = coordinator.engine.fact_auditor.get_audit_summary()
    assert audit2["discrepancy_count"] >= 1

    # 5. Conclude meeting and verify debrief
    report = await coordinator.stop()
    assert report is not None
    assert session.status == MeetingStatus.COMPLETED
    assert "overall_score" in report
    assert "ground_truth_audit" in report
    gt = report["ground_truth_audit"]
    assert gt["total_audited_metrics"] >= 2
    assert len(gt["discrepancies"]) >= 1
