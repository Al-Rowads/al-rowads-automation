from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from tests.helpers import import_file


def test_message_is_shared_between_independent_clients(app):
    first_client = app.test_client()
    second_client = app.test_client()

    response = first_client.put("/api/message", json={"message": "  مرحباً بك  "})

    assert response.status_code == 200
    assert response.get_json()["message"] == "مرحباً بك"
    workspace = second_client.get("/api/contacts").get_json()["workspace"]
    assert workspace["message"] == "مرحباً بك"


def test_message_validation(client):
    assert client.put("/api/message", json={"message": ""}).status_code == 422
    assert client.put("/api/message", json={"message": "x" * 2001}).status_code == 422
    assert client.put("/api/message", json={}).status_code == 400


def test_open_whatsapp_marks_complete_and_encodes_message(client):
    import_file(client, b"0750 123 4567\n")
    client.put("/api/message", json={"message": "مرحباً بك\nكيف حالك؟"})
    contact_id = client.get("/api/contacts").get_json()["contacts"][0]["id"]

    response = client.post(f"/contacts/{contact_id}/open", follow_redirects=False)

    assert response.status_code == 303
    location = response.headers["Location"]
    parsed_url = urlparse(location)
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "wa.me"
    assert parsed_url.path == "/9647501234567"
    assert parse_qs(parsed_url.query)["text"] == ["مرحباً بك\nكيف حالك؟"]
    item = client.get("/api/contacts").get_json()["contacts"][0]
    assert item["completed"] is True
    assert item["completed_at"] is not None


def test_open_without_message_does_not_mark_complete(client):
    import_file(client, b"07501234567\n")
    contact_id = client.get("/api/contacts").get_json()["contacts"][0]["id"]

    response = client.post(f"/contacts/{contact_id}/open")

    assert response.status_code == 422
    assert client.get("/api/contacts").get_json()["contacts"][0]["completed"] is False


def test_uncheck_and_filters_persist(client):
    import_file(client, b"07501234567\n+9647512345678\n009647701234567\n")
    contacts = client.get("/api/contacts").get_json()["contacts"]
    first_id = contacts[0]["id"]
    client.patch(f"/api/contacts/{first_id}", json={"completed": True})

    completed = client.get("/api/contacts?status=completed").get_json()
    pending = client.get("/api/contacts?status=pending&page_size=1").get_json()
    searched = client.get("/api/contacts?q=75123").get_json()

    assert completed["filtered_total"] == 1
    assert completed["contacts"][0]["id"] == first_id
    assert pending["filtered_total"] == 2
    assert len(pending["contacts"]) == 1
    assert searched["filtered_total"] == 1
    assert searched["contacts"][0]["phone"] == "+9647512345678"

    unchecked = client.patch(f"/api/contacts/{first_id}", json={"completed": False})
    assert unchecked.status_code == 200
    assert client.get("/api/contacts").get_json()["counts"] == {
        "completed": 0,
        "pending": 3,
        "total": 3,
    }


def test_health_and_home(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
    home = client.get("/")
    assert home.status_code == 200
    assert 'lang="ar"' in home.get_data(as_text=True)


def test_search_rejects_non_ascii_digits(client):
    response = client.get("/api/contacts?q=٩٨")

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_search"
