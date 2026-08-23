"""询价报价单 PDF：只排版已持久化的 live quote，不在导出时重新报价。"""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from threading import Lock

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


_FONT_NAME = "CNCFlowCJK"
_FONT_LOCK = Lock()
_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)
_COST_LABELS = (
    ("material", "材料"),
    ("machining", "加工"),
    ("setup", "调机/装夹"),
    ("fixture", "夹具"),
    ("programming", "编程"),
    ("inspect", "检测"),
    ("toolwear", "刀具损耗"),
    ("scrap", "不良损耗"),
)


def _register_cjk_font() -> str:
    if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _FONT_NAME
    with _FONT_LOCK:
        if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return _FONT_NAME
        configured = os.environ.get("CNCFLOW_PDF_FONT_PATH")
        candidates = (configured, *_CJK_FONT_CANDIDATES) if configured else _CJK_FONT_CANDIDATES
        for candidate in candidates:
            if not candidate or not Path(candidate).is_file():
                continue
            pdfmetrics.registerFont(
                TTFont(_FONT_NAME, candidate),
            )
            return _FONT_NAME

        # 仅用于非容器开发/CI；生产镜像安装文泉驿正黑并嵌入其 TrueType 子集。
        fallback = "STSong-Light"
        if fallback not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(fallback))
        return fallback


def _value(value, empty="—") -> str:
    return empty if value is None or value == "" else str(value)


