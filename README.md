# WhatsApp Number Tracker

A small Arabic RTL web application for importing a shared list of international phone numbers, opening a prefilled WhatsApp message, and tracking which chats have been opened. State is stored in SQLite and is shared across browsers and devices.

## Important behavior

- Checking a pending number records it as complete on the server, then opens a prefilled `wa.me` link in a new tab.
- A normal WhatsApp link cannot verify that the user pressed **Send**. “Complete” therefore means that the chat was opened, not that WhatsApp delivered the message.
- Re-importing replaces the list, but matching numbers keep their completion state.
- The application intentionally has no authentication. Anyone who can reach it can view and change all phone numbers and statuses. Put it behind HTTPS and add network or reverse-proxy access control if that is not acceptable.

## Number file format

Upload a UTF-8 `.txt` file containing one international number per line:

```text
+989121234567
971501234567
+12025550101
```

The leading `+` is optional. Each number must otherwise contain 7–15 digits and cannot start with zero. Blank lines are ignored; invalid and duplicate lines are shown in the preview and skipped after confirmation. Files are limited to 2 MiB and 20,000 valid unique numbers.

## Run with Docker Compose

```bash
docker compose up --build -d
```

Open `http://SERVER_IP:3001`. To use another host port, set `APP_PORT`:

```bash
APP_PORT=8080 docker compose up --build -d
```

The `tracker-data` named volume contains the SQLite database and survives container recreation. Before production use, terminate HTTPS with the VPS reverse proxy and include this volume in the server backup policy.

Useful operations:

```bash
docker compose ps
docker compose logs -f app
docker compose pull
docker compose up --build -d
```

## Local development

Python 3.12 or later is recommended.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
flask --app whatsapp_tracker run --debug
```

Run the automated tests with:

```bash
pytest
```
