# Phase 7 — Telegram Approval Integration

## 1. Architecture Overview

Phase 7 transitions the approval and notification channel from WhatsApp to **Telegram** for the **Jevyam Technologies AI Marketing Agent**.

```
Daily Orchestration (Scheduled / Manual)
                 ↓
      Gemini Content Engine (Pipeline)
                 ↓
  Post Stored in Supabase (PENDING_APPROVAL)
                 ↓
  Approval Request Created (Secure Token)
                 ↓
  Telegram Interactive Notification Dispatched
  (Official HTTPS Bot API → Founder Chat ID)
                 ↓
      Founder Receives Telegram Message:
      • Jevyam Technologies Header & Context
      • Revision Number (#1)
      • Generated Post Hook & Caption
      • Visual Concept / Image (if available)
      • Inline Keyboard Buttons:
        [✅ YES, PUBLISH]   [❌ NO, REGENERATE]
                 ↓
       Founder Clicks an Inline Button
                 ↓
  Telegram Webhook Callback (POST /telegram/webhook)
  • Verified with Secret Token (X-Telegram-Bot-Api-Secret-Token)
  • Immediate Acknowledgment (answerCallbackQuery)
  • Idempotency Deduplication (Callback Query ID tracking)
                 ↓
        ┌────────────────────────────────┴────────────────────────────────┐
        ▼                                                                 ▼
   [✅ YES, PUBLISH]                                              [❌ NO, REGENERATE]
        ↓                                                                 ↓
ApprovalService.approve_post()                         ApprovalService.reject_and_regenerate()
        ↓                                                                 ↓
• Post Status → APPROVED                               • Post Status → REJECTED → REGENERATING
• Approval Token Consumed                              • Approval Token Consumed
• LinkedIn Dispatch Triggered                          • Gemini Pipeline Regenerates Draft
• Confirmation Sent on Telegram                        • Supabase Stores New Revision (#2)
                                                       • New Approval Request & Token Generated
                                                       • New Telegram Approval Notification Sent
                                                       (Repeats loop until approved)
```

---

## 2. Telegram Bot Information

- **Bot Name**: `JeevyamTechBOT`
- **Username**: `@jeevyam_bot`
- **Created via**: `@BotFather` on Telegram

---

## 3. Why Telegram (Technical Justification & Cost)

1. **Permanent ₹0/Month Infrastructure**:
   - Unlike WhatsApp Meta Cloud API, Telegram Bot API has no business verification barriers, no template approvals, no phone number registration fees, and no 24-hour customer messaging windows.
2. **Official HTTPS Bot API**:
   - Direct REST endpoints over HTTPS (`https://api.telegram.org/bot<TOKEN>/...`) with zero third-party library dependencies. Uses Python standard `httpx` or `requests`.
3. **Native Inline Keyboards**:
   - Interactive buttons (`inline_keyboard`) embedded directly under the message with immediate response callbacks (`callback_data`).
4. **Rich Formatting & Media**:
   - Supports clean HTML formatting and image attachments with captions.
5. **Rock-Solid Security**:
   - Supports native secret token validation (`X-Telegram-Bot-Api-Secret-Token`) for webhook verification.

---

## 4. How to Get the Founder Chat ID

The founder Chat ID is the unique numeric identifier of the Telegram user who receives approvals.

### Method 1: Using the Telegram Bot API (`getUpdates`)
1. Open Telegram and search for `@jeevyam_bot`.
2. Tap **Start** or send any message (e.g. `Hello`) to the bot.
3. In your browser or via curl, open:
   ```
   https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/getUpdates
   ```
4. Look for the JSON response:
   ```json
   "message": {
       "chat": {
           "id": 123456789,
           "first_name": "Saranjeet",
           "type": "private"
       }
   }
   ```
5. Copy the numeric `id` (e.g. `123456789`). This is your `TELEGRAM_FOUNDER_CHAT_ID`.

### Method 2: Using `@userinfobot`
1. Open Telegram and message `@userinfobot`.
2. The bot will immediately reply with your numeric `Id`.

---

## 5. Required Environment Variables

Add these to your local `.env` (never commit real values to Git):

```env
# Approval Provider Selection (telegram by default, or whatsapp)
APPROVAL_PROVIDER=telegram

# Telegram Bot Configuration (Phase 7)
TELEGRAM_BOT_TOKEN=your_real_bot_token_from_botfather
TELEGRAM_FOUNDER_CHAT_ID=your_numeric_chat_id
TELEGRAM_WEBHOOK_SECRET=your_custom_secure_webhook_secret_string

# Base URL for local FastAPI server
APP_BASE_URL=http://localhost:8000
```

> [!IMPORTANT]
> - Never hardcode `TELEGRAM_BOT_TOKEN` in code or documentation.
> - In `LIVE` mode, missing `TELEGRAM_BOT_TOKEN` or `TELEGRAM_FOUNDER_CHAT_ID` will fail with an explicit `ConfigurationError`.
> - In `MOCK` mode, the agent functions completely without real credentials.

