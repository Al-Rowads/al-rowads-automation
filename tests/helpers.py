from __future__ import annotations

import io


def preview_file(client, content: bytes, filename: str = "numbers.txt"):
    return client.post(
        "/api/imports/preview",
        data={"file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def commit_file(client, content: bytes, preview: dict, filename: str = "numbers.txt"):
    return client.post(
        "/api/imports/commit",
        data={
            "file": (io.BytesIO(content), filename),
            "digest": preview["digest"],
            "list_revision": str(preview["list_revision"]),
        },
        content_type="multipart/form-data",
    )


def import_file(client, content: bytes):
    preview_response = preview_file(client, content)
    assert preview_response.status_code == 200
    preview = preview_response.get_json()
    commit_response = commit_file(client, content, preview)
    assert commit_response.status_code == 200
    return commit_response.get_json()

