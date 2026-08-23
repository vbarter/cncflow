"""内部报价置信度：始终出价，confidence<30 标禁止给客户。"""

BOUNDS = {
    "drill": (0.1, 8),
    "tap": (0.2, 5),
    "face_mill": (0.5, 60),
    "pocket_mill": (0.5, 90),
    "default": (0.1, 60),
}

LEVELS = (
    (90, "low", False),
    (70, "medium_low", False),
    (50, "medium", False),
    (30, "high", False),
    (0, "critical", True),
)


def classify(value: int) -> tuple[str, bool]:
    value = max(0, min(100, int(value)))
    for threshold, name, forbid in LEVELS:
        if value >= threshold:
            return name, forbid or value < 30
    return "critical", True


def score(operations: list) -> dict:
    confidence = 100
    warnings, errors = [], []
    tags = []
    for op in operations:
        t = float(op.get("minutes") or 0)
        name = op.get("op") or "default"
        lo, hi = BOUNDS.get(name, BOUNDS["default"])
        if t < lo:
            confidence -= 5
            warnings.append({"op": name, "t": t, "deduction": 5})
        elif t <= hi:
            pass
        elif t < 2 * hi:
            confidence -= 10
            warnings.append({"op": name, "t": t, "deduction": 10})
        elif t < 5 * hi:
            confidence -= 20
            errors.append({"op": name, "t": t, "deduction": 20})
        else:
            confidence -= 40
            errors.append({"op": name, "t": t, "deduction": 40})
        if op.get("na") or op.get("out_of_bound"):
            confidence -= 15
            tags.append("超出常规边界")
    confidence = max(0, min(100, confidence))
    level, customer_forbidden = classify(confidence)
    if confidence < 30:
        customer_forbidden = True
        tags.append("禁止给客户")
    return {
        "confidence": confidence,
        "level": level,
        "customer_forbidden": customer_forbidden,
        "tags": list(dict.fromkeys(tags)),
        "warnings": warnings,
        "errors": errors,
    }
