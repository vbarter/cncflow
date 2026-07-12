"""PDF工程图文本、OCR与可选视觉模型解析。"""
import json
import os
import re
import base64
from io import BytesIO


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


def _vision_extract(images: list) -> dict:
    api_key = os.environ.get("VISION_API_KEY")
    if not api_key:
        return {"fields": {}, "warning": "未配置视觉模型"}
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=os.environ.get("VISION_BASE_URL") or None)
    content = [{"type": "text", "text": "提取工程图中的材料、数量、公差、Ra、表面处理、孔和螺纹标注。只返回JSON对象。"}]
    content.extend({"type": "image_url", "image_url": {"url": image}} for image in images[:5])
    response = client.chat.completions.create(
        model=os.environ.get("VISION_MODEL", "gpt-4.1-mini"),
        messages=[{"role": "user", "content": content}], response_format={"type": "json_object"},
    )
    return {"fields": json.loads(response.choices[0].message.content), "warning": None}


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
    low_confidence_images = []
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
                    if allow_external_ai and len(low_confidence_images) < 5:
                        low_confidence_images.append(_render_data_url(doc[index - 1]))
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
    vision = None
    if allow_external_ai and confidence < 0.7:
        try:
            vision = _vision_extract(low_confidence_images)
        except Exception as exc:
            warnings.append(f"视觉模型调用失败: {exc}")
    return {
        "parser": "pdf-local", "page_count": len(pages), "fields": fields,
        "pages": pages, "confidence": confidence, "vision": vision, "warnings": warnings,
    }
