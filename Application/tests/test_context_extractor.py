import pytest
from src.context.extractor import extract_text_from_bytes, _clean_extracted_text


def test_clean_extracted_text():
    raw = "  Hello   world! \r\n\r\n\n\n  New line here.  "
    cleaned = _clean_extracted_text(raw)
    assert "Hello world!" in cleaned
    assert "New line here." in cleaned
    assert "\r" not in cleaned


def test_extract_text_from_txt():
    sample_txt = b"Startup Pitch Deck: AI Analytics\nCustomer Acquisition Cost: $45\nAnnual Recurring Revenue: $1.2M\n"
    res = extract_text_from_bytes(sample_txt, "deck.txt")
    assert res["format"] == "txt"
    assert "Customer Acquisition Cost: $45" in res["text"]
    assert res["word_count"] > 5
    assert res["page_count"] == 1


def test_extract_text_from_csv():
    csv_bytes = b"Metric,Value,Period\nCAC,$45,Q3 2024\nLTV,$2400,Q3 2024\nGross Margin,82%,Q3 2024\n"
    res = extract_text_from_bytes(csv_bytes, "financials.csv")
    assert res["format"] == "csv"
    assert "CAC | $45 | Q3 2024" in res["text"]
    assert "Gross Margin" in res["text"]


def test_extract_text_from_md():
    md_bytes = b"# Candidate Resume\n## Experience\n- Staff Architect at Tier-1 Infra Corp\n- Reduced latency by 42% across 15 distributed nodes.\n"
    res = extract_text_from_bytes(md_bytes, "resume.md")
    assert res["format"] == "md"
    assert "Staff Architect" in res["text"]
    assert "42%" in res["text"]


def test_extract_empty_or_corrupted():
    res = extract_text_from_bytes(b"", "empty.txt")
    assert res["text"] == ""
    assert res["word_count"] == 0
