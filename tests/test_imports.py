from __future__ import annotations

import io

from tests.helpers import commit_file, import_file, preview_file


def test_preview_reports_valid_invalid_duplicate_and_blank_lines(client):
    response = preview_file(
        client,
        b"0750 123 4567\n+9647501234567\n+971501234567\n\n009647512345678\n",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["valid_count"] == 2
    assert payload["duplicate_count"] == 1
    assert payload["invalid_count"] == 1
    assert payload["blank_count"] == 1
    assert payload["list_revision"] == 0
    assert len(payload["digest"]) == 64


def test_replacement_preserves_matching_state_and_file_order(client):
    first_file = b"07501234567\n+9647512345678\n009647701234567\n"
    import_file(client, first_file)
    initial = client.get("/api/contacts").get_json()
    completed_id = initial["contacts"][0]["id"]
    response = client.patch(
        f"/api/contacts/{completed_id}",
        json={"completed": True},
    )
    assert response.status_code == 200

    replacement = b"7712345678\n9647501234567\n+9647801234567\n+971501234567\n"
    committed = import_file(client, replacement)
    assert committed["imported_count"] == 3
    assert committed["invalid_count"] == 1

    payload = client.get("/api/contacts").get_json()
    assert [item["phone"] for item in payload["contacts"]] == [
        "+9647712345678",
        "+9647501234567",
        "+9647801234567",
    ]
    by_phone = {item["phone"]: item for item in payload["contacts"]}
    assert by_phone["+9647501234567"]["completed"] is True
    assert by_phone["+9647501234567"]["id"] == completed_id
    assert by_phone["+9647712345678"]["completed"] is False
    assert "+9647512345678" not in by_phone


def test_commit_rejects_stale_preview_without_changing_list(client):
    first = b"07501234567\n"
    second = b"07512345678\n"
    first_preview = preview_file(client, first).get_json()
    second_preview = preview_file(client, second).get_json()

    assert commit_file(client, first, first_preview).status_code == 200
    stale_response = commit_file(client, second, second_preview)

    assert stale_response.status_code == 409
    assert stale_response.get_json()["error"] == "stale_import"
    contacts = client.get("/api/contacts").get_json()["contacts"]
    assert [contact["phone"] for contact in contacts] == ["+9647501234567"]


def test_commit_rejects_file_changed_after_preview(client):
    preview = preview_file(client, b"07501234567\n").get_json()

    response = commit_file(client, b"07512345678\n", preview)

    assert response.status_code == 409
    assert response.get_json()["error"] == "file_changed"
    assert client.get("/api/contacts").get_json()["counts"]["total"] == 0


def test_upload_requires_txt_and_enforces_byte_limit(app, client):
    wrong_type = preview_file(client, b"07501234567\n", "numbers.csv")
    assert wrong_type.status_code == 422
    assert wrong_type.get_json()["error"] == "invalid_file_type"

    app.config["UPLOAD_MAX_BYTES"] = 8
    oversized = client.post(
        "/api/imports/preview",
        data={"file": (io.BytesIO(b"07501234567\n"), "numbers.txt")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 422
    assert oversized.get_json()["error"] == "upload_too_large"
