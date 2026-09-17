import pytest
from src.debate.interviewer_panel import (
    PANELS,
    InterviewerPanel,
    Panelist,
    build_panel_system_prompt,
    get_interviewer_panel,
    parse_panel_turn,
)
from src.debate.engine import DebateEngine


def test_panels_exist():
    assert "vc_pitch" in PANELS
    assert "salary_negotiation" in PANELS
    assert "hostile_cross_exam" in PANELS
    assert "senior_interview" in PANELS

    vc_panel = PANELS["vc_pitch"]
    assert len(vc_panel.panelists) == 2
    assert vc_panel.panelists[0].name == "Marcus Vance"
    assert vc_panel.panelists[0].speaker == "bancroft"
    assert vc_panel.panelists[1].name == "Elena Frost"
    assert vc_panel.panelists[1].speaker == "astra"


def test_build_panel_prompt():
    panel = get_interviewer_panel("vc_pitch")
    prompt = build_panel_system_prompt(panel, pressure_level=4)
    assert "Marcus Vance" in prompt
    assert "Elena Frost" in prompt
    assert "2-ON-1 ADVERSARIAL MODE" in prompt
    assert "bancroft" in prompt
    assert "astra" in prompt


def test_parse_panel_turn():
    panel = get_interviewer_panel("vc_pitch")

    # Format 1: Bracketed [Marcus Vance]: ...
    raw = "[Marcus Vance]: Cut the fluff. What is your actual CAC payback?"
    panelist, clean = parse_panel_turn(raw, panel)
    assert panelist.name == "Marcus Vance"
    assert panelist.speaker == "bancroft"
    assert clean == "Cut the fluff. What is your actual CAC payback?"

    # Format 2: Elena Frost: ...
    raw2 = "Elena Frost: Wait. Marcus asked about payback, but what about churn?"
    panelist2, clean2 = parse_panel_turn(raw2, panel)
    assert panelist2.name == "Elena Frost"
    assert panelist2.speaker == "astra"
    assert clean2 == "Wait. Marcus asked about payback, but what about churn?"

    # Fallback to opening panelist when no name prefix
    raw3 = "Give me the numbers right now."
    panelist3, clean3 = parse_panel_turn(raw3, panel)
    assert panelist3.name == "Marcus Vance"
    assert clean3 == "Give me the numbers right now."


def test_debate_engine_panel_mode():
    engine = DebateEngine(scenario_id="vc_pitch", is_panel_mode=True)
    assert engine.is_panel_mode is True
    assert engine.panel is not None
    assert engine.current_speaker_name == "Marcus Vance"
    assert engine.current_speaker_voice == "bancroft"

    opening = engine.start_debate()
    assert opening == engine.panel.opening_statement

    debrief = engine.get_debrief_report()
    assert debrief["is_panel_mode"] is True
    assert debrief["panel"] is not None
    assert debrief["panel"]["id"] == "vc_partnership"


def test_panel_prompt_survives_pressure_update():
    engine = DebateEngine(scenario_id="vc_pitch", is_panel_mode=True)
    assert "2-ON-1 ADVERSARIAL MODE" in engine.persona.system_prompt

    engine.record_user_turn("We hit one million in revenue with fifty enterprise customers.", duration_sec=5.0)

    assert engine.is_panel_mode is True
    assert engine.panel is not None
    assert "2-ON-1 ADVERSARIAL MODE" in engine.persona.system_prompt
    assert "Marcus Vance" in engine.persona.system_prompt
    assert "Elena Frost" in engine.persona.system_prompt
