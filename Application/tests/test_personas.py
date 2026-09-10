import pytest
from src.debate.personas import (
    ANTI_SYCOPHANCY_CORE_RULES,
    build_custom_debate_persona,
    get_persona,
    infer_contrarian_thesis,
    list_scenarios,
    list_persona_tones,
    PERSONAS,
    PERSONA_TONES,
)


def test_standard_personas_exist():
    expected_scenarios = [
        "vc_pitch",
        "salary_negotiation",
        "hostile_cross_exam",
        "senior_interview",
        "sales_objections",
        "media_crisis",
        "hostile_boardroom",
    ]
    for scenario_id in expected_scenarios:
        persona = get_persona(scenario_id)
        assert persona.id == scenario_id
        assert len(persona.name) > 0
        assert len(persona.opening_statement) > 0
        assert len(persona.fluff_interjections) > 0
        # Strict anti-sycophancy assertions
        assert "ZERO SYCOPHANCY" in persona.system_prompt
        assert "NEVER polite" in persona.system_prompt
        assert "END WITH A TRAP" in persona.system_prompt
        assert "under 25 words" in persona.system_prompt


def test_persona_tone_modifiers():
    assert len(PERSONA_TONES) == 5
    tones = list_persona_tones()
    assert len(tones) == 5
    tone_ids = [t["id"] for t in tones]
    assert "calm_ruthless" in tone_ids
    assert "skeptical_vc" in tone_ids
    assert "courtroom_aggressive" in tone_ids
    assert "cold_negotiator" in tone_ids
    assert "smiling_assassin" in tone_ids

    # Test tone injection in prompt
    p_ruthless = get_persona("vc_pitch", persona_tone="calm_ruthless")
    assert "TONE DIRECTIVE (CALM RUTHLESS)" in p_ruthless.system_prompt
    assert p_ruthless.speaker == "alpine"

    p_assassin = get_persona("hostile_boardroom", persona_tone="smiling_assassin")
    assert "TONE DIRECTIVE (SMILING ASSASSIN)" in p_assassin.system_prompt
    assert p_assassin.speaker == "astra"


def test_custom_debate_persona():
    topic = "Remote work is better than office work"
    persona = build_custom_debate_persona(topic, pressure_level=4)
    assert persona.id == "custom_debate"
    assert "Remote work" in persona.system_prompt
    assert "ZERO SYCOPHANCY" in persona.system_prompt
    assert "Pressure Level: 4/5" in persona.system_prompt
    assert len(persona.opening_statement) > 0


def test_contrarian_thesis_inference():
    # User champions remote work -> AI attacks remote work
    thesis_remote_pro = infer_contrarian_thesis("Why remote work is best")
    assert "destroys" in thesis_remote_pro.lower() or "culture" in thesis_remote_pro.lower()

    # User attacks remote work -> AI defends remote work
    thesis_remote_anti = infer_contrarian_thesis("Remote work is bad and destroys companies")
    assert "sovereignty" in thesis_remote_anti.lower() or "productivity" in thesis_remote_anti.lower()

    # User attacks crypto -> AI defends crypto
    thesis_crypto_anti = infer_contrarian_thesis("Crypto is a useless scam")
    assert "debasement" in thesis_crypto_anti.lower() or "sovereign" in thesis_crypto_anti.lower()

    # Dynamic arbitrary topic
    thesis_arbitrary = infer_contrarian_thesis("Pineapples belong on pizza")
    assert len(thesis_arbitrary) > 10


def test_pressure_directive_scaling():
    p1 = get_persona("vc_pitch", pressure_level=1)
    p5 = get_persona("vc_pitch", pressure_level=5)
    assert "Pressure Level: 1/5" in p1.system_prompt
    assert "Pressure Level: 5/5" in p5.system_prompt
    assert "Skeptical" in p1.system_prompt or "Probing" in p1.system_prompt
    assert "ruthless" in p5.system_prompt.lower()


def test_list_scenarios():
    scenarios = list_scenarios()
    assert len(scenarios) == 8
    scenario_ids = [s["id"] for s in scenarios]
    assert "vc_pitch" in scenario_ids
    assert "salary_negotiation" in scenario_ids
    assert "hostile_cross_exam" in scenario_ids
    assert "senior_interview" in scenario_ids
    assert "sales_objections" in scenario_ids
    assert "media_crisis" in scenario_ids
    assert "hostile_boardroom" in scenario_ids
    assert "custom_debate" in scenario_ids


def test_custom_debate_persona_with_curly_braces():
    """Ensure topics containing curly braces do not cause KeyError or format crashes."""
    topic = "Testing {curly} braces and {eval} code syntax"
    persona = get_persona("custom_debate", topic=topic, pressure_level=4, persona_tone="skeptical_vc")
    assert persona.id == "custom_debate"
    assert "{curly}" in persona.system_prompt
    assert "TONE DIRECTIVE (SKEPTICAL VC)" in persona.system_prompt
    assert persona.speaker == "bancroft"


def test_fallback_dossier_empty_topic():
    from src.debate.dossier import generate_fallback_dossier
    dossier = generate_fallback_dossier("   ")
    assert dossier["scenario_id"] == "custom_debate"
    assert len(dossier["topic"]) > 0
    assert len(dossier["attack_vectors"]) == 5
    assert len(dossier["trap_questions"]) == 3


