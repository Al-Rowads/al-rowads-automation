from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import click
from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    message TEXT NOT NULL DEFAULT '',
    list_revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL UNIQUE,
    position INTEGER NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    completed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS contacts_position_idx ON contacts(position);
CREATE INDEX IF NOT EXISTS contacts_completed_idx ON contacts(completed, position);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        g.db = connection
    return g.db


def close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    connection = get_db()
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    connection.execute(
        """
        INSERT INTO workspace (id, message, list_revision, updated_at)
        VALUES (1, '', 0, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (utc_now(),),
    )
    connection.commit()


@click.command("init-db")
def init_db_command() -> None:
    init_db()
    click.echo("Initialized the database.")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

