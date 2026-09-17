from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.debate.engine import DebateEngine
from src.meeting.models import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "meetings"


import re

SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return bool(identifier and SAFE_ID_REGEX.match(identifier))


class DebriefDispatcher:
    """Compiles, persists, and formats post-meeting debrief reports."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def compile_and_save(
        self,
        session: MeetingSession,
        engine: DebateEngine,
    ) -> Dict[str, Any]:
        """Generate debrief report from debate engine, persist to disk, and update session."""
        logger.info(f"[DebriefDispatcher] Generating debrief report for meeting {session.meeting_id}...")
        report = await engine.generate_llm_debrief_report()

        session.debrief_report = report
        session.status = MeetingStatus.COMPLETED

        if not is_safe_identifier(session.meeting_id):
            logger.error(f"[DebriefDispatcher] Invalid meeting_id: {session.meeting_id}")
            return report

        # Persist report to data/meetings/{meeting_id}/debrief.json
        meeting_dir = (self.data_dir / session.meeting_id).resolve()
        if not meeting_dir.is_relative_to(self.data_dir.resolve()):
            logger.error("[DebriefDispatcher] Path traversal detected.")
            return report

        meeting_dir.mkdir(parents=True, exist_ok=True)
        report_file = meeting_dir / "debrief.json"

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            logger.info(f"[DebriefDispatcher] Debrief report saved to {report_file}")
        except Exception as e:
            logger.error(f"[DebriefDispatcher] Failed to write debrief report: {e}", exc_info=True)

        return report

    def get_saved_debrief(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve persisted debrief report for a given meeting safely."""
        if not is_safe_identifier(meeting_id):
            logger.warning(f"[DebriefDispatcher] Rejected unsafe meeting_id: {meeting_id}")
            return None

        meeting_dir = (self.data_dir / meeting_id).resolve()
        if not meeting_dir.is_relative_to(self.data_dir.resolve()):
            logger.warning(f"[DebriefDispatcher] Path traversal detected: {meeting_id}")
            return None

        report_file = meeting_dir / "debrief.json"
        if not report_file.exists():
            return None
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[DebriefDispatcher] Error reading debrief {meeting_id}: {e}")
            return None

    def format_html_summary(self, session: MeetingSession) -> str:
        """Format a clean, responsive HTML summary for email delivery or quick view."""
        report = session.debrief_report or {}
        summary = report.get("executive_summary", "No summary available.")
        overall_score = report.get("overall_score", 0)
        composure = report.get("composure_rating", 0)
        persuasion = report.get("persuasion_rating", 0)
        gt_audit = report.get("ground_truth_audit") or {}
        factual_score = gt_audit.get("factual_accuracy_score", 100)

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
      <div class="score">{overall_score}<span style="font-size: 18px; color: #94a3b8;">/100</span></div>
      <div style="color: #94a3b8; font-size: 12px;">Overall Sparring Score</div>
    </div>
    <div class="metrics">
      <div class="metric"><div class="metric-val">{composure}/100</div><div class="metric-lbl">Composure</div></div>
      <div class="metric"><div class="metric-val">{persuasion}/100</div><div class="metric-lbl">Persuasion</div></div>
      <div class="metric"><div class="metric-val">{factual_score}%</div><div class="metric-lbl">Factual Accuracy</div></div>
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