---

## 6. GitHub Actions Secrets

For automated daily scheduled runs on GitHub Actions, add these repository secrets:

| Secret Name | Description | Required For |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot API token obtained from @BotFather | Live daily runs |
| `TELEGRAM_FOUNDER_CHAT_ID` | Founder's numeric Telegram Chat ID | Live daily runs |
| `TELEGRAM_WEBHOOK_SECRET` | Secret token string for webhook authentication | Production Webhook |
| `GEMINI_API_KEY` | Google Gemini API Key | Content generation |
| `SUPABASE_URL` | Supabase project URL | Content persistence |
| `SUPABASE_KEY` | Supabase service/anon key | Content persistence |
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth Access Token | Post publishing |
| `LINKEDIN_ORGANIZATION_ID`| LinkedIn Company Page numeric URN ID | Post publishing |

---

## 7. Webhook Architecture & Deployment Requirements

### Why GitHub Actions cannot receive Webhooks
GitHub Actions runs on an ephemeral container that executes for a few seconds to generate content, store it in Supabase, dispatch the Telegram notification, and immediately shuts down. It cannot serve as a continuous webhook listener.

### FastAPI Webhook Endpoint
The existing FastAPI application (`api/main.py`) provides the dedicated webhook route:
- **`POST /telegram/webhook`** (or alias `POST /webhook/telegram`)

### Public HTTPS Requirement
Telegram Bot API **requires a publicly reachable HTTPS endpoint** to deliver webhook callbacks. Telegram cannot deliver updates to `http://localhost` or `http://127.0.0.1`.

### ₹0 / Free Production & Development Options

1. **Local Development / Testing (Free)**:
   - **Cloudflare Tunnel (`cloudflared`)** (Recommended, 100% Free):
     ```bash
     cloudflared tunnel --url http://localhost:8000
     ```
   - **ngrok** (Free tier):
     ```bash
     ngrok http 8000
     ```

2. **Production Hosting (Free Tier Options)**:
   - **Render** (Free Web Service tier): Deploys FastAPI Docker / Python service with free automatic HTTPS.
   - **Railway** / **Fly.io** (Generous trial / free credits).
   - **AWS Lambda + API Gateway** (via Mangum): 1 million requests/month free tier forever.

### Setting Up the Webhook with Telegram
Once your FastAPI server is publicly reachable via HTTPS, register the webhook with Telegram using `setWebhook`:

```bash
curl -F "url=https://<YOUR_PUBLIC_HTTPS_DOMAIN>/telegram/webhook" \
     -F "secret_token=<YOUR_TELEGRAM_WEBHOOK_SECRET>" \
     https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook
```

Telegram will confirm:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

---

## 8. Callback Idempotency & Safety

1. **Callback Query Deduplication**:
   - Each Telegram button tap sends a unique `callback_query.id`.
   - The service maintains in-memory tracking of processed callback IDs and rejects duplicate deliveries with `DUPLICATE_CALLBACK`.
2. **Authoritative State Transitions**:
   - The database status in Supabase (`ApprovalStatus` and `PostStatus`) is the single source of truth.
   - Repeated button clicks on already-approved or already-regenerated posts are safely rejected (`ALREADY_PROCESSED`).
   - Duplicate LinkedIn publications or runaway regenerations are mathematically prevented.
3. **Credential Masking in Logs**:
   - All URLs containing `bot<TOKEN>` are automatically masked to `bot<MASKED_TELEGRAM_TOKEN>` before logging.
   - Secrets are never exposed in exceptions, traces, or HTTP error responses.

---

## 9. Verification & Testing

### Run Complete Test Suite
```bash
python -m pytest -q
```
*(All 121+ tests pass, including Telegram, WhatsApp, Gemini, Supabase, and LinkedIn publishing tests).*

### Run Local End-to-End Mock Run
```bash
python scripts/daily_run.py --dry-run --mock-gemini --in-memory
```
Example Output:
```
[SUCCESS] Post 'JVY-20261006-001' generated and approval notification sent via Telegram.
  Post ID:        JVY-20261006-001
  Revision:       1
  Status:         PENDING_APPROVAL
  Approval URL:   http://127.0.0.1:8000/approve/appr_...
  Telegram Msg ID:mock_tg_msg_1001
```

---

## 10. Backward Compatibility

- WhatsApp integration files (`integrations/whatsapp/`, `api/services/whatsapp_service.py`, `api/routes/whatsapp_webhook.py`) remain 100% intact.
- Provider selection is fully configurable via `APPROVAL_PROVIDER=telegram` or `APPROVAL_PROVIDER=whatsapp`.
- Existing WhatsApp test suite (`tests/test_whatsapp.py`) remains completely green.
