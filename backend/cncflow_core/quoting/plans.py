"""一期多方案报价编排：方案只描述工艺壳，金额全部来自现有 quote()。"""
import json
import os
import re
from urllib import error, request

from ..common.models import PlanQuoteComparison, ProcessPlanCandidate
from . import blank, blank_llm
from .engine import quote


TUZI_URL = "https://api.tu-zi.com/v1/chat/completions"
def _feature_refs(payload: dict) -> tuple[list[str], list[str]]:
    types = list(dict.fromkeys(
        str(feature.get("type"))
        for feature in payload.get("features") or []
        if isinstance(feature, dict) and feature.get("type")
    ))
    operations = [
        {
            "hole": "孔加工",
            "thread": "螺纹加工",
            "face": "铣面",
            "pocket": "型腔铣削",
            "slot": "槽铣削",
            "surface": "曲面精加工",
            "step": "台阶铣削",
        }.get(feature_type, feature_type)
        for feature_type in types
    ]
    return operations or ["按现有特征工艺链加工"], [
        f"{feature_type}-pipeline" for feature_type in types
    ] or ["quote-engine-default"]


def _machine_axes(machine: str) -> int:
    match = re.search(r"([345])\s*轴", machine)
    return int(match.group(1)) if match else 3


def _user_candidate(raw, payload: dict) -> ProcessPlanCandidate | None:
    if raw in (None, "", {}):
        return None
    defaults, refs = _feature_refs(payload)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return ProcessPlanCandidate(
            id="user-plan",
            source="user",
            machine="3轴立式加工中心",
            setups=1,
            operations=[text],
            process_chain_ref=refs,
            label="用户给定",
        )
    if not isinstance(raw, dict):
        raise ValueError("user_process_plan 须为字符串或对象")
    machine = str(raw.get("machine") or raw.get("machine_type") or "3轴立式加工中心")
    try:
        setups = int(raw.get("setups") or raw.get("setup_count") or 1)
    except (TypeError, ValueError):
        raise ValueError("user_process_plan.setups 须为正整数") from None
    if setups < 1:
        raise ValueError("user_process_plan.setups 须为正整数")
    operations = raw.get("operations") or raw.get("process_chain")
    if isinstance(operations, str):
        operations = [operations]
    if not isinstance(operations, list):
        operations = defaults
    operations = [str(item) for item in operations if str(item).strip()] or defaults
    process_refs = raw.get("process_chain_ref") or refs
    if isinstance(process_refs, str):
        process_refs = [process_refs]
    if not isinstance(process_refs, list):
        process_refs = refs
    return ProcessPlanCandidate(
        id="user-plan",
        source="user",
        machine=machine,
        setups=setups,
        operations=operations,
        process_chain_ref=[str(item) for item in process_refs],
        label="用户给定",
    )


def _rule_candidates(payload: dict) -> list[ProcessPlanCandidate]:
    operations, refs = _feature_refs(payload)
    features = payload.get("features") or []
    advanced = any(
        isinstance(feature, dict)
        and (
            feature.get("type") == "surface"
            or "倾斜" in str(feature.get("position_type") or "")
            or feature.get("surface_type") == "自由曲面"
        )
        for feature in features
    )
    first_machine = "5轴联动加工中心" if advanced else "3轴立式加工中心"
    first_setups = 1 if advanced else 2
    return [
        ProcessPlanCandidate(
            id="rule-efficient",
            source="rule",
            machine=first_machine,
            setups=first_setups,
            operations=operations,
            process_chain_ref=refs,
            label=f"{first_machine}·{first_setups}装夹",
        ),
        ProcessPlanCandidate(
            id="rule-low-setup",
            source="rule",
            machine="4轴立式加工中心" if not advanced else "3轴立式加工中心",
            setups=1 if not advanced else 2,
            operations=operations,
            process_chain_ref=refs,
            label="少装夹方案" if not advanced else "通用设备备选",
        ),
    ]


def _extract_json(text: str):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = min(
        (index for index in (text.find("["), text.find("{")) if index >= 0),
        default=-1,
    )
    if start > 0:
        text = text[start:]
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed.get("candidates") or parsed.get("plans") or []
    return parsed


def _request_llm_candidates(payload: dict) -> list[dict]:
    api_key = os.environ.get("TUZI_API_KEY")
    if not api_key:
        return []
    operations, refs = _feature_refs(payload)
    prompt = {
        "envelope_mm": {
            "length": payload.get("length"),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "diameter": payload.get("diameter"),
        },
        "material": payload.get("material") or payload.get("material_code"),
        "feature_types": refs,
        "required_operations": operations,
    }
    body = json.dumps({
        "model": os.environ.get("TUZI_PLAN_MODEL") or "gpt-4.1-mini",
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 CNC 工艺规划器。只输出 JSON："
                    '{"candidates":[{"machine":"3轴立式加工中心","setups":2,'
                    '"operations":["..."],"process_chain_ref":["hole-pipeline"],'
                    '"label":"..."}]}。提出 1~3 个工艺壳；禁止输出价格、费率或成本。'
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }, ensure_ascii=False).encode()
    req = request.Request(
        TUZI_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = float(os.environ.get("TUZI_PLAN_TIMEOUT_SECONDS") or "8")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode())
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"tu-zi 方案生成失败: {exc}") from exc
    content = (
        ((result.get("choices") or [{}])[0].get("message") or {}).get("content")
    )
    if not isinstance(content, str):
        raise RuntimeError("tu-zi 方案生成未返回 JSON 内容")
    parsed = _extract_json(content)
    if not isinstance(parsed, list):
        raise RuntimeError("tu-zi 方案 candidates 须为数组")
    return parsed


