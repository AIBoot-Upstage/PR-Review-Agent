from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from backend.app.core.routing import extract_features, select_route
from backend.app.core.schemas import ReviewRequest
from backend.app.services.policy_harness import PolicyHarness
from backend.app.services.rag import LocalPolicyIndex

DEFAULT_FIXTURES = Path("review_harness/evaluation/policy-selection-fixtures.json")


def evaluate_harness(
    fixtures_path: Path = DEFAULT_FIXTURES,
    harness_root: Path = Path("review_harness"),
    policy_root: Path = Path("policies"),
) -> dict[str, Any]:
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    harness = PolicyHarness(harness_root)
    policy_index = LocalPolicyIndex(policy_root)
    all_policy_chars = sum(len(chunk.content) for chunk in policy_index.load_chunks())
    skill_hits = 0
    skill_expected = 0
    skill_allowed_hits = 0
    skill_labeled_selected = 0
    card_hits = 0
    card_expected = 0
    card_allowed_hits = 0
    card_labeled_selected = 0
    policy_hits = 0
    policy_expected = 0
    policy_selected = 0
    legacy_policy_hits = 0
    legacy_policy_selected = 0
    selected_policy_chars = 0
    legacy_policy_chars = 0
    cases: list[dict[str, Any]] = []

    for fixture in fixtures:
        request = ReviewRequest.from_dict(fixture["request"])
        features = extract_features(request, policy_available=policy_index.has_policy())
        route = select_route(features, request.review_mode)
        context = harness.select(request, route)
        policies = (
            policy_index.search(
                request,
                top_k=harness.max_policies_per_batch,
                policy_types=set(context.policy_types) or None,
            )
            if route.use_rag
            else []
        )
        legacy_policies = policy_index.search(request, top_k=3) if route.use_rag else []
        selected_skills = {skill.skill_id for skill in context.skills}
        selected_cards = {card.card_id for card in context.knowledge_cards}
        selected_policy_types = {policy.policy_type for policy in policies}
        legacy_policy_types = {policy.policy_type for policy in legacy_policies}
        expected_skills = set(fixture.get("expected_skills", []))
        allowed_skills = set(fixture.get("allowed_skills", expected_skills))
        expected_cards = set(fixture.get("expected_cards", []))
        allowed_cards = set(fixture.get("allowed_cards", expected_cards))
        expected_policy_types = set(fixture.get("expected_policy_types", []))
        skill_hits += len(selected_skills & expected_skills)
        skill_expected += len(expected_skills)
        skill_allowed_hits += len(selected_skills & allowed_skills)
        skill_labeled_selected += len(selected_skills)
        card_hits += len(selected_cards & expected_cards)
        card_expected += len(expected_cards)
        if allowed_cards:
            card_allowed_hits += len(selected_cards & allowed_cards)
            card_labeled_selected += len(selected_cards)
        policy_hits += len(selected_policy_types & expected_policy_types)
        policy_expected += len(expected_policy_types)
        policy_selected += len(selected_policy_types)
        legacy_policy_hits += len(legacy_policy_types & expected_policy_types)
        legacy_policy_selected += len(legacy_policy_types)
        selected_policy_chars += sum(len(policy.content) for policy in policies)
        legacy_policy_chars += sum(len(policy.content) for policy in legacy_policies)
        cases.append(
            {
                "id": fixture["id"],
                "route": route.name,
                "skills": sorted(selected_skills),
                "knowledge_cards": sorted(selected_cards),
                "policy_types": sorted(selected_policy_types),
            }
        )

    baseline_policy_chars = all_policy_chars * len(fixtures)
    used_source_ids = set(harness.design_source_ids)
    used_source_ids.update(
        str(source_id)
        for item in harness.manifest["skills"]
        for source_id in item.get("source_ids", [])
    )
    used_source_ids.update(
        str(source_id)
        for card in harness.knowledge_cards
        for source_id in card.get("source_ids", [])
    )
    return {
        "fixture_count": len(fixtures),
        "skill_recall": round(skill_hits / skill_expected, 4) if skill_expected else 1.0,
        "skill_precision": (
            round(skill_allowed_hits / skill_labeled_selected, 4)
            if skill_labeled_selected
            else 1.0
        ),
        "knowledge_card_recall": (
            round(card_hits / card_expected, 4) if card_expected else 1.0
        ),
        "knowledge_card_precision": (
            round(card_allowed_hits / card_labeled_selected, 4)
            if card_labeled_selected
            else 1.0
        ),
        "source_count": len(harness.source_ids),
        "source_utilization_rate": round(
            len(used_source_ids & harness.source_ids) / max(len(harness.source_ids), 1),
            4,
        ),
        "knowledge_card_count": len(harness.knowledge_cards),
        "source_backed_card_rate": round(
            sum(
                bool(card.get("source_ids"))
                and set(str(value) for value in card.get("source_ids", []))
                <= harness.source_ids
                for card in harness.knowledge_cards
            )
            / max(len(harness.knowledge_cards), 1),
            4,
        ),
        "policy_type_recall": round(policy_hits / policy_expected, 4) if policy_expected else 1.0,
        "policy_type_precision": round(policy_hits / policy_selected, 4) if policy_selected else 1.0,
        "legacy_top3_policy_type_precision": (
            round(legacy_policy_hits / legacy_policy_selected, 4)
            if legacy_policy_selected
            else 1.0
        ),
        "selected_policy_chars": selected_policy_chars,
        "legacy_top3_policy_chars": legacy_policy_chars,
        "vs_legacy_context_reduction": (
            round(1 - (selected_policy_chars / legacy_policy_chars), 4)
            if legacy_policy_chars
            else 0.0
        ),
        "all_policy_chars_baseline": baseline_policy_chars,
        "policy_context_reduction": (
            round(1 - (selected_policy_chars / baseline_policy_chars), 4)
            if baseline_policy_chars
            else 0.0
        ),
        "cases": cases,
    }


def main() -> int:
    fixtures_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FIXTURES
    result = evaluate_harness(fixtures_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if (
        result["skill_recall"] < 1.0
        or result["skill_precision"] < 1.0
        or result["knowledge_card_recall"] < 1.0
        or result["knowledge_card_precision"] < 1.0
        or result["source_backed_card_rate"] < 1.0
        or result["source_utilization_rate"] < 1.0
        or result["policy_type_recall"] < 1.0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
