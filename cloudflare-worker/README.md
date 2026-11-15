# Jevyam Technologies — Cloudflare Worker Telegram Webhook Relay

A zero-budget, serverless webhook relay running on Cloudflare Workers (Free Tier).

This worker receives interactive Telegram inline button callbacks from the founder (`approve:<token>` or `reject:<token>`), validates incoming webhooks and founder authorization, immediately acknowledges Telegram callback queries within 200ms (preventing client-side spinners), and dispatches the event payload to GitHub Actions for asynchronous processing and publishing.

---

## 1. Required Cloudflare Worker Secrets

Configure these secrets in Cloudflare Workers using Wrangler or via the Cloudflare Dashboard (**Workers & Pages > jevyam-telegram-relay > Settings > Variables**):

| Secret Name | Description | Example / Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token from BotFather | `123456789:ABC...` |
| `TELEGRAM_WEBHOOK_SECRET` | Secret token used to verify authentic Telegram requests | Random 32+ character string |
| `TELEGRAM_FOUNDER_CHAT_ID` | Telegram Chat ID of authorized founder | `8164283098` |
| `GITHUB_TOKEN` | GitHub Personal Access Token (PAT) with dispatch permissions | Fine-grained or Classic PAT |

---

## 2. GitHub Token Permissions

The `GITHUB_TOKEN` used by the Cloudflare Worker requires permission to trigger repository dispatches:

### Option A: Fine-Grained Personal Access Token (Recommended)
1. Go to **GitHub > Settings > Developer Settings > Personal access tokens > Fine-grained tokens**.
2. Click **Generate new token**.
3. **Repository access**: Select **Only select repositories** -> Choose `Saran-227/Jevyam-Agent`.
4. **Permissions**:
   - **Contents**: `Read and write` (Required to trigger `repository_dispatch` events).
   - **Actions**: `Read and write` (Optional: if triggering `workflow_dispatch`).
5. Copy the generated token (`github_pat_...`).

### Option B: Classic Personal Access Token
- Scope: `repo` (Full control of private repositories) or `public_repo` (if repository is public).

---

## 3. Worker Deployment Commands

From your terminal in the `cloudflare-worker` directory:

```bash
# 1. Navigate to the worker directory
cd cloudflare-worker

# 2. Login to Cloudflare (one-time setup)
npx wrangler login

# 3. Configure the worker secrets
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
npx wrangler secret put TELEGRAM_FOUNDER_CHAT_ID
npx wrangler secret put GITHUB_TOKEN

# 4. Deploy the worker to Cloudflare
npx wrangler deploy
```

Once deployed, Cloudflare will output your worker's live public URL, for example:
```
https://jevyam-telegram-relay.<your-subdomain>.workers.dev
```

---

## 4. Registering the Telegram Webhook

Once the worker is deployed and responding, register the webhook with Telegram by making this API call:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://jevyam-telegram-relay.<your-subdomain>.workers.dev",
    "secret_token": "<YOUR_TELEGRAM_WEBHOOK_SECRET>",
    "allowed_updates": ["callback_query", "message"]
  }'
```

Telegram should respond with:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

To verify the webhook status at any time:
```bash
curl -s "https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

---

## 5. Live Debugging / Monitoring

To watch live incoming requests and dispatch logs in real time:
```bash
npx wrangler tail
```

