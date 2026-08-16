"""通用难度/工序链：YAML first-match，NA 仍返回结果。"""
from ..common.rule_loader import load_rules


def _num(payload, key, default=None):
    val = payload.get(key)
    if val is None:
        return default
    return float(val)


def evaluate_difficulty(rules_relpath: str, metrics: dict) -> dict:
    rules = load_rules(rules_relpath)
    fired = []
    worst = "D1"
    order = {"D1": 1, "D2": 2, "D3": 3, "D4": 4, "NA": 5}
    for check in rules.get("checks", []):
        metric = check.get("metric")
        value = metrics.get(metric)
        if value is None:
            continue
        for band in check.get("bands", []):
            mn = band.get("min")
            mx = band.get("max")
            if mn is not None and value < mn:
                continue
            if mx is not None and value >= mx:
                continue
            level = band["level"]
            fired.append({"id": check["id"], "name": check.get("name"), "level": level, "value": value})
            if order[level] > order[worst]:
                worst = level
            break
    return {"level": worst, "fired_rules": fired, "na": worst == "NA"}


def process_chain(rules_relpath: str, difficulty: str) -> list:
    rules = load_rules(rules_relpath)
    chains = rules.get("chains", {})
    return list(chains.get(difficulty) or chains.get("default") or [])
