"""一期多方案报价编排：方案只描述工艺壳，金额全部来自现有 quote()。"""
import json
import os
import re
from queue import Queue
from threading import Thread
from urllib import error, request

from ..common.models import PlanQuoteComparison, ProcessPlanCandidate
from . import blank, blank_llm
from .engine import quote


TUZI_URL = "https://api.tu-zi.com/v1/chat/completions"
PLAN_MODEL_DEFAULT = "gpt-6-astra"
PLAN_TIMEOUT_SECONDS_DEFAULT = 5.0
PLAN_MAX_STEP_CHARS_DEFAULT = 120_000


def plan_model() -> str:
    return os.environ.get("TUZI_PLAN_MODEL") or PLAN_MODEL_DEFAULT


def _plan_timeout_seconds() -> float:
    try:
        timeout = float(
            os.environ.get("TUZI_PLAN_TIMEOUT_SECONDS")
            or PLAN_TIMEOUT_SECONDS_DEFAULT
        )
    except (TypeError, ValueError):
        return PLAN_TIMEOUT_SECONDS_DEFAULT
    return timeout if timeout > 0 else PLAN_TIMEOUT_SECONDS_DEFAULT


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


_FEATURE_SUMMARY_FIELDS = (
    "feature_id",
    "type",
    "diameter_mm",
    "depth_mm",
    "cut_depth_mm",
    "length",
    "width",
    "height",
    "depth",
    "thread_length",
    "pitch",
    "corner_radius",
    "hole_type",
    "pocket_type",
    "profile_type",
    "surface_type",
    "face_position",
    "position_type",
    "position",
    "axis",
)
_EXPLICIT_SETUP_HINT_FIELDS = (
    "setup_hint",
    "clamping_hint",
    "fixture_hint",
)


def _feature_summary(payload: dict) -> list[dict]:
    """只发送已进入报价的审定特征，以及与工艺路线有关的尺寸/装夹线索。"""
    summaries = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict) or not feature.get("type"):
            continue
        summary = {
            key: feature[key]
            for key in _FEATURE_SUMMARY_FIELDS
            if feature.get(key) not in (None, "")
        }
        dimensions = feature.get("dimensions")
        if isinstance(dimensions, dict):
            for key in _FEATURE_SUMMARY_FIELDS:
                if key not in summary and dimensions.get(key) not in (None, ""):
                    summary[key] = dimensions[key]
        setup_hints = [
            str(feature[key]).strip()
            for key in _EXPLICIT_SETUP_HINT_FIELDS
            if feature.get(key) not in (None, "")
        ]
        for key in ("position_type", "face_position", "position", "axis"):
            if summary.get(key) not in (None, ""):
                setup_hints.append(f"{key}={summary[key]}")
        if setup_hints:
            summary["setup_hints"] = setup_hints
        summaries.append(summary)
    return summaries


def _plan_step(
    step_path: str | None,
    step_text: str | bytes | None,
) -> tuple[str, bool]:
    text, truncated = blank_llm._read_step(step_path, step_text)
    try:
        limit = int(
            os.environ.get("TUZI_PLAN_MAX_STEP_CHARS")
            or PLAN_MAX_STEP_CHARS_DEFAULT
        )
    except (TypeError, ValueError):
        limit = PLAN_MAX_STEP_CHARS_DEFAULT
    limit = max(limit, 0)
    return text[:limit], truncated or len(text) > limit


def _geometry_bbox(geometry: dict | None) -> dict:
    if not isinstance(geometry, dict):
        return {}
    bbox = geometry.get("bounding_box_mm") or geometry
    if not isinstance(bbox, dict):
        return {}
    return {
        axis: bbox[axis]
        for axis in ("x", "y", "z")
        if bbox.get(axis) not in (None, "")
    }


def _plan_messages(
    payload: dict,
    *,
    step_text: str,
    step_truncated: bool,
    geometry: dict | None,
) -> list[dict]:
    operations, refs = _feature_refs(payload)
    context = {
        "bbox_mm": {
            "length": payload.get("length"),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "diameter": payload.get("diameter"),
        },
        "geometry_bbox_mm": _geometry_bbox(geometry),
        "material": payload.get("material") or payload.get("material_code"),
        "reviewed_features": _feature_summary(payload),
        "existing_feature_operations": operations,
        "existing_process_chain_refs": refs,
        "step_truncated": step_truncated,
    }
    prompt = f"已审上下文：{json.dumps(context, ensure_ascii=False)}"
    if step_text:
        prompt += f"\n\nSTEP:\n{step_text}"
    else:
        prompt += "\n\n未提供 STEP；仅按 bbox、材料和已审特征规划。"
    return [
        {
            "role": "system",
            "content": (
                "你是 CNC 工艺路线规划器。只输出 JSON："
                '{"candidates":[{"machine":"3轴立式加工中心","setups":2,'
                '"operations":["粗铣基准面","钻孔"],'
                '"process_chain_ref":["face-pipeline","hole-pipeline"],'
                '"label":"三轴两装夹","rationale":"通用设备完成基准转换"}]}。'
                "提出 1~3 条真实可区分的路线，operations 必须是可读工序名，"
                "rationale 只写一句短理由。任意两条路线至少在 machine、setups "
                "或 operations/process_chain_ref 工序链之一有实质差异；"
                "禁止同机床、同装夹、同工序链只改 label/rationale。"
                "禁止输出或推测价格、费率、成本、工时分钟、切削参数、刀具表；"
                "缺少切削表时不得编造。"
            ),
        },
        {"role": "user", "content": prompt},
    ]


