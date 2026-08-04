from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from . import db
from .routes import bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    upload_max_bytes = 2 * 1024 * 1024
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "DATABASE",
            str(Path(app.instance_path) / "tracker.sqlite3"),
        ),
        UPLOAD_MAX_BYTES=upload_max_bytes,
        MAX_CONTENT_LENGTH=upload_max_bytes + (64 * 1024),
        MAX_CONTACTS=20_000,
        JSON_SORT_KEYS=False,
    )

    if test_config is not None:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.init_db()

    app.register_blueprint(bp)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error: RequestEntityTooLarge):
        message = "حجم الملف يتجاوز الحد الأقصى المسموح به (2 ميجابايت)."
        if request.path.startswith("/api/"):
            return jsonify(error="upload_too_large", message=message), 413
        return message, 413

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    return app

