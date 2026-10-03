# Safe, deterministic and accessible HTML report rendering.
from collections.abc import Iterable
from html import escape

from .contracts import AssessmentResult


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _list(items: Iterable[object]) -> str:
    return (
        "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in items) + "</ul>"
        if items
        else "<p>None reported.</p>"
    )


def render_report(result: AssessmentResult) -> str:
    rows = "".join(
        f"<tr><th scope='row'>{_e(s.criterion_id)}</th><td>{s.score}/10</td><td>{_e(s.justification)}</td><td><q>{_e(s.evidence_quote)}</q></td></tr>"
        for s in result.criterion_scores
    )
    metric_rows = "".join(
        f"<tr><th scope='row'>{_e(k)}</th><td>{_e(v.value) if v.value is not None else 'Unavailable'}</td><td>{_e(v.unavailable_reason or '')}</td></tr>"
        for k, v in result.financials.metrics.items()
    )
    flags = (
        "".join(
            f"<li><strong>{_e(f.severity)}</strong>: {_e(f.summary)}</li>" for f in result.red_flags
        )
        or "<li>None reported.</li>"
    )
    questions = _list([q.question for q in result.investor_questions])
    actions = (
        "".join(
            f"<li>{_e(a.action)} <strong>Maximum projected gain: +{_e(a.projected_gain)}</strong></li>"
            for a in result.improvement_plan
        )
        or "<li>None reported.</li>"
    )
    confidence = (
        "Not exposed"
        if result.mamak_confidence.value is None
        else _e(result.mamak_confidence.value)
    )
    return f"""<article class='mamak-report'><style>.mamak-report{{font:16px/1.5 system-ui;color:#17202a;background:#fff;max-width:70rem;margin:auto}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #566573;padding:.5rem;text-align:left;vertical-align:top}}.warning{{border:3px solid #8a4b00;padding:1rem;background:#fff4df}}@media print{{.mamak-report{{max-width:none}}}}</style><h1>MamakScore Assessment</h1><p><strong>Application:</strong> {_e(result.application_id)}</p><p><strong>MamakScore:</strong> {_e(result.mamak_score)}/100 — {_e(result.band.label)}</p><p><strong>Human review required:</strong> Yes</p><section class='warning'><h2>MamakConfidence warning</h2><p>PROVISIONAL — NOT CLIENT APPROVED. Value: {confidence}</p></section><section><h2>Category scores</h2><table><caption>Evidence-grounded category assessment</caption><thead><tr><th>Category</th><th>Score</th><th>Analysis</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table></section><section><h2>Financial metrics</h2><table><caption>Deterministic calculations</caption><thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead><tbody>{metric_rows}</tbody></table></section><section><h2>Red flags</h2><ul>{flags}</ul></section><section><h2>Investor questions</h2>{questions}</section><section><h2>Prioritised improvement plan</h2><ol>{actions}</ol></section><section><h2>Missing information</h2>{_list(result.missing_information)}</section><section><h2>Provenance</h2><p>Model {_e(result.provenance.model_id)}; rubric {_e(result.provenance.rubric_version)}; prompt {_e(result.provenance.prompt_version)}.</p></section></article>"""