def _request_llm_candidates(
    payload: dict,
    *,
    step_path: str | None = None,
    step_text: str | bytes | None = None,
    geometry: dict | None = None,
    timeout: float | None = None,
) -> list[dict]:
    api_key = os.environ.get("TUZI_API_KEY")
    if not api_key:
        return []
    plan_step, truncated = _plan_step(step_path, step_text)
    body = json.dumps({
        "model": plan_model(),
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": _plan_messages(
            payload,
            step_text=plan_step,
            step_truncated=truncated,
            geometry=geometry,
        ),
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
    timeout = timeout or _plan_timeout_seconds()
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


def _bounded_llm_request(
    payload: dict,
    *,
    step_path: str | None,
    step_text: str | bytes | None,
    geometry: dict | None,
) -> list[dict]:
    """给整个调用加硬上限；底层客户端不遵守 timeout 时也不阻塞报价。"""
    timeout = _plan_timeout_seconds()
    result: Queue = Queue(maxsize=1)

    def run():
        try:
            value = _request_llm_candidates(
                payload,
                step_path=step_path,
                step_text=step_text,
                geometry=geometry,
                timeout=timeout,
            )
        except Exception as exc:
            result.put((False, exc))
        else:
            result.put((True, value))

    worker = Thread(target=run, name="cncflow-plan-llm", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"tu-zi 方案生成超时（{timeout:g}s）")
    ok, value = result.get_nowait()
    if not ok:
        raise value
    return value


def _normalized_text(value) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").casefold())


def _candidate_signature(candidate: ProcessPlanCandidate) -> tuple:
    return (
        _normalized_text(candidate.machine),
        candidate.setups,
        tuple(_normalized_text(item) for item in candidate.operations),
        tuple(_normalized_text(item) for item in candidate.process_chain_ref),
    )


def _llm_candidates(
    payload: dict,
    *,
    step_path: str | None = None,
    step_text: str | bytes | None = None,
    geometry: dict | None = None,
) -> tuple[list[ProcessPlanCandidate], list[str]]:
    enabled = (os.environ.get("CNCFLOW_PLAN_LLM_ENABLED") or "1").strip().lower()
    if enabled in {"0", "false", "no"}:
        return [], ["LLM 方案生成未启用，已使用规则方案"]
    if not os.environ.get("TUZI_API_KEY"):
        return [], ["未配置 TUZI_API_KEY，已使用规则方案"]
    try:
        raw_candidates = _bounded_llm_request(
            payload,
            step_path=step_path,
            step_text=step_text,
            geometry=geometry,
        )
    except Exception as exc:
        return [], [f"{plan_model()}: {exc}；已回退规则方案"]
    defaults, refs = _feature_refs(payload)
    candidates = []
    signatures = set()
    duplicate_count = 0
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
        candidate = ProcessPlanCandidate(
            id=f"llm-{index}",
            source="llm",
            machine=machine,
            setups=max(setups, 1),
            operations=[str(item) for item in operations if str(item).strip()] or defaults,
            process_chain_ref=[str(item) for item in process_refs],
            label=str(raw.get("label") or f"AI 方案 {index}"),
            rationale=str(raw.get("rationale") or "").strip()[:300],
            model=plan_model(),
        )
        signature = _candidate_signature(candidate)
        if signature in signatures:
            duplicate_count += 1
            continue
        candidates.append(candidate)
        signatures.add(signature)
    if not candidates:
        return [], ["tu-zi 未返回有效方案；已回退规则方案"]
    warnings = []
    if duplicate_count:
        warnings.append(
            f"tu-zi 返回 {duplicate_count} 条同机床/装夹/工序链重复路线，已去重"
        )
    return candidates, warnings


def generate_candidates(
    payload: dict,
    *,
    step_path: str | None = None,
    step_text: str | bytes | None = None,
    geometry: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """用户方案固定第一；其后优先 LLM，规则补足到至少两个方案。"""
    candidates = []
    user = _user_candidate(payload.get("user_process_plan"), payload)
    if user:
        candidates.append(user)
    llm, warnings = _llm_candidates(
        payload,
        step_path=step_path,
        step_text=step_text,
        geometry=geometry,
    )
    existing_signatures = {_candidate_signature(candidate) for candidate in candidates}
    duplicate_count = 0
    for candidate in llm:
        signature = _candidate_signature(candidate)
        if signature in existing_signatures:
            duplicate_count += 1
            continue
        candidates.append(candidate)
        existing_signatures.add(signature)
    if duplicate_count:
        warnings.append(f"{duplicate_count} 条 LLM 路线与已有方案重复，已去重")
    for candidate in _rule_candidates(payload):
        if len(candidates) >= 2:
            break
        signature = _candidate_signature(candidate)
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
    use_blank_llm: bool = False,
    step_path: str | None = None,
    step_text: str | None = None,
    geometry: dict | None = None,
) -> dict:
    geometry_context = geometry or payload.get("geometry")
    geometry_quote_payload = blank_llm.geometry_payload(payload, geometry_context)
    geometry_quote_payload.pop("force_blank_llm", None)
    legacy_decision = blank.decide(geometry_quote_payload)
    if use_blank_llm:
        decision = blank_llm.decide_cached(
            geometry_quote_payload,
            conn,
            step_path=step_path,
            step_text=step_text or payload.get("step_text"),
            geometry=geometry_context,
        )
    else:
        decision = blank_llm.geometry_decide(
            geometry_quote_payload,
            geometry=geometry_context,
        )
    candidates, warnings = generate_candidates(
        payload,
        step_path=step_path,
        step_text=step_text or payload.get("step_text"),
        geometry=geometry_context,
    )
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
