"""零件原始工程文件列表与下载接口。"""
from io import BytesIO


STEP_BYTES = (
    b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
    b"ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;"
)
PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


def _create_part(client):
    inquiry = client.post(
        "/api/v1/inquiries",
        json={"customer": "Freeze"},
    ).get_json()
    return client.post(
        f"/api/v1/inquiries/{inquiry['id']}/parts",
        json={"name": "XM8"},
    ).get_json()


def test_part_files_list_and_download_originals(
    client,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "uploads"))
    part = _create_part(client)
    upload = client.post(
        "/api/v1/parse-jobs",
        data={
            "step_file": (BytesIO(STEP_BYTES), "XM8.step"),
            "drawing_file": (BytesIO(PDF_BYTES), "XM8 drawing.pdf"),
            "part_id": part["id"],
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 202

    response = client.get(f"/api/v1/parts/{part['id']}/files")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "role": "drawing",
            "original_name": "XM8 drawing.pdf",
            "size_bytes": len(PDF_BYTES),
            "detected_type": "pdf",
            "content_type": "application/pdf",
        },
        {
            "role": "step",
            "original_name": "XM8.step",
            "size_bytes": len(STEP_BYTES),
            "detected_type": "step",
            "content_type": "model/step",
        },
    ]
    assert "storage_path" not in response.get_data(as_text=True)
    assert "r2://" not in response.get_data(as_text=True)

    for role, expected_bytes, expected_type, expected_name in (
        ("step", STEP_BYTES, "model/step", "XM8.step"),
        ("drawing", PDF_BYTES, "application/pdf", "XM8 drawing.pdf"),
    ):
        download = client.get(f"/api/v1/parts/{part['id']}/files/{role}")
        assert download.status_code == 200
        assert download.data == expected_bytes
        assert download.content_type == expected_type
        assert "attachment" in download.headers["Content-Disposition"]
        assert expected_name in download.headers["Content-Disposition"]


def test_part_file_download_missing_role_is_404(
    client,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("CNCFLOW_FILE_STORAGE", str(tmp_path / "uploads"))
    part = _create_part(client)
    upload = client.post(
        "/api/v1/parse-jobs",
        data={
            "step_file": (BytesIO(STEP_BYTES), "XM8.step"),
            "part_id": part["id"],
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 202

    response = client.get(
        f"/api/v1/parts/{part['id']}/files/drawing",
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "文件不存在"}