def _number(value, digits=2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    text = f"{number:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def _quote_hours(quote_data: dict) -> str:
    quote = quote_data.get("quote") or {}
    hours = quote.get("hours")
    if hours is None:
        hours = (quote_data.get("hours") or {}).get("total")
    return _number(hours, 1)


def _records(inquiry: dict) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    parts = inquiry.get("parts") or []
    records.extend([
        ("meta", f"询价 ID：{_value(inquiry.get('id'))}"),
        ("meta", f"询价标题：{_value(inquiry.get('title'))}"),
        ("meta", f"客户：{_value(inquiry.get('customer'))}"),
    ])
    if not parts:
        records.append(("body", "零件：—"))
        return records

    for index, part in enumerate(parts, start=1):
        quote_data = part.get("quote") if isinstance(part.get("quote"), dict) else {}
        quote = quote_data.get("quote") or {}
        ui_cost = quote_data.get("ui_cost") or {}
        process_sequence = quote_data.get("process_sequence") or []
        deductions = quote_data.get("deductions")
        if not isinstance(deductions, list):
            deductions = (quote_data.get("risk") or {}).get("deductions") or []

        records.append(("section", f"零件 {index}｜{_value(part.get('name'))}"))
        records.append((
            "body",
            f"材料：{_value(part.get('material_code'))}    数量：{_value(part.get('qty'), '1')}",
        ))
        records.append((
            "body",
            "报价："
            f"金额 ¥{_number(quote.get('amount'))}    "
            f"成本 ¥{_number(quote.get('cost'))}    "
            f"毛利 {_number(quote.get('margin'))}%    "
            f"工时 {_quote_hours(quote_data)}h    "
            f"建议交期 {_number(quote_data.get('suggested_days'), 0)} 天",
        ))

        costs = "    ".join(
            f"{label} ¥{_number(ui_cost.get(key))}"
            for key, label in _COST_LABELS
        )
        records.append(("subsection", "成本明细（ui_cost）"))
        records.append(("body", costs))

        records.append(("subsection", "工艺顺序（process_sequence）"))
        if process_sequence:
            for step_index, step in enumerate(process_sequence, start=1):
                order = step.get("order") or step_index
                records.append((
                    "item",
                    f"{order}. {_value(step.get('name') or step.get('process'))}"
                    f"｜工艺 {_value(step.get('process'))}"
                    f"｜刀具 {_value(step.get('sku') or step.get('tool'))}"
                    f"｜{_number(step.get('minutes'))} min"
                    f"｜¥{_number(step.get('amount'))}",
                ))
        else:
            records.append(("item", "—"))

        records.append(("subsection", "风险扣分（deductions[]）"))
        if deductions:
            for deduction in deductions:
                records.append((
                    "item",
                    f"{_value(deduction.get('rule_id'))}"
                    f"｜{_value(deduction.get('dimension'))}"
                    f"｜-{_number(deduction.get('deduction'))} 分"
                    f"｜{_value(deduction.get('reason'))}",
                ))
        else:
            records.append(("item", "无"))
    return records


def _wrap(text: str, font_name: str, font_size: float, width: float) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _layout(
    records: list[tuple[str, str]],
    font_name: str,
    width: float,
    available_height: float,
) -> tuple[float, float, int, list[tuple[str, str]]]:
    for columns in (1, 2):
        column_width = (width - (18 if columns == 2 else 0)) / columns
        for font_size in (8.5, 8, 7.5, 7, 6.5, 6, 5.5, 5):
            expanded: list[tuple[str, str]] = []
            for role, text in records:
                indent = 10 if role == "item" else 0
                for line_index, line in enumerate(_wrap(text, font_name, font_size, column_width - indent)):
                    expanded.append((role if line_index == 0 else "continuation", line))
            leading = font_size * 1.42
            capacity = max(1, int(available_height // leading))
            if len(expanded) <= capacity * columns:
                return font_size, leading, columns, expanded

    font_size = 4.5
    leading = font_size * 1.35
    expanded = []
    column_width = (width - 36) / 3
    for role, text in records:
        indent = 8 if role == "item" else 0
        for line_index, line in enumerate(_wrap(text, font_name, font_size, column_width - indent)):
            expanded.append((role if line_index == 0 else "continuation", line))
    return font_size, leading, 3, expanded


def build_quote_pdf(inquiry: dict) -> bytes:
    """用询价响应中的 quote 快照生成单页 PDF。"""
    font_name = _register_cjk_font()
    output = BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    title = f"{_value(inquiry.get('title'), '询价')} 报价单"
    pdf.setTitle(title)
    pdf.setAuthor("CNCFlow")
    pdf.setSubject(f"询价报价单 {_value(inquiry.get('id'))}")

    parts = inquiry.get("parts") or []
    first_quote = (parts[0].get("quote") or {}) if parts else {}
    first_values = first_quote.get("quote") or {}
    pdf.setKeywords(
        f"inquiry_id={_value(inquiry.get('id'))};"
        f"amount={_number(first_values.get('amount'))};"
        f"hours={_quote_hours(first_quote)};"
        f"suggested_days={_number(first_quote.get('suggested_days'), 0)}",
    )

    margin = 36
    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setFont(font_name, 18)
    pdf.drawString(margin, page_height - 52, "CNCFlow 报价单")
    pdf.setFont(font_name, 8)
    pdf.setFillColor(HexColor("#64748b"))
    pdf.drawRightString(page_width - margin, page_height - 49, "QUOTE / 单页")
    pdf.setStrokeColor(HexColor("#cbd5e1"))
    pdf.line(margin, page_height - 64, page_width - margin, page_height - 64)

    body_top = page_height - 82
    body_bottom = 38
    usable_width = page_width - margin * 2
    records = _records(inquiry)
    font_size, leading, columns, lines = _layout(
        records,
        font_name,
        usable_width,
        body_top - body_bottom,
    )
    gap = 18 if columns == 2 else (18 if columns == 3 else 0)
    column_width = (usable_width - gap * (columns - 1)) / columns
    capacity = max(1, int((body_top - body_bottom) // leading))

    for line_index, (role, text) in enumerate(lines):
        column = min(columns - 1, line_index // capacity)
        row = line_index % capacity
        x = margin + column * (column_width + gap)
        if role in {"item", "continuation"}:
            x += 10 if columns < 3 else 8
        y = body_top - row * leading
        if role == "section":
            pdf.setFillColor(HexColor("#1d4ed8"))
            pdf.setFont(font_name, font_size + 1)
        elif role == "subsection":
            pdf.setFillColor(HexColor("#334155"))
            pdf.setFont(font_name, font_size)
        elif role == "meta":
            pdf.setFillColor(HexColor("#0f172a"))
            pdf.setFont(font_name, font_size + 0.4)
        else:
            pdf.setFillColor(HexColor("#475569"))
            pdf.setFont(font_name, font_size)
        pdf.drawString(x, y, text)

    pdf.setStrokeColor(HexColor("#cbd5e1"))
    pdf.line(margin, 28, page_width - margin, 28)
    pdf.setFillColor(HexColor("#94a3b8"))
    pdf.setFont(font_name, 6.5)
    pdf.drawString(margin, 17, "本报价由 CNCFlow 当前报价快照生成")
    pdf.drawRightString(page_width - margin, 17, "1 / 1")
    pdf.save()
    return output.getvalue()
