from __future__ import annotations

import pytest

from whatsapp_tracker import create_app


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite3"),
            "UPLOAD_MAX_BYTES": 2 * 1024 * 1024,
            "MAX_CONTENT_LENGTH": (2 * 1024 * 1024) + (64 * 1024),
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()

