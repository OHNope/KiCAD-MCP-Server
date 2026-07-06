"""Routing quality rule catalog and scoring helpers.

The score is a penalty score: rules that are loaded and not satisfied add their
weight to the final score. A perfect route scores 0.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple


ALWAYS_LOADED_RULES: Tuple[Dict[str, Any], ...] = (
    {"id": "return_path_crossing_split", "score": 100, "load": "always"},
    {"id": "reference_plane_continuity", "score": 100, "load": "always"},
    {"id": "gnd_plane_not_fragmented", "score": 95, "load": "always"},
    {"id": "via_transition_has_return_path", "score": 88, "load": "always"},
    {"id": "aggressor_victim_parallel_coupling", "score": 92, "load": "always"},
    {"id": "board_edge_high_speed_emi", "score": 86, "load": "always"},
    {"id": "excessive_detour_for_critical_net", "score": 78, "load": "always"},
    {"id": "plane_cut_by_signal", "score": 92, "load": "always"},
)


DYNAMIC_RULES: Tuple[Dict[str, Any], ...] = (
    {"id": "decoupling_loop", "score": 100, "load": "dynamic"},
    {"id": "regulator_hot_loop", "score": 100, "load": "dynamic"},
    {"id": "sw_node_noise", "score": 98, "load": "dynamic"},
    {"id": "crystal_short_no_via", "score": 98, "load": "dynamic"},
    {"id": "differential_pair_together", "score": 96, "load": "dynamic"},
    {"id": "usb_diff_quality", "score": 95, "load": "dynamic"},
    {"id": "can_pair_stub_termination", "score": 84, "load": "dynamic"},
    {"id": "analog_away_from_noise", "score": 94, "load": "dynamic"},
    {"id": "reset_boot_away_from_noise", "score": 88, "load": "dynamic"},
    {"id": "esd_close_to_connector", "score": 96, "load": "dynamic"},
    {"id": "high_current_loop", "score": 95, "load": "dynamic"},
    {"id": "feedback_trace_quiet", "score": 95, "load": "dynamic"},
)


RULES_BY_ID: Dict[str, Dict[str, Any]] = {
    rule["id"]: rule for rule in (*ALWAYS_LOADED_RULES, *DYNAMIC_RULES)
}


def _normalise_rule_ids(values: Optional[Iterable[Any]]) -> List[str]:
    rule_ids: List[str] = []
    if not values:
        return rule_ids

    for value in values:
        if isinstance(value, str):
            rule_id = value
        elif isinstance(value, dict):
            rule_id = str(value.get("rule") or value.get("id") or "")
        else:
            rule_id = str(value)

        rule_id = rule_id.strip()
        if rule_id and rule_id not in rule_ids:
            rule_ids.append(rule_id)

    return rule_ids


def _normalise_rule_results(rule_results: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    if not isinstance(rule_results, dict):
        return {}

    normalised: Dict[str, bool] = {}
    for rule_id, passed in rule_results.items():
        if rule_id in RULES_BY_ID:
            normalised[rule_id] = bool(passed)
    return normalised


def _loaded_rule_ids(params: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    loaded = [rule["id"] for rule in ALWAYS_LOADED_RULES]
    unknown_dynamic = []

    if params.get("loadAllDynamicRules"):
        dynamic_ids = [rule["id"] for rule in DYNAMIC_RULES]
    else:
        dynamic_ids = _normalise_rule_ids(params.get("dynamicRules"))

    for rule_id in dynamic_ids:
        rule = RULES_BY_ID.get(rule_id)
        if not rule or rule["load"] != "dynamic":
            unknown_dynamic.append(rule_id)
            continue
        if rule_id not in loaded:
            loaded.append(rule_id)

    return loaded, unknown_dynamic


def loaded_rule_ids(params: Dict[str, Any]) -> List[str]:
    """Return the rule ids loaded by the given request parameters."""
    loaded, _unknown_dynamic = _loaded_rule_ids(params)
    return loaded


def evaluate_route_quality(params: Dict[str, Any]) -> Dict[str, Any]:
    """Score one route from explicit rule outcomes.

    Accepted outcome inputs:
    - ``failedRules`` / ``violations``: list of rule ids or objects with ``rule``/``id``.
    - ``passedRules``: list of rule ids.
    - ``ruleResults``: mapping of rule id to bool, where ``False`` means failed.
    """
    loaded_ids, unknown_dynamic = _loaded_rule_ids(params)
    loaded_set = set(loaded_ids)
    rule_results = _normalise_rule_results(params.get("ruleResults"))

    failed_ids = set(_normalise_rule_ids(params.get("failedRules") or params.get("violations")))
    passed_ids = set(_normalise_rule_ids(params.get("passedRules")))
    for rule_id, passed in rule_results.items():
        if passed:
            passed_ids.add(rule_id)
        else:
            failed_ids.add(rule_id)

    ignored_rule_ids = sorted((failed_ids | passed_ids) - loaded_set)
    failed_loaded = [rule_id for rule_id in loaded_ids if rule_id in failed_ids]
    passed_loaded = [rule_id for rule_id in loaded_ids if rule_id in passed_ids and rule_id not in failed_ids]
    not_evaluated = [
        rule_id for rule_id in loaded_ids if rule_id not in failed_ids and rule_id not in passed_ids
    ]

    violations = [
        {
            "rule": rule_id,
            "score": RULES_BY_ID[rule_id]["score"],
            "load": RULES_BY_ID[rule_id]["load"],
        }
        for rule_id in failed_loaded
    ]

    return {
        "traceUuid": params.get("traceUuid") or params.get("uuid"),
        "net": params.get("net"),
        "score": sum(item["score"] for item in violations),
        "maxScore": sum(RULES_BY_ID[rule_id]["score"] for rule_id in loaded_ids),
        "loadedRuleCount": len(loaded_ids),
        "violatedRules": failed_loaded,
        "violations": violations,
        "passedRules": passed_loaded,
        "notEvaluatedRules": not_evaluated,
        "ignoredRules": ignored_rule_ids,
        "unknownDynamicRules": unknown_dynamic,
    }


def rule_catalog() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "alwaysLoaded": [dict(rule) for rule in ALWAYS_LOADED_RULES],
        "dynamic": [dict(rule) for rule in DYNAMIC_RULES],
    }
