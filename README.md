<div align="center">

# Convo
Convo' Product - neev.convoaiservices.com

### The 24/7 AI front desk for local service businesses.

**One AI receptionist. Five channels. Two verticals. Zero phone tag.**

Chat · Voice · WhatsApp · ChatGPT Plugin · Owner Dashboard

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-RAG-blueviolet)](https://github.com/pgvector/pgvector)
[![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini-412991?logo=openai&logoColor=white)](https://openai.com/)
[![Twilio](https://img.shields.io/badge/Twilio-Voice%2BSMS%2BWhatsApp-F22F46?logo=twilio&logoColor=white)](https://www.twilio.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=next.js)](https://nextjs.org/)
[![Clerk](https://img.shields.io/badge/Auth-Clerk-6C47FF)](https://clerk.com/)
[![Status](https://img.shields.io/badge/status-active%20build-success)]()

</div>

---

## What Convo Is

Most local service businesses still answer the phone to take bookings. The result: missed calls, no-shows, double-bookings, and a front-desk job nobody wants.

Convo is the AI receptionist that replaces it. Customers reach the business through whatever channel they prefer — a text, a phone call, a WhatsApp message, even a ChatGPT search — and Convo books them in. The same tenant context. The same calendar. The same booking state.

The owner gets a dashboard with every conversation transcribed, every booking logged, every customer remembered.

> *Not a chatbot. A front desk that happens to be made of language models.*

---

## Two Verticals, One Engine

Convo is built around a **shared multi-tenant platform** with vertical-specific data models layered on top:

| Vertical | What gets booked | Pricing | Channels |
|---|---|---|---|
| 💇 **Salons / Barbershops** | Appointments by service + stylist + slot | Static service price + tip | Chat, Voice (Twilio), WhatsApp, ChatGPT Plugin, Web |
| 🚖 **Cab Owners / Drivers** | Rides with pickup, drop-off, vehicle assignment | **Dynamic** by distance, time-of-day, demand | Web, WhatsApp, Phone, ChatGPT Plugin |

This isn't two apps glued together — it's one tenant-resolved engine with distinct data tables, pricing logic, and booking flows per vertical.

---

## The Five Channels — All Land in the Same Booking State

```
                        ┌────────────────────────────────────┐
   💬 Web Chat   ───►   │                                    │
   📞 Phone     ───►   │       Convo Backend (FastAPI)      │
   📱 WhatsApp  ───►   │     ShopContext  → Booking State   │  ───► PostgreSQL 16 + pgvector
   🤖 ChatGPT   ───►   │       (Async, Tenant-Scoped)       │
   🌐 Dashboard ───►   │                                    │
                        └────────────────────────────────────┘
                                       │
                                       ▼
                            Twilio · OpenAI · Google Maps · Clerk · Resend
```

A customer who starts in WhatsApp, calls back later, and confirms via ChatGPT will land on the **same booking** — Convo resolves identity by phone, email, and shop scope.

---

## AI / LLM Stack

| Workflow | Module | Model | What it does |
|---|---|---|---|
| **Customer chat** | `chat.py` (890 LOC) | gpt-4o-mini | Structured action dispatch: service selection, slot holding, booking confirmation, promo injection, style preference capture |
| **Owner chat** | `owner_chat.py` + `owner_actions.py` | gpt-4o-mini | Natural-language management — create/edit services, modify schedules, manage promos, lookup customers |
| **Call summarization** | `call_summary.py` | gpt-4o-mini | Fire-and-forget post-call task → structured JSON (customer, service, stylist, time, notes) → `call_summaries` table |
| **RAG / semantic search** | `rag.py`, `rag_enhanced.py`, `vector_search.py` (834 LOC) | text-embedding-3-small | pgvector store, recency + relevance ranking, hallucination detection, source attribution |
| **ChatGPT Plugin / Custom GPT** | `public_booking.py` (1,301 LOC) | gpt-4o-mini via OpenAPI | Full OpenAPI spec (`openapi_chatgpt.yaml`) exposes booking as GPT function-calling tools |
| **RouterGPT discovery layer** | `router_gpt.py` (872 LOC) | gpt-4o-mini + geo | Global ChatGPT entry — fuzzy business search, geo-proximity ranking, shop handoff/delegation, analytics |

**Embeddings:** 1,536-dim vectors stored in Postgres via `pgvector 0.3.6` — no separate vector DB. Owners can semantically query "did anyone complain about hair color last week?" against months of call transcripts.

---

## The Voice Agent — A Deliberate Engineering Bet

**Architecture:** Deterministic state machine. **Zero LLM calls per turn.**

```
GET_IDENTITY  →  GET_SERVICE  →  GET_DATE  →  GET_TIME_AND_STYLIST  →  HOLD_SLOT  →  CONFIRM  →  DONE
```

This is a defensible choice, not a default. Most "AI phone agent" demos call GPT every conversation turn — they're slow, expensive, and unreliable for telephony. Convo's voice IVR runs on Twilio TwiML + Amazon Polly (Joanna) and uses:

- **Regex-based speech extraction** for phone numbers (spoken digits), names (filler-word filtering), dates (today/tomorrow/day-of-week/explicit), times (morning/afternoon/evening/clock)
- **`fuzzy_match_service()`** with strict gender-aware rules ("haircut" matches both Men's and Women's services — `SequenceMatcher` alone fails here, so a keyword-priority override layer was added)
- **`fuzzy_match_stylist()`** — same approach for staff matching
- **In-memory `CALL_SESSIONS` dict** keyed by Twilio CallSid, 30-min TTL — trades stateless-restart safety for zero-latency reads during active calls (correct trade for short-lived phone sessions)
- **Twilio `RequestValidator` signature check** on every webhook
- **Shop resolution** by incoming Twilio "To" number → `shop_phone_numbers` table → tenant context
- **Post-call:** transcript collected per-turn → `asyncio.create_task()` fires GPT summarization after hangup so TwiML response is never blocked

**LLM only fires once per call** — for the summary, *after* hangup. That's the single most important architectural decision in the system.

---

## Multi-Tenancy — Five Shop Resolution Strategies

Every request resolves to a single `ShopContext` dataclass (frozen / immutable) injected as a FastAPI dependency:

| Strategy | Use case |
|---|---|
| URL slug `/s/{slug}/` | Web dashboard, scoped API routes |
| Twilio "To" phone number | Inbound voice + SMS + WhatsApp |
| SHA-256 API key hash | Server-to-server, ChatGPT Plugin |
| Clerk JWT `org_id` | Owner/manager portal |
| Subdomain | Scaffolded for future white-label |

**No PostgreSQL RLS.** Instead, every query in the scoped router (`routes_scoped.py` — 4,529 LOC) is enforced to include `WHERE shop_id = ?` from context. Trade: less defense-in-depth, but much simpler reasoning and faster query plans.

**Cross-tenant model:** the `customers` table is global (by email/phone), but `customer_shop_profiles` and `customer_stylist_preferences` isolate per-shop behavior — customers can exist across multiple shops without bleeding preferences.

**RBAC:** `shop_members` table with `OWNER` / `MANAGER` / `EMPLOYEE` roles. Auth splits:
- **Clerk JWT** for owners and managers
- **PIN-hash sessions** (`PyJWT` + `cryptography`) for stylists / employees

**Audit trail:** `audit_logs` table records actor, action, target, and JSON metadata for every significant mutation.

---

## Engineering Judgment Calls (the interesting stuff)

These are the design decisions that separate Convo from a generic "AI chatbot" project:

| Decision | Why it matters |
|---|---|
| **Deterministic voice IVR over LLM** | Eliminates latency, reduces cost, improves reliability for phone UX. LLM fires once post-call for summarization. |
| **Fire-and-forget async call summaries** | `asyncio.create_task()` after hangup so TwiML response never blocks. Call logs remain fast regardless of GPT latency. |
| **In-memory voice sessions with TTL pruning** | Accepted stateless-restart risk for zero-latency reads during active calls. Right trade for short-lived phone sessions. |
| **Geocoding cache layer** | `CachedGeocoder` wraps Google Maps with a DB-backed `geocoding_cache` table — prevents repeated paid API calls for the same address. |
| **Gender-aware fuzzy service matching** | `SequenceMatcher` alone matches "haircut" to both Men's and Women's — added a keyword-priority override layer. |
| **Event-driven promo trigger system** | 5 lifecycle trigger points (`AT_CHAT_START`, `AFTER_EMAIL_CAPTURE`, etc.) with daily impression dedup via `(identity_key, day_bucket)` composite key. Same user same day never sees the same promo twice. |
| **Async all the way down** | `asyncpg` + `AsyncSQLAlchemy` + `AsyncOpenAI` + `httpx`. No blocking calls in the hot path — handles concurrent voice + chat + webhooks without thread contention. |
| **Raw SQL migrations over ORM migrations** | 15 progressive SQL files. More transparent, easier to review, avoids Alembic footguns in early-stage product. |

---

## Full Tech Stack

### Backend

| Layer | Choice | Version |
|---|---|---|
| Framework | FastAPI (async) | 0.115.6 |
| Server | Uvicorn | — |
| Database | PostgreSQL | 16 |
| Driver | asyncpg | 0.29.0 |
| ORM | SQLAlchemy (async) | 2.0 |
| Validation | Pydantic (v2) + Pydantic Settings | — |
| Vector store | pgvector | 0.3.6 |
| LLM | OpenAI Python SDK (gpt-4o-mini + text-embedding-3-small) | 1.61.0 |
| Telephony | Twilio SDK (Voice/IVR, SMS, WhatsApp) | 9.2.2 |
| Token counting | tiktoken | 0.8.0 |
| Auth/Crypto | PyJWT + cryptography | 2.9.0 / 42.0.5 |
| HTTP client | httpx (async) | 0.27.2 |
| Email | Resend API | — |
| Geocoding | Google Maps API + DB cache | — |
| Testing | pytest + pytest-asyncio (13 test modules) | — |

### Frontend

| Layer | Choice |
|---|---|
| Framework | Next.js 16.1.1 (App Router) |
| UI | React 19 + TypeScript 5 |
| Styling | Tailwind CSS v4 |
| Animation | Framer Motion 12 |
| Auth | @clerk/nextjs 6 |
| Icons | Lucide React |

### Infrastructure

- Docker Compose (local Postgres 16-alpine)
- Vercel (Next.js deployment)
- 12-factor env config via Pydantic Settings
- Self-hosted backend (FastAPI + Uvicorn)

---

## Architecture (high-level)

```
backend/
├── app/
│   ├── main.py                    ← 50+ global routes (public, health, webhooks)
│   ├── routes_scoped.py           ← 30+ tenant-scoped routes under /s/{slug}/...  (4,529 LOC)
│   ├── tenancy/                   ← ShopContext + 5 resolution strategies
│   ├── services/                  ← 36 Python modules, one concern per file
│   │   ├── chat.py                ← Customer chat (890 LOC)
│   │   ├── owner_chat.py
│   │   ├── owner_actions.py
│   │   ├── voice.py               ← Voice IVR state machine
│   │   ├── call_summary.py        ← Post-call summarization
│   │   ├── rag.py / rag_enhanced.py / vector_search.py (834 LOC)
│   │   ├── public_booking.py      ← ChatGPT Plugin (1,301 LOC)
│   │   ├── router_gpt.py          ← RouterGPT discovery (872 LOC)
│   │   ├── cab_booking.py         ← Cab vertical
│   │   ├── whatsapp.py            ← WhatsApp dispatch
│   │   └── ...
│   └── db/
│       └── 24 tables, 15 raw SQL migrations
└── tests/
    └── 13 test modules

frontend/
├── src/
│   ├── app/                       ← 6 Next.js App Router pages
│   ├── components/                ← 40+ React components
│   ├── hooks/                     ← 9 custom hooks
│   └── lib/
│       ├── api.client.ts          ← Browser-facing API
│       └── api.server.ts          ← Server-component API (Edge-ready)
```

---

## Scale Signals

| Dimension | Count |
|---|---|
| Python modules | **36** |
| Backend LOC | **~28,500** |
| API endpoints | **138+** |
| Database tables | **24** |
| DB migrations (raw SQL) | **15** |
| React components | **40+** |
| Custom React hooks | **9** |
| Frontend pages | **6** |
| Voice IVR stages | **7** |
| LLM integration points | **6 distinct workflows** |
| Promo trigger lifecycle points | **5** |
| Shop resolution methods | **5** |
| Test modules | **13** |
| External API integrations | **5** (OpenAI, Twilio, Google Maps, Clerk, Resend) |

---

## What Makes This Worthy

- **Two production verticals** with distinct data models, pricing logic, and booking flows — not a demo, not a CRUD app.
- **Multi-channel delivery** — the same booking intent is handled identically across chat UI, Twilio voice call, WhatsApp, and ChatGPT Plugin, with shared tenant context and booking state.
- **Voice agent with no LLM per turn** — a deliberate, defensible architecture that separates Convo from "slap GPT on a phone call" demos. Shows latency and cost reasoning.
- **RouterGPT discovery layer** — positions Convo as a *ChatGPT-native booking network*, not just a standalone tool. The handoff / delegation pattern enables a marketplace model.
- **RAG on call transcripts** — owners can semantically query their call history. High-value enterprise feature built on commodity pgvector infrastructure.
- **Audit logging + RBAC + rate limiting** — security/compliance layer that most side projects skip entirely.
- **Async-first Python backend** — not retrofitted. `asyncpg` + `AsyncSQLAlchemy` + FastAPI means this handles concurrent voice sessions, chat, and webhook processing without thread contention.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker (for Postgres 16)
- API keys: OpenAI, Twilio, Clerk, Google Maps, Resend

### Backend

```bash
cd Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start Postgres 16 + pgvector
docker compose up -d

# Apply raw SQL migrations
make migrate

# Run dev server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### Environment

Copy `.env.example` → `.env` in both `Backend/` and `frontend/`. Required vars include:
`OPENAI_API_KEY`, `DATABASE_URL`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `CLERK_SECRET_KEY`, `GOOGLE_MAPS_API_KEY`, `RESEND_API_KEY`.

---

## Companion Project

**[Marketing site](https://github.com/aryan3002/Convo_website)** — the public-facing Next.js marketing site for Convo at [convoaiservices.com](https://www.convoaiservices.com). Neon-cyberpunk design system, 13 pages, SEO landing pages, Lighthouse-optimized.

---

## Status

**Active build.** This is a real product in development, not a demo. Features, architecture, and implementation continue to evolve.

The public website at [convoaiservices.com](https://www.convoaiservices.com) is a *showcase* of the product — not the full production application. This repo contains the actual backend, AI workflows, voice agent, scheduling logic, and integrations.

---

## About the Author

**Aryan Tripathi** — CS Senior at Arizona State University (May 2026), 4+1 MS CS candidate (AI concentration). Building real AI products for real businesses.

- 🔗 [LinkedIn](https://linkedin.com/in/aryan-tripathi-9254a611b)
- 💻 [GitHub](https://github.com/aryan3002)
- 📧 atripa38@asu.edu
- 🌐 Live: [convoaiservices.com](https://www.convoaiservices.com)

---

## License

Proprietary — All rights reserved.

The architecture, design decisions, and engineering patterns are publicly documented here for portfolio and educational reference. Production code, business logic, and brand assets are not licensed for reuse.

---

<div align="center">

*The phone shouldn't be a job. Let an AI take the calls.*

</div>
