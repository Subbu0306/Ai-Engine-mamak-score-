"""Intelligence validation: verifies LLM output draft meets strict rubric requirements."""

from typing import Dict, List, Set
from mamakscore.contracts import (
    AssessmentDraft,
    CriterionScore,
    ImprovementActionDraft,
    InvestorQuestion,
    RedFlag,
)
from mamakscore.errors import ErrorCode, ServiceError
from mamakscore.rubric import RubricDefinition


def validate_assessment_draft(
    draft: AssessmentDraft,
    rubric: RubricDefinition,
) -> AssessmentDraft:
    """Validates and normalizes an AssessmentDraft against institutional rubric constraints:
    - Guarantees all 9 rubric criteria are present without duplicates.
    - Enforces the verbatim grounding law: if evidence_quote is empty, clamps score to 0.
    - Enforces investor questions count between 5 and 10 with unique strings.
    - Enforces improvement actions target known criteria and ensure target_score > current_score.
    - Validates red flag criteria references.
    """
    rubric_ids: Set[str] = {c.id for c in rubric.criteria}
    score_map: Dict[str, int] = {}
    normalized_scores: List[CriterionScore] = []
    seen_ids: Set[str] = set()

    # 1. Normalize and validate Criterion Scores
    for item in draft.criterion_scores:
        cid = item.criterion_id
        if cid not in rubric_ids:
            continue
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        raw_quote = (item.evidence_quote or "").strip()
        score = item.score

        # Grounding Law: positive score requires non-empty evidence quote
        if score > 0 and not raw_quote:
            # If no quote was extracted from the deck, score cannot be positive
            score = 0
            quote = ""
            justification = (
                f"{item.justification.strip()} [Grounding Note: Score adjusted to 0 "
                f"due to absence of verbatim slide evidence.]"
            ).strip()
        else:
            quote = raw_quote
            justification = item.justification

        updated_item = item.model_copy(
            update={
                "score": score,
                "evidence_quote": quote,
                "justification": justification,
            }
        )
        normalized_scores.append(updated_item)
        score_map[cid] = score

    # Backfill any missing rubric criteria with score 0
    missing_ids = rubric_ids - set(score_map.keys())
    for missing_id in missing_ids:
        missing_crit = next((c for c in rubric.criteria if c.id == missing_id), None)
        crit_name = missing_crit.name if missing_crit else missing_id
        zero_score = CriterionScore(
            criterion_id=missing_id,
            score=0,
            justification=f"No slide evidence or quantitative data provided for {crit_name}.",
            evidence_quote="",
            source_file="deck.pdf",
            confidence="low",
        )
        normalized_scores.append(zero_score)
        score_map[missing_id] = 0

    # 2. Normalize and validate Investor Questions (5 to 10 unique questions)
    unique_questions: List[InvestorQuestion | str] = []
    seen_question_texts: Set[str] = set()

    for q in draft.investor_questions:
        q_text = q.question.strip() if hasattr(q, "question") else str(q).strip()
        if not q_text or q_text in seen_question_texts:
            continue
        seen_question_texts.add(q_text)

        # Sanitize criterion_ids if present on object
        if hasattr(q, "criterion_ids"):
            valid_cids = [cid for cid in q.criterion_ids if cid in rubric_ids]
            unique_questions.append(
                InvestorQuestion(
                    question=q_text,
                    criterion_ids=valid_cids,
                    reasoning=getattr(q, "reasoning", None),
                )
            )
        else:
            unique_questions.append(q_text)

    # Pad if fewer than 5 questions
    if len(unique_questions) < 5:
        fallback_questions = [
            "What are the direct customer acquisition costs across primary marketing channels?",
            "How does the venture plan to defend its unit margins against competitive entry?",
            "What key regulatory or operational milestones must be achieved over the next 12 months?",
            "What is the current monthly cash burn and runway under conservative assumptions?",
            "What technical or distribution partnerships are secured by binding agreements?",
        ]
        for fq in fallback_questions:
            if len(unique_questions) >= 5:
                break
            if fq not in seen_question_texts:
                seen_question_texts.add(fq)
                unique_questions.append(
                    InvestorQuestion(
                        question=fq,
                        criterion_ids=["business_model", "financials"],
                        reasoning="Standard institutional due diligence question.",
                    )
                )

    # Truncate if more than 10 questions
    normalized_questions = unique_questions[:10]

    # 3. Normalize and validate Improvement Actions
    normalized_actions: List[ImprovementActionDraft] = []
    for action in draft.improvement_actions:
        target_cid = action.criterion_id
        if target_cid not in rubric_ids:
            # Re-map unassigned or invalid criterion to a default key
            target_cid = "problem"

        curr_score = score_map.get(target_cid, 0)
        target_score = action.target_score

        # Rule 4: target_score must be strictly greater than current_score
        if target_score <= curr_score:
            target_score = min(10, curr_score + 2 if curr_score < 9 else 10)
            if target_score <= curr_score:
                # If already at 10, target remains 10 and current is capped
                target_score = 10

        normalized_actions.append(
            action.model_copy(
                update={
                    "criterion_id": target_cid,
                    "target_score": target_score,
                }
            )
        )

    # 4. Normalize and validate Red Flags
    normalized_red_flags: List[RedFlag] = []
    for flag in draft.red_flags:
        cid = getattr(flag, "criterion_id", None)
        if cid and cid not in rubric_ids:
            flag = flag.model_copy(update={"criterion_id": None})
        normalized_red_flags.append(flag)

    return draft.model_copy(
        update={
            "criterion_scores": normalized_scores,
            "investor_questions": normalized_questions,
            "improvement_actions": normalized_actions,
            "red_flags": normalized_red_flags,
        }
    )


__all__ = ["validate_assessment_draft"]