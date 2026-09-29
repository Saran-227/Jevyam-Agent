# Jevyam Technologies AI Marketing Agent

An autonomous AI marketing agent that generates technical, brand-aligned LinkedIn content for **Jevyam Technologies**, manages state in **Supabase**, and orchestrates founder approvals via **FastAPI** and **WhatsApp Interactive Messages**.

---

## Workflow Overview

```
Daily Trigger (Cron)
       ↓
Content Strategist & Writer (Gemini 2.5 Flash SDK)
       ↓
Post Draft + Image Brief Persisted to Supabase (DRAFT / PENDING_APPROVAL)
       ↓
Founder WhatsApp Notification (Meta Cloud API / Interactive Buttons)
       ↓
Founder selects [APPROVE / YES] or [REGENERATE / NO]
       ↓
YES → Approved Post (Ready for Phase 5 LinkedIn Dispatch)
NO  → Autonomous Regeneration (Pivots strategy, generates Rev #2, dispatches new WhatsApp request)
```

---

## Project Structure

```
JevyamAgent/
├── agent/                  # Content strategist, writer, prompts, repetition control
├── api/                    # FastAPI founder approval API & WhatsApp webhook router
│   ├── routes/             # Health, approval web interface, WhatsApp webhooks
│   └── services/           # ApprovalService and WhatsAppService
├── config/                 # Environment and application settings
├── database/               # PostgreSQL schema, models, and repositories (Supabase & In-Memory)
├── docs/                   # System design, WhatsApp options, Phase 4 documentation
├── integrations/
│   ├── gemini.py           # Google GenAI SDK integration wrapper
│   └── whatsapp/           # WhatsApp provider abstraction (Meta Cloud API & Mock)
├── tests/                  # Automated pytest suite (61 unit & acceptance tests)
└── main.py                 # Application CLI entrypoint
```

---

## Phase 4 — WhatsApp Setup

### 1. Configure Environment Variables
Copy `.env.example` to `.env` and configure your WhatsApp credentials:

```bash
cp .env.example .env
```

```env
# WhatsApp Configuration (Meta Cloud API)
WHATSAPP_PROVIDER=meta
WHATSAPP_ACCESS_TOKEN=your_meta_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id
WHATSAPP_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_FOUNDER_PHONE=+919876543210
WHATSAPP_APP_SECRET=your_app_secret
```

For offline development and tests, set `WHATSAPP_PROVIDER=mock`.

### 2. Run API Server & Webhook Listener
```bash
python main.py
# Or: uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Endpoints active:
- `GET /health` — Health check
- `GET /approve/{token}` — Web approval interface
- `GET /webhook/whatsapp` — Meta Webhook challenge verification
- `POST /webhook/whatsapp` — Meta Webhook event & button callback processor

### 3. Expose Webhook for Meta Sandbox
Use Cloudflare Tunnel or ngrok to provide an HTTPS endpoint to Meta:
```bash
ngrok http 8000
```
In your Meta Developer Console, set the Webhook Callback URL to:
`https://<your-subdomain>.ngrok-free.app/webhook/whatsapp`

---

---

## Phase 5 — LinkedIn Publishing Setup

### Configure LinkedIn Credentials
Set your LinkedIn Developer application credentials in `.env`:

```env
# LinkedIn API (Phase 5 — Company Page Publishing)
LINKEDIN_CLIENT_ID=your_linkedin_client_id_here
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret_here
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token_here
LINKEDIN_ORGANIZATION_ID=12345678
AUTO_PUBLISH_ON_APPROVAL=true
```

When `AUTO_PUBLISH_ON_APPROVAL=true`, approving a post via the Web approval interface or WhatsApp interactive button immediately publishes the post to the **Jevyam Technologies** LinkedIn Company Page.

Endpoints active:
- `POST /posts/{post_id}/publish` — Manually publish or retry an approved post
- `GET /posts/{post_id}/publications` — Fetch publication audit records

---

## Running Tests

All unit tests use mock HTTP clients and in-memory repositories. No real external API calls (WhatsApp, LinkedIn, Gemini) are dispatched during automated tests:

```bash
pytest
```

---

## Roadmap

- [x] **Phase 0**: Project foundation & Gemini SDK setup
- [x] **Phase 1**: Content generation engine & repetition control
- [x] **Phase 2**: Supabase database layer & persistent post state
- [x] **Phase 3**: FastAPI founder approval web interface
- [x] **Phase 4**: WhatsApp interactive approval notification layer
- [x] **Phase 5**: LinkedIn publishing integration
- [x] **Phase 6**: GitHub Actions daily orchestration & automation

---

## Phase 6 — Daily Automation & Orchestration

The agent executes automatically every morning via GitHub Actions:
- **Scheduled Time**: `03:30 UTC` (every day) $\rightarrow$ `09:00 AM IST` (Indian Standard Time)
- **Workflow File**: `.github/workflows/daily-agent.yml`
- **CI Test Suite**: `.github/workflows/tests.yml`

### Run Locally:
```bash
# Offline dry run with simulated AI and in-memory DB:
python scripts/daily_run.py --dry-run --mock-gemini --in-memory

# Dry run with real local environment & Supabase:
python scripts/daily_run.py --dry-run

# Bypass daily idempotency check:
python scripts/daily_run.py --dry-run --force
```

For complete documentation on GitHub Secrets, manual dispatch, and timezone schedules, see [`docs/github-actions.md`](docs/github-actions.md).

