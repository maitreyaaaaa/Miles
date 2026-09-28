from src.debate.debrief_store import DebriefReportStore


def test_private_reports_persist_and_are_scoped_to_their_owner(tmp_path):
    owner_id = "00000000-0000-4000-8000-000000000001"
    other_owner_id = "00000000-0000-4000-8000-000000000002"
    report = {"session_id": "session-123", "overall_score": 87}
    store = DebriefReportStore(tmp_path)

    store.save_report(report, owner_id)

    reloaded = DebriefReportStore(tmp_path)
    assert reloaded.get_report("session-123", owner_id) == report
    assert reloaded.get_report("session-123", other_owner_id) is None
    assert reloaded.get_report("../session-123", owner_id) is None


def test_share_ids_are_server_generated_and_not_overwritten(tmp_path):
    store = DebriefReportStore(tmp_path)
    owner_id = "00000000-0000-4000-8000-000000000001"

    share_id = store.save_debrief({"overall_score": 87}, owner_id=owner_id)

    assert share_id.startswith("deb_")
    assert len(share_id) > 20
    assert store.get_debrief(share_id)["owner_id"] == owner_id
