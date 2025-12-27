# Convo Backend (FastAPI)

FastAPI + Postgres backend for the booking MVP. Endpoints match the frontend expectations at `http://localhost:8000`.

## Setup
1) Start Postgres (Docker):
```bash
docker compose up -d
```

2) Create a virtualenv and install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

3) Configure environment:
```bash
cp backend/.env.example backend/.env  # adjust if needed
```

4) Run the server:
```bash
uvicorn backend.app.main:app --reload --port 8000
```

Visit docs: http://localhost:8000/docs

## Notes
- CORS allows `http://localhost:3000` by default for the Next.js frontend.
- Tables auto-create on startup; seed data loads if empty (services + stylists for Bishops Tempe).
- Hold TTL defaults to 5 minutes; working hours 09:00–17:00 (local time per `tz_offset_minutes`).
- Times are stored in UTC; holds and confirmed bookings block overlapping slots. Confirm will fail if a hold expired.
