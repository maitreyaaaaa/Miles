from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MeetingStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONNECTING = "connecting"
    IN_CALL = "in_call"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MeetingConfig:
    max_duration_seconds: int = 1800  # 30 minutes max
    barge_in_sensitivity: float = 0.5
    participant_name: str = "Miles (Adversary)"
    auto_debrief: bool = True
    audio_only: bool = True  # Video camera explicitly off

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> MeetingConfig:
        if not data:
            return cls()
        return cls(
            max_duration_seconds=data.get("max_duration_seconds", 1800),
            barge_in_sensitivity=data.get("barge_in_sensitivity", 0.5),
            participant_name=data.get("participant_name", "Miles (Adversary)"),
            auto_debrief=data.get("auto_debrief", True),
            audio_only=data.get("audio_only", True),
        )


@dataclass
class MeetingSession:
    meeting_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: Optional[str] = None
    recall_bot_id: Optional[str] = None
    recall_status: Optional[str] = None
    recall_status_message: Optional[str] = None
    recall_status_updated_at: Optional[float] = None
    meet_url: str = ""
    context_id: Optional[str] = None
    context_filename: Optional[str] = None
    persona_id: str = "vc_pitch"
    difficulty: str = "hard"
    topic: Optional[str] = None
    persona_tone: Optional[str] = None
    status: MeetingStatus = MeetingStatus.SCHEDULED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    duration_seconds: float = 0.0
    config: MeetingConfig = field(default_factory=MeetingConfig)
    debrief_report: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    provider_mode: str = "mock"
    provider_notice: Optional[str] = "Local simulation channel; no external meeting bot is connected."

    def to_dict(self, *, include_owner: bool = False) -> Dict[str, Any]:
        data = {
            "meeting_id": self.meeting_id,
            "meet_url": self.meet_url,
            "context_id": self.context_id,
            "context_filename": self.context_filename,
            "persona_id": self.persona_id,
            "difficulty": self.difficulty,
            "topic": self.topic,
            "persona_tone": self.persona_tone,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "config": self.config.to_dict(),
            "has_debrief": self.debrief_report is not None,
            "debrief_report": self.debrief_report,
            "error_message": self.error_message,
            "provider_mode": self.provider_mode,
            "provider_notice": self.provider_notice,
            "recall_bot_id": self.recall_bot_id,
            "recall_status": self.recall_status,
            "recall_status_message": self.recall_status_message,
            "recall_status_updated_at": self.recall_status_updated_at,
        }
        if include_owner:
            data["owner_id"] = self.owner_id
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MeetingSession:
        cfg = MeetingConfig.from_dict(data.get("config"))
        status_val = data.get("status", MeetingStatus.SCHEDULED.value)
        try:
            status_enum = MeetingStatus(status_val)
        except ValueError:
            status_enum = MeetingStatus.SCHEDULED

        return cls(
            meeting_id=data.get("meeting_id", str(uuid.uuid4())),
            owner_id=data.get("owner_id"),
            recall_bot_id=data.get("recall_bot_id"),
            recall_status=data.get("recall_status"),
            recall_status_message=data.get("recall_status_message"),
            recall_status_updated_at=data.get("recall_status_updated_at"),
            meet_url=data.get("meet_url", ""),
            context_id=data.get("context_id"),
            context_filename=data.get("context_filename"),
            persona_id=data.get("persona_id", "vc_pitch"),
            difficulty=data.get("difficulty", "hard"),
            topic=data.get("topic"),
            persona_tone=data.get("persona_tone"),
            status=status_enum,
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            duration_seconds=data.get("duration_seconds", 0.0),
            config=cfg,
            debrief_report=data.get("debrief_report"),
            error_message=data.get("error_message"),
            provider_mode=data.get("provider_mode", "mock"),
            provider_notice=data.get("provider_notice", "Local simulation channel; no external meeting bot is connected."),
        )