def _llm_candidates(payload: dict) -> tuple[list[ProcessPlanCandidate], list[str]]:
    enabled = (os.environ.get("CNCFLOW_PLAN_LLM_ENABLED") or "1").strip().lower()
    if enabled in {"0", "false", "no"}:
        return [], ["LLM 方案生成未启用，已使用规则方案"]
    if not os.environ.get("TUZI_API_KEY"):
        return [], ["未配置 TUZI_API_KEY，已使用规则方案"]
    try:
        raw_candidates = _request_llm_candidates(payload)
    except Exception as exc:
        return [], [f"{exc}；已回退规则方案"]
    defaults, refs = _feature_refs(payload)
    candidates = []
    for index, raw in enumerate(raw_candidates[:3], 1):
        if not isinstance(raw, dict):
            continue
        machine = str(raw.get("machine") or "").strip()
        if not machine:
            continue
        try:
            setups = int(raw.get("setups") or 1)
        except (TypeError, ValueError):
            continue
        operations = raw.get("operations")
        if isinstance(operations, str):
            operations = [operations]
        if not isinstance(operations, list):
            operations = defaults
        process_refs = raw.get("process_chain_ref")
        if isinstance(process_refs, str):
            process_refs = [process_refs]
        if not isinstance(process_refs, list):
            process_refs = refs
        candidates.append(ProcessPlanCandidate(
            id=f"llm-{index}",
            source="llm",
            machine=machine,
            setups=max(setups, 1),
            operations=[str(item) for item in operations if str(item).strip()] or defaults,
            process_chain_ref=[str(item) for item in process_refs],
            label=str(raw.get("label") or f"AI 方案 {index}"),
        ))
    if not candidates:
        return [], ["tu-zi 未返回有效方案；已回退规则方案"]
    return candidates, []


def generate_candidates(payload: dict) -> tuple[list[dict], list[str]]:
    """用户方案固定第一；其后优先 LLM，规则补足到至少两个方案。"""
    candidates = []
    user = _user_candidate(payload.get("user_process_plan"), payload)
    if user:
        candidates.append(user)
    llm, warnings = _llm_candidates(payload)
    candidates.extend(llm)
    existing_signatures = {
        (candidate.machine, candidate.setups) for candidate in candidates
    }
    for candidate in _rule_candidates(payload):
        if len(candidates) >= 2:
            break
        signature = (candidate.machine, candidate.setups)
        if signature in existing_signatures:
            continue
        candidates.append(candidate)
        existing_signatures.add(signature)
    return [candidate.to_dict() for candidate in candidates], warnings


def build_plan_quotes(
    payload: dict,
    conn,
    rules_version: str = "",
    *,
    step_path: str | None = None,
    step_text: str | None = None,
    geometry: dict | None = None,
) -> dict:
    geometry_context = geometry or payload.get("geometry")
    geometry_quote_payload = blank_llm.geometry_payload(payload, geometry_context)
    legacy_decision = blank.decide(geometry_quote_payload)
    decision = blank_llm.decide(
        geometry_quote_payload,
        step_path=step_path,
        step_text=step_text or payload.get("step_text"),
        geometry=geometry_context,
    )
    candidates, warnings = generate_candidates(payload)
    comparison = []
    for candidate in candidates:
        quote_payload = dict(geometry_quote_payload)
        quote_payload.pop("user_process_plan", None)
        quote_payload.pop("step_text", None)
        quote_payload["equipment_type"] = candidate["machine"]
        quote_payload["machine_axes"] = _machine_axes(candidate["machine"])
        if not quote_payload.get("stock_type") and not quote_payload.get("blank_type"):
            quote_payload["stock_type"] = (
                "棒料"
                if legacy_decision["blank_type"] == "round_bar"
                else "板料"
            )
        engine_result = quote(quote_payload, conn, rules_version=rules_version)
        row = PlanQuoteComparison(
            plan_id=candidate["id"],
            label=candidate["label"],
            source=candidate["source"],
            machine=candidate["machine"],
            setup_count=candidate["setups"],
            total_cost=float(engine_result["quote"]["cost"]),
            quoted_amount=float(engine_result["quote"]["amount"]),
            machining_cost=float(
                engine_result["ui_cost"]["machining"]
                + engine_result["ui_cost"]["setup"]
            ),
            machining_time_hours=float(engine_result["hours"]["total"]),
        ).to_dict()
        row["engine_setup_count"] = int(
            (engine_result.get("fixture") or {}).get("setup_count") or 0
        )
        comparison.append(row)
    return {
        "blank": decision,
        "candidates": candidates,
        "comparison": comparison,
        "warnings": warnings,
    }
