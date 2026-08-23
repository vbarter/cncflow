"""PDF工程图文本、OCR与可选视觉模型解析。"""
import json
import os
import re
import base64
from io import BytesIO


TUZI_BASE_URL = "https://api.tu-zi.com"


def _match(patterns, text, transform=lambda value: value):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return transform(match.group(1)), match.group(0)
    return None, None


def _extract_fields(text: str) -> dict:
    fields = {}
    material, raw = _match([
        r"(?:材料|材质)\s*[:：]?\s*([^\n,，;；]{2,30})",
        r"\b((?:AL)?6061(?:-T6)?|(?:SUS)?304|(?:SUS)?316L?|45#|Q235|TC4)\b",
    ], text)
    if material:
        fields["material"] = {"value": material.strip(), "raw": raw, "confidence": 0.78}
    quantity, raw = _match([r"(?:数量|QTY)\s*[:：]?\s*(\d+)", r"(\d+)\s*(?:件|PCS)"], text, int)
    if quantity:
        fields["quantity"] = {"value": quantity, "raw": raw, "confidence": 0.8}
    tolerance, raw = _match([r"(?:公差\s*[:：]?\s*)?([±]\s*\d+(?:\.\d+)?)", r"(ISO\s*2768[-\w]*)"], text)
    if tolerance:
        fields["tolerance"] = {"value": tolerance.replace(" ", ""), "raw": raw, "confidence": 0.75}
    ra, raw = _match([r"\bRa\s*[:=]?\s*(\d+(?:\.\d+)?)", r"粗糙度[^\d]*(\d+(?:\.\d+)?)"], text)
    if ra:
        fields["roughness_ra"] = {"value": float(ra), "raw": raw, "confidence": 0.82}
    thread_specs = sorted(set(re.findall(r"\bM\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?)?\b", text, re.I)))
    if thread_specs:
        fields["thread_specs"] = {"value": thread_specs, "raw": ", ".join(thread_specs), "confidence": 0.72}
    for name in ("阳极氧化", "发黑", "镀锌", "镀镍", "喷砂", "抛光", "钝化"):
        if name in text:
            fields["surface_finish"] = {"value": name, "raw": name, "confidence": 0.8}
            break
    return fields


def _ocr_page(page):
    try:
        import pytesseract
        bitmap = page.render(scale=300 / 72)
        image = bitmap.to_pil()
        langs = os.environ.get("CNCFLOW_TESSERACT_LANG", "chi_sim+eng")
        return pytesseract.image_to_string(image, lang=langs)
    except Exception as exc:
        return "", f"OCR不可用: {exc}"


