"""孔可加工性判定（文档1模块一，前置风控层）。

规则数据在 rules/hole/machinability.yaml，本模块只做确定性求值：
- bands: 数值分档（min 含 / max 不含，exclusive_min 可改为不含）
- cases: 枚举匹配（如材料）
- all_of: 组合条件（全部满足才命中）
综合结论 = 所有命中规则的最高 level（四级判定，文档1 §1.8）。
"""
from ...common.models import MachinabilityResult
from ...common.rule_loader import load_rules
from .models import HoleSpec


def _metric_value(metric: str, hole: HoleSpec, material: str, tolerance_it: int):
    values = {
        "h_over_d": hole.h_over_d,
        "diameter_mm": hole.diameter_mm,
        "material": material,
        "tolerance_it": tolerance_it,
    }
    return values[metric]


def _in_band(value: float, band: dict) -> bool:
    min_v = band.get("min")
    max_v = band.get("max")
    if min_v is not None:
        if band.get("exclusive_min"):
            if value <= min_v:
                return False
        elif value < min_v:
            return False
    if max_v is not None and value >= max_v:
        return False
    return True


def evaluate(hole: HoleSpec, material: str, tolerance_it: int) -> MachinabilityResult:
    rules = load_rules("hole/machinability.yaml")
    levels_map = rules["levels"]

    fired = []
    max_level = 1
    risk_notes = []

    for check in rules["checks"]:
        hit = None
        if "bands" in check:
            value = _metric_value(check["metric"], hole, material, tolerance_it)
            for band in check["bands"]:
                if _in_band(value, band):
                    hit = band
                    break
        elif "cases" in check:
            value = _metric_value(check["metric"], hole, material, tolerance_it)
            hit = check["cases"].get(value)
        elif "all_of" in check:
            if all(
                _in_band(_metric_value(cond["metric"], hole, material, tolerance_it), cond)
                for cond in check["all_of"]
            ):
                hit = check  # 结论字段就写在 check 顶层
        else:
            raise ValueError(f"规则 {check.get('id')} 缺少 bands/cases/all_of")

        if hit is None:
            continue

        fired.append(check["id"])
        level = int(hit["level"])
        max_level = max(max_level, level)
        note = f"{check['name']}"
        if hit.get("grade"):
            note += f"[{hit['grade']}]"
        note += f"：{hit['risk']}（{hit['process_stage']}）"
        risk_notes.append(note)

    return MachinabilityResult(
        level=max_level,
        label=levels_map[max_level],
        risk_notes=risk_notes,
        fired_rules=fired,
    )
