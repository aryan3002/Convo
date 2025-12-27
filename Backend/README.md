# Convo Backend (FastAPI)

FastAPI + Postgres backend for the booking MVP. Endpoints match the frontend expectations at `http://localhost:8000`.

## Setup
1) Start Postgres (Docker):
```bash
docker compose up -d
```
Postgres will be available at `localhost:55432` based on `docker-compose.yml`.

2) Create a virtualenv and install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r Backend/requirements.txt
```

3) Configure environment:
```bash
cp Backend/.env.example Backend/.env  # adjust if needed
```

4) Run the server:
```bash
uvicorn Backend.app.main:app --reload --port 8000
```

Visit docs: http://localhost:8000/docs

## Notes
- CORS allows `http://localhost:3000` by default for the Next.js frontend.
- Tables auto-create on startup; seed data loads if empty (services + stylists for Bishops Tempe).
- Hold TTL defaults to 5 minutes; working hours default to 09:00–17:00 (local time per `tz_offset_minutes`).
- Working days default to Tuesday–Sunday (`WORKING_DAYS=1,2,3,4,5,6`).
- Times are stored in UTC; holds and confirmed bookings block overlapping slots. Confirm will fail if a hold expired.
- Chat uses `CHAT_TIMEZONE` (default `America/Phoenix`) and logs to `CHAT_LOG_PATH` when set.
