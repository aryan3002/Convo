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
- Bookings can be identified by phone or email; phone numbers are normalized to E.164 when possible.

## Promotions
Owners can configure promotions via Owner GPT or the `/owner/promos` endpoints. Consumers receive eligible promotions through `/promos/eligible` at defined trigger points.

Endpoints:
- `POST /owner/promos` create a promotion
- `GET /owner/promos` list promotions
- `PATCH /owner/promos/{id}` update a promotion
- `DELETE /owner/promos/{id}` disable a promotion
- `GET /promos/eligible` returns the single eligible promotion for a trigger point

Example payload:
```json
{
  "type": "DAILY_PROMO",
  "trigger_point": "AFTER_EMAIL_CAPTURE",
  "discount_type": "PERCENT",
  "discount_value": 10,
  "constraints_json": {
    "min_spend_cents": 3000,
    "valid_days_of_week": [0,1,2,3,4]
  },
  "custom_copy": "Save {discount} on your first visit!",
  "active": true,
  "priority": 1
}
```

## Preferred style per service
Customers can save a preferred style (text and/or image URL) per service. Use Cloudinary for image uploads.

Endpoints:
- `POST /uploads/style-image` upload an image and get `{ "image_url": "..." }`
- `GET /customers/{email}/preferences?service_id=...` get a saved preference
- `PUT /customers/{email}/preferences` upsert a preference

Env vars:
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_UPLOAD_PRESET`
- `CLOUDINARY_API_KEY` (optional for unsigned uploads)

## Twilio Voice (Local)
1) Run the backend:
```bash
uvicorn Backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

2) Start ngrok:
```bash
ngrok http 8000
```

3) In Twilio Console, set the Voice webhook to:
```
https://<YOUR_NGROK_SUBDOMAIN>.ngrok-free.dev/twilio/voice
```

The gather webhook is handled automatically by the backend at `/twilio/gather`.

## Embeddings / Vector Search (Feature Flag)

The backend includes semantic search over call transcripts using pgvector. This feature is **disabled by default** to allow running without pgvector installed.

### Running Without pgvector (Default)

By default, `ENABLE_EMBEDDINGS=False`:
- The app starts normally without pgvector
- `embedded_chunks` table is NOT created
- All vector search functions return empty results (no-ops)
- RAG queries return "feature not enabled" messages
- All other features work normally

This is the recommended mode for:
- Local development without pgvector
- Migrations to new databases (e.g., Neon)
- Testing non-vector features

### Enabling Embeddings (Phase 8)

To enable vector search:

1) Install pgvector extension in Postgres:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

2) Set environment variable:
```bash
export ENABLE_EMBEDDINGS=true
```

3) Install the Python pgvector package:
```bash
pip install pgvector
```

4) Restart the app - `embedded_chunks` table will be auto-created

When enabled:
- Call transcripts are automatically chunked and embedded
- Owner GPT can search call history semantically
- RAG provides grounded answers with citations

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_EMBEDDINGS` | `false` | Enable pgvector semantic search |
| `OPENAI_API_KEY` | - | Required for embeddings when enabled |

