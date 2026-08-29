"""报价单 PDF endpoint 契约。"""
from io import BytesIO

import pytest
from pypdf import PdfReader

from cncflow_core.common.db import get_conn
from cncflow_core.ingestion.jobs import finish_job


MINIMAL_STEP = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)


def _create_o8_inquiry(client, db_path):
    inquiry = client.post(
        "/api/v1/inquiries",
        json={"title": "RFQ-Ø8-PDF", "customer": "华科", "project": "PDF 验收"},
    ).get_json()
    part = client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={"name": "Ø8通孔板", "material": "铝合金"},
    ).get_json()
    upload = client.post(
        "/api/v1/parse-jobs",
        data={"step_file": (BytesIO(MINIMAL_STEP), "plate_hole_d8.step"), "part_id": part["id"]},
        content_type="multipart/form-data",
    ).get_json()
    conn = get_conn(db_path)
    finish_job(conn, upload["job_id"], {
        "geometry": {"volume_cm3": 50.0, "bounding_box_mm": {"x": 80, "y": 60, "z": 12}},
        "features": [
            {
                "type": "hole", "feature_id": "hole-0", "selected": True,
                "diameter_mm": 8, "depth_mm": 12, "hole_type": "through",
                "position_type": "垂直", "cut_depth_mm": 14.4,
            },
            {
                "type": "face", "feature_id": "face-1", "selected": True,
                "length": 80, "width": 60,
            },
        ],
        "drawing": None,
        "warnings": [],
    })
    conn.close()
    quoted_part = client.get(f"/api/v1/parts/{part['id']}").get_json()
    return inquiry["id"], quoted_part


def test_inquiry_quote_pdf_contains_live_o8_quote(client, seeded_db_path):
    inquiry_id, part = _create_o8_inquiry(client, seeded_db_path)
    live_quote = part["quote"]
    amount = live_quote["quote"]["amount"]
    amount_text = f"{amount:g}"
    items = {item["code"]: item["amount"] for item in live_quote["cost_items"]}
    assert items["PROG"] == pytest.approx(62, abs=0.01)
    assert amount < 694.4
    assert live_quote["quote"]["hours"] == 0.1
    assert live_quote["suggested_days"] == 2

    response = client.get(f"/api/v1/inquiries/{inquiry_id}/quote.pdf")

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF-")
    assert "attachment" in response.headers["Content-Disposition"]

    reader = PdfReader(BytesIO(response.data))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    for expected in (
        "询价 ID", "询价标题", "客户", "零件", "材料", "数量",
        "金额", "成本", "毛利", "工时", "建议交期", "成本明细",
        "工艺顺序", "风险扣分", "Ø8通孔板", amount_text, "0.1h", "2 天",
    ):
        assert expected in text
    assert f"amount={amount_text};hours=0.1;suggested_days=2" in reader.metadata["/Keywords"]

    # 导出读取持久化快照，不触发第二套计算或覆盖 live quote。
    after = client.get(f"/api/v1/inquiries/{inquiry_id}").get_json()["parts"][0]["quote"]
    assert after == live_quote


def test_inquiry_quote_pdf_missing_inquiry_is_404(client):
    response = client.get("/api/v1/inquiries/not-found/quote.pdf")
    assert response.status_code == 404
    assert response.get_json()["error"] == "询价单不存在"
