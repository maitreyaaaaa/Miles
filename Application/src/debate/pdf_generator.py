from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)


def generate_executive_pdf(report: Dict[str, Any]) -> bytes:
    """Generate a pixel-perfect, agency-grade Executive Debrief PDF using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0a0a0a"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#71717a"),
        spaceAfter=12,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0a0a0a"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#27272a"),
    )
    bold_label = ParagraphStyle(
        "BoldLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0a0a0a"),
    )
    stat_val_style = ParagraphStyle(
        "StatVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#0a0a0a"),
        alignment=1,  # Center
    )
    stat_lbl_style = ParagraphStyle(
        "StatLbl",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#71717a"),
        alignment=1,  # Center
    )
    reframe_quote_style = ParagraphStyle(
        "ReframeQuote",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#71717a"),
    )
    reframe_winner_style = ParagraphStyle(
        "ReframeWinner",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0a0a0a"),
    )

    story = []

    # 1. Header Block
    scenario = (report.get("scenario") or "Debate").replace("_", " ").upper()
    topic = report.get("topic") or "Adversarial Sparring Session"
    session_id = report.get("session_id", "LIVE-SESSION")[:12]
    timestamp = datetime.now().strftime("%B %d, %Y • %H:%M UTC")

    story.append(Paragraph("MILES // EXECUTIVE DEBRIEF", title_style))
    story.append(Paragraph(f"<b>{scenario}</b>: {topic} &nbsp;|&nbsp; Session: <code>{session_id}</code> &nbsp;|&nbsp; {timestamp}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e4e4e7"), spaceAfter=10))

    # 2. Key Metrics Bar (Table with border boxes)
    metrics = report.get("metrics", {})
    composure = report.get("overall_score", metrics.get("composure_score", 100))
    wpm = metrics.get("current_wpm", 145)
    fillers = metrics.get("filler_word_count", 0)
    barge_ins = metrics.get("barge_ins", 0)
    turns = metrics.get("turns_count", report.get("rounds_completed", 1))

    metric_data = [
        [
            Paragraph(f"{composure}%", stat_val_style),
            Paragraph(f"{wpm} WPM", stat_val_style),
            Paragraph(f"{fillers}", stat_val_style),
            Paragraph(f"{barge_ins}", stat_val_style),
            Paragraph(f"{turns}", stat_val_style),
        ],
        [
            Paragraph("COMPOSURE", stat_lbl_style),
            Paragraph("CADENCE", stat_lbl_style),
            Paragraph("FILLER WORDS", stat_lbl_style),
            Paragraph("TACTICAL CUTS", stat_lbl_style),
            Paragraph("ROUNDS COMPLETED", stat_lbl_style),
        ],
    ]
    metric_table = Table(metric_data, colWidths=[108, 108, 108, 108, 108])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f4f5")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 12))

    # 3. Verdict & Executive Takeaway
    verdict = report.get("verdict", "SPARRING SESSION CONCLUDED")
    verdict_desc = report.get("verdict_description", "")
    story.append(Paragraph("EXECUTIVE VERDICT", section_heading))
    verdict_content = [
        [Paragraph(f"<b>Verdict:</b> {verdict}", bold_label)],
    ]
    if verdict_desc:
        verdict_content.append([Paragraph(verdict_desc, body_style)])

    verdict_table = Table(verdict_content, colWidths=[540])
    verdict_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(verdict_table)
    story.append(Spacer(1, 10))

    # 4. Math & Contradiction Traps Caught
    math_audit = report.get("math_audit", {})
    math_discrepancies = math_audit.get("discrepancies", [])
    if math_discrepancies:
        story.append(Paragraph("FORENSIC MATH & CONTRADICTION AUDIT", section_heading))
        math_table_rows = [
            [
                Paragraph("<b>Rule</b>", bold_label),
                Paragraph("<b>Discrepancy Details</b>", bold_label),
                Paragraph("<b>Lethal Trap</b>", bold_label),
            ]
        ]
        for m in math_discrepancies[:4]:
            math_table_rows.append([
                Paragraph(m.get("rule_type", "Math Mismatch").replace("_", " ").upper(), body_style),
                Paragraph(m.get("description", ""), body_style),
                Paragraph(f'"{m.get("lethal_salvo", "")}"', reframe_quote_style),
            ])
        m_table = Table(math_table_rows, colWidths=[110, 230, 200])
        m_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fee2e2")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fca5a5")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(m_table)
        story.append(Spacer(1, 10))

    # 5. Weakest Answer vs Executive Reframe
    weakest = report.get("weakest_answer")
    reframes = report.get("executive_reframes", [])
    if weakest or reframes:
        story.append(Paragraph("CRITICAL REFRAME: WHAT YOU SHOULD HAVE SAID", section_heading))
        orig = weakest.get("quote", "") if weakest else (reframes[0].get("original_quote", "") if reframes else "")
        why = weakest.get("why_faltered", "") if weakest else (reframes[0].get("rationale", "") if reframes else "")
        win = reframes[0].get("executive_reframe", "") if reframes else "Lead with verified numbers and anchor firmly."

        reframe_data = [
            [Paragraph("<b>Original Spoken Response:</b>", bold_label)],
            [Paragraph(f'"{orig}"', reframe_quote_style)],
            [Paragraph(f"<b>Why It Faltered:</b> {why}", body_style)],
            [Paragraph("<b>Winning Executive Reframe:</b>", bold_label)],
            [Paragraph(f'"{win}"', reframe_winner_style)],
        ]
        reframe_table = Table(reframe_data, colWidths=[540])
        reframe_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0a0a0a")),
            ("LINEBELOW", (0, 2), (-1, 2), 0.5, colors.HexColor("#e4e4e7")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(reframe_table)
        story.append(Spacer(1, 10))

    # 6. Strategic Coaching Recommendations
    coaching = report.get("coaching_tips", [])
    if coaching:
        story.append(Paragraph("STRATEGIC COACHING DIRECTIVES", section_heading))
        coach_rows = []
        for i, tip in enumerate(coaching[:4], 1):
            coach_rows.append([Paragraph(f"<b>{i}.</b> {tip}", body_style)])
        coach_table = Table(coach_rows, colWidths=[540])
        coach_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f4f5")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(coach_table)

    doc.build(story)
    return buffer.getvalue()
