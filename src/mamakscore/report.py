"""Institutional HTML Due Diligence Report Generator for MamakScore."""

import html
from decimal import Decimal
from typing import Any
from mamakscore.contracts import AssessmentResult


def _sanitize(text: Any) -> str:
    """Escapes HTML entities safely."""
    if text is None:
        return ""
    return html.escape(str(text))


def render_report_html(result: AssessmentResult) -> str:
    """Renders a self-contained, publication-grade HTML report from an AssessmentResult."""
    app_id = _sanitize(result.application_id)
    score = (
        f"{result.mamak_score:.1f}"
        if isinstance(result.mamak_score, (int, float, Decimal))
        else str(result.mamak_score)
    )
    band_name = _sanitize(
        result.band.band_name
        if hasattr(result.band, "band_name")
        else str(result.band)
    )

    # Confidence calculation resolution
    conf_obj = getattr(result, "mamak_confidence", None)
    conf_score_val = (
        getattr(conf_obj, "score", None)
        if conf_obj and getattr(conf_obj, "score", None) is not None
        else getattr(result, "provisional_confidence", None)
    )
    conf_str = (
        f"{conf_score_val:.1f}%"
        if isinstance(conf_score_val, (int, float, Decimal))
        else "N/A"
    )

    # Determine band badge color
    band_lower = band_name.lower()
    if "strong" in band_lower or "leader" in band_lower:
        badge_style = "background: #10b981; color: #ffffff;"
    elif (
        "potential" in band_lower
        or "consideration" in band_lower
        or "validation" in band_lower
    ):
        badge_style = "background: #f59e0b; color: #ffffff;"
    else:
        badge_style = "background: #ef4444; color: #ffffff;"

    # 1. Criterion Scores Table
    criteria_rows = []
    for c in result.criterion_scores:
        c_id = _sanitize(c.criterion_id)
        c_score = f"{c.score}/10"
        c_just = _sanitize(c.justification)
        c_quote = (
            f'"{_sanitize(c.evidence_quote)}"'
            if c.evidence_quote
            else '<span style="color: #9ca3af; font-style: italic;">No evidence quoted</span>'
        )

        criteria_rows.append(
            f"<tr>\n"
            f'  <td style="font-weight: 600; text-transform: capitalize;">{c_id.replace("_", " ")}</td>\n'
            f'  <td style="text-align: center; font-weight: bold; font-size: 1.05rem;">{c_score}</td>\n'
            f'  <td style="font-size: 0.92rem; line-height: 1.4;">{c_just}</td>\n'
            f'  <td style="font-size: 0.88rem; background: #f8fafc; border-left: 2px solid #cbd5e1; font-family: monospace;">{c_quote}</td>\n'
            f"</tr>"
        )
    criteria_table_body = "\n".join(criteria_rows)

    # 2. Red Flags List with Trigger Telemetry
    red_flags_html = ""
    if result.red_flags:
        flag_items = []
        for rf in result.red_flags:
            sev = _sanitize(getattr(rf, "severity", "medium")).lower()
            if sev == "critical":
                badge = '<span style="background: #991b1b; color: #fee2e2; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">CRITICAL (-50%)</span>'
            elif sev == "high":
                badge = '<span style="background: #dc2626; color: #fef2f2; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">HIGH (-25%)</span>'
            elif sev == "medium":
                badge = '<span style="background: #d97706; color: #fffbeb; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">MEDIUM (-12%)</span>'
            else:
                badge = '<span style="background: #4b5563; color: #f3f4f6; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">LOW (-4%)</span>'

            summary = _sanitize(getattr(rf, "summary", getattr(rf, "flag", "")))
            trigger = _sanitize(getattr(rf, "trigger_mechanism", ""))
            trigger_html = (
                f'<div style="font-size: 0.82rem; color: #64748b; margin-top: 2px;">'
                f"<strong>Trigger / Rationale:</strong> {trigger}</div>"
                if trigger
                else ""
            )
            eq = (
                f'<div style="font-size: 0.82rem; color: #475569; font-family: monospace; margin-top: 4px; background: #fee2e2; padding: 4px 8px; border-radius: 4px;">'
                f'Quote: "{_sanitize(rf.evidence_quote)}"</div>'
                if getattr(rf, "evidence_quote", None)
                else ""
            )

            flag_items.append(
                f'<li style="margin-bottom: 12px; list-style-type: none; border-bottom: 1px solid #fecdd3; padding-bottom: 8px;">\n'
                f"  {badge} <strong style=\"color: #991b1b; font-size: 0.95rem;\">{summary}</strong>\n"
                f"  {trigger_html}\n"
                f"  {eq}\n"
                f"</li>"
            )
        red_flags_html = f"""
        <div style="margin-top: 28px; padding: 20px; background: #fff1f2; border: 1px solid #fecdd3; border-radius: 8px;">
            <h3 style="margin-top: 0; color: #9f1239; font-size: 1.15rem;">Identified Vulnerabilities &amp; Red Flags ({len(result.red_flags)})</h3>
            <ul style="padding-left: 0; margin-bottom: 0;">
                {''.join(flag_items)}
            </ul>
        </div>
        """

    # 3. Improvement Actions List
    actions_html = ""
    if result.improvement_actions:
        action_items = []
        for act in result.improvement_actions:
            act_text = _sanitize(act.action)
            crit = _sanitize(act.criterion_id)
            target = getattr(act, "target_score", "")
            action_items.append(
                f'<li style="margin-bottom: 8px;">\n'
                f'  <strong>{crit.replace("_", " ").capitalize()} (Target: {target}/10):</strong> {act_text}\n'
                f"</li>"
            )
        actions_html = f"""
        <div style="margin-top: 24px; padding: 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px;">
            <h3 style="margin-top: 0; color: #166534;">Strategic Diligence Improvement Actions</h3>
            <ul style="padding-left: 20px; margin-bottom: 0;">
                {''.join(action_items)}
            </ul>
        </div>
        """

    # 4. Critical Information Deficits
    missing_html = ""
    if result.missing_information:
        missing_items = [f"<li>{_sanitize(m)}</li>" for m in result.missing_information]
        missing_html = f"""
        <div style="margin-top: 24px; padding: 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;">
            <h3 style="margin-top: 0; color: #334155;">Critical Information Deficits</h3>
            <ul style="padding-left: 20px; margin-bottom: 0;">
                {''.join(missing_items)}
            </ul>
        </div>
        """

    # Complete HTML Document (all internal CSS braces double-escaped)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MamakScore Due Diligence Report - {app_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f1f5f9;
            color: #0f172a;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: #ffffff;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 24px;
            margin-bottom: 32px;
        }}
        .score-card {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 32px;
            text-align: center;
        }}
        .score-val {{
            font-size: 2.2rem;
            font-weight: 800;
            margin: 4px 0;
            color: #1e293b;
        }}
        .score-lbl {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #64748b;
            font-weight: 600;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}
        th, td {{
            padding: 12px 14px;
            border: 1px solid #e2e8f0;
            text-align: left;
        }}
        th {{
            background: #f8fafc;
            font-size: 0.85rem;
            text-transform: uppercase;
            color: #475569;
            letter-spacing: 0.05em;
        }}
        .disclaimer {{
            margin-top: 48px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            font-size: 0.78rem;
            color: #94a3b8;
            line-height: 1.5;
            text-align: justify;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1 style="margin: 0; font-size: 1.8rem;">Institutional Venture Assessment</h1>
                <p style="margin: 6px 0 0 0; color: #64748b;">Target Submission: <strong>{app_id}</strong></p>
            </div>
            <div>
                <span style="display: inline-block; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 0.95rem; {badge_style}">
                    {band_name}
                </span>
            </div>
        </div>

        <div class="score-card">
            <div>
                <div class="score-lbl">MamakScore</div>
                <div class="score-val">{score}</div>
                <div style="font-size: 0.8rem; color: #64748b;">Scale: 0.0 - 100.0 (Capped)</div>
            </div>
            <div>
                <div class="score-lbl">Confidence Calibration</div>
                <div class="score-val" style="color: #0284c7;">{conf_str}</div>
                <div style="font-size: 0.8rem; color: #64748b;">Completeness &amp; Grounding</div>
            </div>
            <div>
                <div class="score-lbl">Review Escalation</div>
                <div class="score-val" style="font-size: 1.3rem; margin-top: 14px; color: #dc2626;">
                    {'MANDATORY' if getattr(result.band, 'human_review_required', True) else 'ROUTINE'}
                </div>
                <div style="font-size: 0.8rem; color: #64748b;">Institutional Safeguard</div>
            </div>
        </div>

        <h2>Rubric Evaluation &amp; Verbatim Grounding</h2>
        <table>
            <thead>
                <tr>
                    <th style="width: 18%;">Criterion</th>
                    <th style="width: 10%; text-align: center;">Score</th>
                    <th style="width: 36%;">Evaluation &amp; Justification</th>
                    <th style="width: 36%;">Extracted Verbatim Quote</th>
                </tr>
            </thead>
            <tbody>
                {criteria_table_body}
            </tbody>
        </table>

        {red_flags_html}
        {actions_html}
        {missing_html}

        <div class="disclaimer">
            <strong>Institutional Diligence Disclaimer:</strong> This document represents an automated algorithmic assessment generated by the MamakScore Due Diligence Intelligence Engine. All scores and confidence ratings are derived through deterministic rubric weightings based on extracted submission content and optional financial models. This report does not constitute formal investment advice, fiduciary endorsement, or financial product recommendation. Venture investment carries significant risk of capital loss. Formal independent verification of all cited customer, team, and financial metrics by human analysts is strictly required prior to capital commitment.
        </div>
    </div>
</body>
</html>
"""


# Function aliases supporting pipeline and test imports
render_report = render_report_html
generate_html_report = render_report_html
render_html = render_report_html
build_html_report = render_report_html

__all__ = [
    "render_report_html",
    "render_report",
    "generate_html_report",
    "render_html",
    "build_html_report",
]