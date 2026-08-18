from __future__ import annotations

import io
import sqlite3

import pytest
from PIL import Image

from tests.helpers import import_file
from whatsapp_tracker import create_app


def photo_bytes(
    image_format: str = "PNG",
    *,
    size: tuple[int, int] = (40, 24),
    exif_orientation: int | None = None,
) -> bytes:
    image = Image.new("RGB", size, "#1c9b69")
    output = io.BytesIO()
    options = {}
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[274] = exif_orientation
        options["exif"] = exif
    image.save(output, format=image_format, **options)
    return output.getvalue()


def save_template(
    client,
    *,
    message: str = "مرحباً بك",
    photo_action: str = "keep",
    photo: bytes | None = None,
    filename: str = "photo.png",
):
    data = {"message": message, "photo_action": photo_action}
    if photo is not None:
        data["photo"] = (io.BytesIO(photo), filename)
    return client.put(
        "/api/message-template",
        data=data,
        content_type="multipart/form-data",
    )


@pytest.mark.parametrize(
    ("image_format", "filename"),
    [("JPEG", "photo.jpg"), ("PNG", "photo.png"), ("WEBP", "photo.webp")],
)
def test_template_accepts_supported_photos_and_serves_png(client, image_format, filename):
    response = save_template(
        client,
        message="  أهلاً وسهلاً  ",
        photo_action="replace",
        photo=photo_bytes(image_format),
        filename=filename,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["message"] == "أهلاً وسهلاً"
    assert payload["photo"]["width"] == 40
    assert payload["photo"]["height"] == 24
    assert payload["photo"]["url"].startswith("/api/message-photo?v=")

    inline = client.get(payload["photo"]["url"])
    assert inline.status_code == 200
    assert inline.mimetype == "image/png"
    assert inline.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert inline.headers["Content-Disposition"].startswith("inline;")
    assert inline.headers["Cache-Control"] == "private, no-cache"

    cached = client.get(
        payload["photo"]["url"],
        headers={"If-None-Match": inline.headers["ETag"]},
    )
    assert cached.status_code == 304

    download = client.get(payload["photo"]["download_url"])
    assert download.headers["Content-Disposition"].startswith("attachment;")


def test_photo_is_oriented_resized_and_exposed_in_workspace(client):
    response = save_template(
        client,
        photo_action="replace",
        photo=photo_bytes("JPEG", size=(2_000, 1_000), exif_orientation=6),
        filename="rotated.jpg",
    )

    assert response.status_code == 200
    assert response.get_json()["photo"]["width"] == 800
    assert response.get_json()["photo"]["height"] == 1_600
    workspace = client.get("/api/contacts").get_json()["workspace"]
    assert workspace["photo"] == response.get_json()["photo"]
    served = client.get(workspace["photo"]["url"])
    with Image.open(io.BytesIO(served.data)) as image:
        assert image.getexif() == {}


def test_invalid_photo_does_not_partially_update_template(client):
    saved = save_template(
        client,
        message="النص الأصلي",
        photo_action="replace",
        photo=photo_bytes(),
    ).get_json()

    rejected = save_template(
        client,
        message="نص لا يجب حفظه",
        photo_action="replace",
        photo=b"not an image",
        filename="broken.png",
    )

    assert rejected.status_code == 422
    assert rejected.get_json()["error"] == "invalid_photo"
    workspace = client.get("/api/contacts").get_json()["workspace"]
    assert workspace["message"] == "النص الأصلي"
    assert workspace["photo"]["url"] == saved["photo"]["url"]


def test_template_can_keep_and_remove_photo(client):
    first = save_template(
        client,
        photo_action="replace",
        photo=photo_bytes(),
    ).get_json()

    kept = save_template(client, message="نص جديد", photo_action="keep")
    assert kept.status_code == 200
    assert kept.get_json()["photo"]["url"] == first["photo"]["url"]

    legacy_update = client.put("/api/message", json={"message": "تحديث متوافق"})
    assert legacy_update.status_code == 200
    workspace = client.get("/api/contacts").get_json()["workspace"]
    assert workspace["photo"]["url"] == first["photo"]["url"]

    removed = save_template(client, message="نص أخير", photo_action="remove")
    assert removed.status_code == 200
    assert removed.get_json()["photo"] is None
    assert client.get("/api/message-photo").status_code == 404


def test_template_rejects_missing_invalid_and_oversized_photo(app, client):
    missing = save_template(client, photo_action="replace")
    assert missing.status_code == 400
    assert missing.get_json()["error"] == "missing_photo"

    action = save_template(client, photo_action="unknown")
    assert action.status_code == 400
    assert action.get_json()["error"] == "invalid_photo_action"

    app.config["PHOTO_UPLOAD_MAX_BYTES"] = 8
    oversized = save_template(
        client,
        photo_action="replace",
        photo=b"123456789",
    )
    assert oversized.status_code == 413
    assert oversized.get_json()["error"] == "photo_too_large"


def test_template_rejects_animation_and_excessive_dimensions(app, client):
    first = Image.new("RGB", (10, 10), "red")
    second = Image.new("RGB", (10, 10), "blue")
    animated = io.BytesIO()
    first.save(animated, format="PNG", save_all=True, append_images=[second], duration=100)

    animation_response = save_template(
        client,
        photo_action="replace",
        photo=animated.getvalue(),
    )
    assert animation_response.status_code == 422
    assert animation_response.get_json()["error"] == "animated_photo"

    app.config["PHOTO_MAX_PIXELS"] = 100
    dimensions_response = save_template(
        client,
        photo_action="replace",
        photo=photo_bytes(size=(11, 10)),
    )
    assert dimensions_response.status_code == 422
    assert dimensions_response.get_json()["error"] == "photo_dimensions_too_large"


def test_prepare_page_does_not_complete_contact_until_open(client):
    import_file(client, b"07501234567\n")
    save_template(
        client,
        message="مرحباً من القالب",
        photo_action="replace",
        photo=photo_bytes(),
    )
    contact_id = client.get("/api/contacts").get_json()["contacts"][0]["id"]

    prepared = client.get(f"/contacts/{contact_id}/prepare")

    assert prepared.status_code == 200
    html = prepared.get_data(as_text=True)
    assert "نسخ الصورة وفتح واتساب" in html
    assert "مرحباً من القالب" in html
    assert client.get("/api/contacts").get_json()["contacts"][0]["completed"] is False

    opened = client.post(f"/contacts/{contact_id}/open")
    assert opened.status_code == 303
    assert client.get("/api/contacts").get_json()["contacts"][0]["completed"] is True


def test_prepare_page_falls_back_when_photo_was_removed(client):
    import_file(client, b"07501234567\n")
    save_template(client, message="رسالة نصية", photo_action="keep")
    contact_id = client.get("/api/contacts").get_json()["contacts"][0]["id"]

    response = client.get(f"/contacts/{contact_id}/prepare")

    assert response.status_code == 200
    assert "فتح واتساب" in response.get_data(as_text=True)


def test_existing_database_gains_photo_table_without_data_loss(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE workspace (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message TEXT NOT NULL DEFAULT '',
            list_revision INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO workspace VALUES (1, 'رسالة قديمة', 7, '2026-01-01T00:00:00+00:00')"
    )
    connection.commit()
    connection.close()

    app = create_app({"TESTING": True, "DATABASE": str(database)})

    with app.app_context():
        connection = sqlite3.connect(database)
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        workspace = connection.execute(
            "SELECT message, list_revision FROM workspace WHERE id = 1"
        ).fetchone()
        connection.close()
    assert "workspace_photo" in tables
    assert workspace == ("رسالة قديمة", 7)
