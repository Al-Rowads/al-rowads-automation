from __future__ import annotations

import sqlite3
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from .db import get_db, utc_now
from .parsing import ParseResult, UploadValidationError, parse_numbers_file


bp = Blueprint("tracker", __name__)
ISSUE_DETAIL_LIMIT = 200


def json_error(code: str, message: str, status: int):
    return jsonify(error=code, message=message), status


def read_uploaded_file() -> tuple[bytes, ParseResult]:
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise UploadValidationError("missing_file", "اختر ملف أرقام بصيغة TXT.")
    if not upload.filename.lower().endswith(".txt"):
        raise UploadValidationError("invalid_file_type", "يُسمح بملفات TXT فقط.")

    limit = current_app.config["UPLOAD_MAX_BYTES"]
    raw = upload.stream.read(limit + 1)
    if len(raw) > limit:
        raise UploadValidationError(
            "upload_too_large",
            "حجم الملف يتجاوز الحد الأقصى المسموح به (2 ميجابايت).",
        )
    return raw, parse_numbers_file(raw, current_app.config["MAX_CONTACTS"])


def parse_positive_integer(value: str | None, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError from error
    if parsed < 1 or parsed > maximum:
        raise ValueError
    return parsed


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/healthz")
def health():
    get_db().execute("SELECT 1").fetchone()
    return jsonify(status="ok")


@bp.get("/api/contacts")
def contacts():
    try:
        page = parse_positive_integer(request.args.get("page"), 1, 1_000_000)
        page_size = parse_positive_integer(request.args.get("page_size"), 100, 200)
    except ValueError:
        return json_error("invalid_pagination", "قيم ترقيم الصفحات غير صالحة.", 400)

    status = request.args.get("status", "all")
    if status not in {"all", "pending", "completed"}:
        return json_error("invalid_status", "عامل تصفية الحالة غير صالح.", 400)

    search = request.args.get("q", "").strip().removeprefix("+")
    if search and (not search.isascii() or not search.isdigit()):
        return json_error("invalid_search", "ابحث باستخدام الأرقام فقط.", 400)

    conditions: list[str] = []
    parameters: list[object] = []
    if search:
        conditions.append("substr(phone, 2) LIKE ?")
        parameters.append(f"%{search}%")
    if status == "pending":
        conditions.append("completed = 0")
    elif status == "completed":
        conditions.append("completed = 1")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    connection = get_db()
    workspace = connection.execute(
        "SELECT message, list_revision, updated_at FROM workspace WHERE id = 1"
    ).fetchone()
    counts = connection.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(completed = 0), 0) AS pending,
               COALESCE(SUM(completed = 1), 0) AS completed
        FROM contacts
        """
    ).fetchone()
    filtered_total = connection.execute(
        f"SELECT COUNT(*) FROM contacts {where_clause}", parameters
    ).fetchone()[0]
    offset = (page - 1) * page_size
    rows = connection.execute(
        f"""
        SELECT id, phone, position, completed, completed_at, created_at
        FROM contacts
        {where_clause}
        ORDER BY position
        LIMIT ? OFFSET ?
        """,
        [*parameters, page_size, offset],
    ).fetchall()

    return jsonify(
        workspace=dict(workspace),
        counts=dict(counts),
        filtered_total=filtered_total,
        page=page,
        page_size=page_size,
        contacts=[
            {
                **dict(row),
                "completed": bool(row["completed"]),
            }
            for row in rows
        ],
    )


@bp.put("/api/message")
def update_message():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
        return json_error("invalid_message", "نص الرسالة مطلوب.", 400)

    message = payload["message"].strip()
    if not message or len(message) > 2_000:
        return json_error(
            "invalid_message",
            "يجب أن يتراوح نص الرسالة بين حرف واحد و2000 حرف.",
            422,
        )

    updated_at = utc_now()
    connection = get_db()
    connection.execute(
        "UPDATE workspace SET message = ?, updated_at = ? WHERE id = 1",
        (message, updated_at),
    )
    connection.commit()
    return jsonify(message=message, updated_at=updated_at)


@bp.post("/api/imports/preview")
def preview_import():
    try:
        _raw, parsed = read_uploaded_file()
    except UploadValidationError as error:
        return json_error(error.code, error.message, 422)

    revision = get_db().execute(
        "SELECT list_revision FROM workspace WHERE id = 1"
    ).fetchone()[0]
    return jsonify({**import_summary(parsed), "list_revision": revision})


@bp.post("/api/imports/commit")
def commit_import():
    try:
        _raw, parsed = read_uploaded_file()
    except UploadValidationError as error:
        return json_error(error.code, error.message, 422)

    expected_digest = request.form.get("digest", "")
    if expected_digest != parsed.digest:
        return json_error(
            "file_changed",
            "تغيّر الملف بعد المعاينة. عاين الملف مرة أخرى.",
            409,
        )
    try:
        expected_revision = int(request.form["list_revision"])
    except (KeyError, ValueError):
        return json_error("missing_revision", "رقم مراجعة القائمة مطلوب.", 400)

    connection = get_db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        current_revision = connection.execute(
            "SELECT list_revision FROM workspace WHERE id = 1"
        ).fetchone()[0]
        if current_revision != expected_revision:
            connection.rollback()
            return json_error(
                "stale_import",
                "استُبدلت القائمة من جهاز آخر. عاين الملف مرة أخرى.",
                409,
            )

        connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS imported_contacts "
            "(phone TEXT PRIMARY KEY, position INTEGER NOT NULL)"
        )
        connection.execute("DELETE FROM imported_contacts")
        connection.executemany(
            "INSERT INTO imported_contacts (phone, position) VALUES (?, ?)",
            ((phone, position) for position, phone in enumerate(parsed.numbers, start=1)),
        )
        now = utc_now()
        # Free the positive position range before inserting the replacement rows.
        # Existing IDs and their completion state remain intact for matching phones.
        connection.execute("UPDATE contacts SET position = -id")
        connection.execute(
            """
            INSERT INTO contacts (phone, position, completed, completed_at, created_at)
            SELECT imported.phone, imported.position, 0, NULL, ?
            FROM imported_contacts AS imported
            WHERE NOT EXISTS (
                SELECT 1 FROM contacts WHERE contacts.phone = imported.phone
            )
            """,
            (now,),
        )
        connection.execute(
            """
            DELETE FROM contacts
            WHERE NOT EXISTS (
                SELECT 1 FROM imported_contacts WHERE imported_contacts.phone = contacts.phone
            )
            """
        )
        connection.execute(
            """
            UPDATE contacts
            SET position = (
                SELECT position FROM imported_contacts
                WHERE imported_contacts.phone = contacts.phone
            )
            """
        )
        new_revision = current_revision + 1
        connection.execute(
            "UPDATE workspace SET list_revision = ?, updated_at = ? WHERE id = 1",
            (new_revision, now),
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        current_app.logger.exception("Failed to replace the contacts list")
        return json_error(
            "database_error",
            "تعذّر استبدال القائمة. لم يتم تغيير البيانات الحالية.",
            500,
        )

    return jsonify(
        imported_count=len(parsed.numbers),
        list_revision=new_revision,
        invalid_count=parsed.invalid_count,
        duplicate_count=parsed.duplicate_count,
    )


@bp.patch("/api/contacts/<int:contact_id>")
def update_contact(contact_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("completed"), bool):
        return json_error("invalid_state", "حالة الرقم غير صالحة.", 400)

    completed = payload["completed"]
    completed_at = utc_now() if completed else None
    connection = get_db()
    cursor = connection.execute(
        "UPDATE contacts SET completed = ?, completed_at = ? WHERE id = ?",
        (int(completed), completed_at, contact_id),
    )
    if cursor.rowcount == 0:
        return json_error("contact_not_found", "الرقم غير موجود.", 404)
    connection.commit()
    return jsonify(id=contact_id, completed=completed, completed_at=completed_at)


@bp.post("/contacts/<int:contact_id>/open")
def open_whatsapp(contact_id: int):
    connection = get_db()
    row = connection.execute(
        """
        SELECT contacts.phone, workspace.message
        FROM contacts CROSS JOIN workspace
        WHERE contacts.id = ? AND workspace.id = 1
        """,
        (contact_id,),
    ).fetchone()
    if row is None:
        return render_template(
            "error.html",
            title="الرقم غير موجود",
            message="ربما استُبدلت القائمة من جهاز آخر.",
        ), 404
    if not row["message"].strip():
        return render_template(
            "error.html",
            title="لم تُحفظ الرسالة",
            message="احفظ نص الرسالة قبل فتح واتساب.",
        ), 422

    connection.execute(
        "UPDATE contacts SET completed = 1, completed_at = ? WHERE id = ?",
        (utc_now(), contact_id),
    )
    connection.commit()
    phone = row["phone"].removeprefix("+")
    whatsapp_url = f"https://wa.me/{phone}?text={quote(row['message'], safe='')}"
    return redirect(whatsapp_url, code=303)


def import_summary(parsed: ParseResult) -> dict:
    visible_issues = parsed.issues[:ISSUE_DETAIL_LIMIT]
    return {
        "digest": parsed.digest,
        "valid_count": len(parsed.numbers),
        "invalid_count": parsed.invalid_count,
        "duplicate_count": parsed.duplicate_count,
        "blank_count": parsed.blank_count,
        "issues": [
            {
                "line": issue.line,
                "value": issue.value,
                "reason": issue.reason,
            }
            for issue in visible_issues
        ],
        "issues_truncated": len(parsed.issues) > ISSUE_DETAIL_LIMIT,
    }
