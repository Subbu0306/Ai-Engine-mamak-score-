"""HTML assessment report renderer with accessibility and security escaping."""

import html
from typing import Any, List


def _get_text(val: Any) -> str:
    if hasattr(val, "question"):
        return str(val.question)
    if hasattr(val, "summary"):
        return str(val.summary)
    if isinstance(val, dict):
        return str(val.get("question") or val.get("summary") or val)
    return str(val)


def render_report(result: Any) -> str:
    """Renders a self-contained, accessible, script-escaped HTML report."""
    app_id = html.escape(str(getattr(result, "application_id", "")))

    # Format score and confidence
    score_val = getattr(result, "mamak_score", "0.0")
    score_str = f"{float(score_val):.1f}"

    band_obj = getattr(result, "band", "Not ready")
    band_label = band_obj.label if hasattr(band_obj, "label") else str(band_obj)
    band_str = html.escape(band_label)

    conf_val = getattr(result, "provisional_confidence", None)
    conf_str = f"{conf_val:.1f}%" if conf_val is not None else "N/A"

    # 1. Criteria rows
    criteria_rows: List[str] = []
    for c in getattr(result, "criterion_scores", []):
        cid = html.escape(str(getattr(c, "criterion_id", "")))
        c_score = str(getattr(c, "score", 0))
        c_just = html.escape(str(getattr(c, "justification", "")))
        c_quote = html.escape(str(getattr(c, "evidence_quote", "")))
        criteria_rows.append(
            f"<tr><td><strong>{cid}</strong></td><td>{c_score}</td><td>{c_just}</td><td><em>{c_quote}</em></td></tr>"
        )
    criteria_table_body = "\n".join(criteria_rows)

    # 2. Red flags
    flag_items: List[str] = []
    for f in getattr(result, "red_flags", []):
        f_type = html.escape(str(getattr(f, "flag", getattr(f, "flag_type", "Flag"))))
        f_sum = html.escape(_get_text(getattr(f, "summary", "")))
        f_quote = html.escape(str(getattr(f, "evidence_quote", "")))
        flag_items.append(f"<li><strong>{f_type}</strong>: {f_sum} <em>{f_quote}</em></li>")
    flags_html = "\n".join(flag_items) or "<li>No red flags detected.</li>"

    # 3. Actions
    action_items: List[str] = []
    for a in getattr(result, "improvement_actions", []):
        cid = html.escape(str(getattr(a, "criterion_id", "")))
        act = html.escape(str(getattr(a, "action", "")))
        target = str(getattr(a, "target_score", ""))
        gain = f"{float(getattr(a, 'projected_gain', 0)):.1f}"
        action_items.append(
            f"<li><strong>{cid}</strong>: {act} (Target: {target}, Projected Gain: +{gain})</li>"
        )
    actions_html = "\n".join(action_items) or "<li>None recommended.</li>"

    # 4. Investor questions
    q_items: List[str] = []
    for q in getattr(result, "investor_questions", []):
        q_text = html.escape(_get_text(q))
        q_items.append(f"<li>{q_text}</li>")
    questions_html = "\n".join(q_items) or "<li>No specific questions generated.</li>"

    # 5. Missing information (ensures <script> tags are fully escaped into &lt;script&gt;)
    missing_items: List[str] = []
    for m in getattr(result, "missing_information", []):
        missing_items.append(f"<li>{html.escape(str(m))}</li>")
    missing_html = "\n".join(missing_items) or "<li>None reported.</li>"

    # Note: Exactly 1 <h1>, contains <h2>, <caption>, and the exact string "PROVISIONAL — NOT CLIENT APPROVED"
    # No external stylesheet links (no http:// or https://)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>MamakScore Assessment Report - {app_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; color: #111; }}
    h1, h2, h3 {{ color: #1e293b; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 0.75rem; text-align: left; }}
    th {{ background: #f8fafc; }}
    .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; background: #e2e8f0; font-weight: bold; }}
    .disclaimer {{ padding: 0.5rem 1rem; background: #fef3c7; color: #92400e; font-weight: bold; margin-bottom: 1rem; border-left: 4px solid #f59e0b; }}
  </style>
</head>
<body>
  <div class="disclaimer">PROVISIONAL — NOT CLIENT APPROVED</div>
  <header>
    <h1>MamakScore Due Diligence Report</h1>
    <p>Application ID: <code>{app_id}</code></p>
  </header>
  
  <section aria-labelledby="summary-heading">
    <h2 id="summary-heading">Assessment Summary</h2>
    <p>MamakScore: <strong>{score_str}</strong> / 100</p>
    <p>Band: <span class="badge">{band_str}</span></p>
    <p>Provisional Confidence: <strong>{conf_str}</strong></p>
  </section>

  <section aria-labelledby="criteria-heading">
    <h2 id="criteria-heading">Rubric Category Scores</h2>
    <table>
      <caption>Evaluation Criteria Breakdown</caption>
      <thead>
        <tr><th>Criterion</th><th>Score</th><th>Justification</th><th>Evidence Quote</th></tr>
      </thead>
      <tbody>
        {criteria_table_body}
      </tbody>
    </table>
  </section>

  <section aria-labelledby="flags-heading">
    <h2 id="flags-heading">Identified Red Flags</h2>
    <ul>
      {flags_html}
    </ul>
  </section>

  <section aria-labelledby="actions-heading">
    <h2 id="actions-heading">Recommended Improvement Actions</h2>
    <ul>
      {actions_html}
    </ul>
  </section>

  <section aria-labelledby="questions-heading">
    <h2 id="questions-heading">Investor Triage Questions</h2>
    <ul>
      {questions_html}
    </ul>
  </section>

  <section aria-labelledby="missing-heading">
    <h2 id="missing-heading">Missing Information</h2>
    <ul>
      {missing_html}
    </ul>
  </section>
</body>
</html>
"""


render_html_report = render_report
__all__ = ["render_report", "render_html_report"]