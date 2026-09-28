from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from src.debate.engine import DebateEngine
from src.meeting.models import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return isinstance(identifier, str) and bool(identifier and SAFE_ID_REGEX.match(identifier))


class DebriefDispatcher:
    """Compiles, persists, and formats post-meeting debrief reports."""

    async def compile_and_save(
        self,
        session: MeetingSession,
        engine: DebateEngine,
    ) -> Dict[str, Any]:
        """Generate a report and attach it to the meeting session for durable save."""
        logger.info(f"[DebriefDispatcher] Generating debrief report for meeting {session.meeting_id}...")
        report = await engine.generate_llm_debrief_report()

        session.debrief_report = report
        session.status = MeetingStatus.COMPLETED

        return report

    def get_saved_debrief(self, meeting_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        """Load a meeting report through its owner-scoped persistent record."""
        if not is_safe_identifier(meeting_id):
            logger.warning("[DebriefDispatcher] Rejected unsafe meeting_id.")
            return None
        try:
            from src.meeting.store import get_meeting_store

            session = get_meeting_store().get_session(owner_id, meeting_id)
        except (TypeError, ValueError):
            return None
        return session.debrief_report if session else None

    def format_html_summary(self, session: MeetingSession) -> str:
        """Format a clean, responsive HTML summary for email delivery or quick view."""
        report = session.debrief_report or {}
        summary = report.get("executive_summary", "No summary available.")
        overall_score = report.get("overall_score")
        composure = report.get("composure_rating")
        persuasion = report.get("persuasion_rating")
        gt_audit = report.get("ground_truth_audit") or {}
        factual_score = gt_audit.get("factual_accuracy_score")

        def display_score(value, suffix=""):
            return f"{value}{suffix}" if isinstance(value, (int, float)) else "Not scored"

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0c0e14; color: #e2e8f0; padding: 24px; }}
    .card {{ background: #181b24; border: 1px solid #2d3748; border-radius: 12px; padding: 24px; max-width: 650px; margin: 0 auto; }}
    .header {{ border-bottom: 1px solid #2d3748; padding-bottom: 16px; margin-bottom: 20px; }}
    .score {{ font-size: 36px; font-weight: 800; color: #6366f1; }}
    .metrics {{ display: flex; gap: 16px; margin: 20px 0; }}
    .metric {{ background: #1f2430; padding: 12px 16px; border-radius: 8px; flex: 1; text-align: center; }}
    .metric-val {{ font-size: 20px; font-weight: 700; color: #38bdf8; }}
    .metric-lbl {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }}
    .summary {{ line-height: 1.6; color: #cbd5e1; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h2>Miles Sparring Debrief: Google Meet</h2>
      <p style="color: #94a3b8; font-size: 12px;">Meeting ID: {session.meeting_id} | Persona: {session.persona_id}</p>
    </div>
    <div style="text-align: center;">
      <div class="score">{display_score(overall_score, "/100")}</div>
      <div style="color: #94a3b8; font-size: 12px;">Overall Sparring Score</div>
    </div>
    <div class="metrics">
      <div class="metric"><div class="metric-val">{display_score(composure, "/100")}</div><div class="metric-lbl">Composure</div></div>
      <div class="metric"><div class="metric-val">{display_score(persuasion, "/100")}</div><div class="metric-lbl">Persuasion</div></div>
      <div class="metric"><div class="metric-val">{display_score(factual_score, "%")}</div><div class="metric-lbl">Factual Accuracy</div></div>
    </div>
    <div class="summary">
      <h4>Executive Assessment</h4>
      <p>{summary}</p>
    </div>
  </div>
</body>
</html>"""
        return html


_DEBRIEF_DISPATCHER: Optional[DebriefDispatcher] = None


def get_debrief_dispatcher() -> DebriefDispatcher:
    global _DEBRIEF_DISPATCHER
    if _DEBRIEF_DISPATCHER is None:
        _DEBRIEF_DISPATCHER = DebriefDispatcher()
    return _DEBRIEF_DISPATCHER