def _json_object(content):
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("tu-zi 返回内容不是 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("tu-zi 返回 JSON 不是对象")
    return value


def _value(value):
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _first(source, *keys):
    for key in keys:
        if key in source and _value(source[key]) not in (None, "", []):
            return _value(source[key])
    return None


def _number(value, integer=False):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if not match:
            return None
        value = match.group(0)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if integer and number.is_integer() else (None if integer else number)


def map_tuzi_fields(payload: dict) -> dict:
    """把 tu-zi JSON 严格映射到冻结字段；不会生成任何 3D feature。"""
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("fields")
    source = {**payload, **nested} if isinstance(nested, dict) else payload
    out = {}

    material = _first(source, "material_code", "material", "材质", "材料")
    if material is not None:
        material = str(material).strip()
        if material:
            out["material_code"] = material[:100]

    tolerance = _first(source, "tolerance_it", "IT", "it", "公差等级")
    tolerance_it = _number(tolerance, integer=True)
    if tolerance_it is not None and 1 <= tolerance_it <= 18:
        out["tolerance_it"] = tolerance_it

    roughness = _first(source, "roughness_ra", "Ra", "ra", "粗糙度")
    roughness_ra = _number(roughness)
    if roughness_ra is not None and roughness_ra > 0:
        out["roughness_ra"] = roughness_ra

    surface = _first(
        source,
        "surface_finish",
        "surface_treatment",
        "surface",
        "表面处理",
    )
    if surface is not None:
        surface = str(surface).strip()
        if surface:
            out["surface_finish"] = surface[:200]

    raw_specs = _first(
        source,
        "thread_specs",
        "threads",
        "thread_specifications",
        "螺纹规格列表",
        "螺纹规格",
    )
    if isinstance(raw_specs, str):
        raw_specs = re.split(r"[,，;；\n]+", raw_specs)
    if isinstance(raw_specs, list):
        specs = []
        for item in raw_specs:
            item = str(_value(item) or "").strip()
            if item and item not in specs:
                specs.append(item[:100])
        if specs:
            out["thread_specs"] = specs

    qty = _number(_first(source, "qty", "quantity", "数量", "QTY"), integer=True)
    if qty is not None and 1 <= qty <= 1_000_000:
        out["qty"] = qty
    return out


def _tuzi_extract(text: str, images: list) -> dict:
    api_key = os.environ.get("TUZI_API_KEY") or os.environ.get("VISION_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 TUZI_API_KEY")
    from openai import OpenAI

    timeout = float(os.environ.get("TUZI_TIMEOUT_SECONDS", "20"))
    client = OpenAI(
        api_key=api_key,
        base_url=f"{TUZI_BASE_URL}/v1",
        timeout=timeout,
        max_retries=0,
    )
    prompt = (
        "你是 CNC 工程图字段抽取器。根据 PDF 页面图像和可选文本，只抽取明确标注的值，"
        "不要推断，不要生成加工特征。只返回一个 JSON 对象，键固定为："
        'material_code, tolerance_it, roughness_ra, surface_finish, thread_specs, qty。'
        "tolerance_it 是 1~18 整数；roughness_ra 是正数；thread_specs 是字符串数组；"
        "qty 是正整数。未找到的字段返回 null 或空数组。\n\n"
        f"PDF 文本（可能为空）：\n{text[:50000]}"
    )
    content = [{"type": "text", "text": prompt}]
    content.extend({"type": "image_url", "image_url": {"url": image}} for image in images[:5])
    response = client.chat.completions.create(
        model=os.environ.get("TUZI_MODEL") or os.environ.get("VISION_MODEL", "gpt-4.1-mini"),
        messages=[{"role": "user", "content": content}], response_format={"type": "json_object"},
    )
    raw = _json_object(response.choices[0].message.content)
    return {"raw": raw, "fields": map_tuzi_fields(raw)}


def _render_data_url(page) -> str:
    image = page.render(scale=180 / 72).to_pil()
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


def parse_pdf(path: str, allow_external_ai=False) -> dict:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("解析Worker未安装pdfplumber") from exc
    pages = []
    warnings = []
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        for index, page in enumerate(pdf.pages[:20], start=1):
            text = page.extract_text() or ""
            method = "text"
            if len(text.strip()) < 20:
                method = "ocr"
                try:
                    import pypdfium2 as pdfium
                    doc = pdfium.PdfDocument(path)
                    text, warning = _ocr_page(doc[index - 1])
                    if warning:
                        warnings.append(f"第{index}页{warning}")
                except Exception as exc:
                    warnings.append(f"第{index}页OCR失败: {exc}")
            pages.append({"page": index, "method": method, "text": text[:30000]})
        if total_pages > 20:
            warnings.append(f"PDF共{total_pages}页，MVP仅解析前20页")
    combined = "\n".join(page["text"] for page in pages)
    fields = _extract_fields(combined)
    confidence = round(sum(v["confidence"] for v in fields.values()) / max(len(fields), 1), 3)
    images = []
    tuzi = {"provider": "tu-zi", "called": False, "ok": False}
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(path)
        images = [_render_data_url(doc[index]) for index in range(min(len(doc), 5))]
    except Exception as exc:
        warnings.append(f"PDF页面渲染失败: {exc}")
    try:
        extracted = _tuzi_extract(combined, images)
        tuzi.update({"called": True, "ok": True, "model": os.environ.get("TUZI_MODEL") or os.environ.get("VISION_MODEL", "gpt-4.1-mini")})
        backfill = extracted["fields"]
        tuzi["raw"] = extracted["raw"]
        if not backfill:
            tuzi["ok"] = False
            tuzi["warning"] = "tu-zi 未返回可回填字段"
            warnings.append(tuzi["warning"])
    except Exception as exc:
        backfill = {}
        tuzi.update({"called": bool(os.environ.get("TUZI_API_KEY") or os.environ.get("VISION_API_KEY")), "warning": f"tu-zi 提取失败: {exc}"})
        warnings.append(tuzi["warning"])
    return {
        "parser": "pdf-local", "page_count": len(pages), "fields": fields,
        "pages": pages, "confidence": confidence, "backfill": backfill,
        "tuzi": tuzi, "warnings": warnings,
    }
