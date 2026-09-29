# GitHub Actions Daily Automation & Orchestration (Phase 6)

## 1. Architecture Overview

Phase 6 implements the autonomous daily execution layer for the **Jevyam Technologies AI Marketing Agent** via GitHub Actions.

GitHub Actions acts strictly as the **scheduler and orchestrator**, while the underlying Python application manages all business logic, duplicate checks, persistence, approval creation, and notifications.

```text
GitHub Actions Daily Scheduler (Cron: 03:30 UTC / 09:00 IST)
                      ↓
           scripts/daily_run.py
                      ↓
             DailyOrchestrator
                      ↓
      [Idempotency Check in Database]
      - Already generated today? → SKIP
      - New run or Force → PROCEED
                      ↓
     Content Generation (Gemini AI)
     - Strategist + Repetition Control
     - LinkedIn Post Copy Writer
     - Visual Image Brief Generation
                      ↓
         Persistence (Supabase)
         - posts record (DRAFT → PENDING_APPROVAL)
         - post_revisions record (rev 1)
                      ↓
         Approval Token Creation
         - Unguessable token generated
         - Valid for 24h
                      ↓
        WhatsApp Notification Dispatch
      - MOCK: MockWhatsAppProvider (safe simulation)
      - LIVE: Meta WhatsApp Cloud API (interactive buttons)
                      ↓
              Exit 0 (Success)
```

---

## 2. Daily Schedule and Timezone Conversion

The workflow `.github/workflows/daily-agent.yml` is scheduled using GitHub Actions cron:

```yaml
schedule:
  - cron: "30 3 * * *"
```

### Timezone Conversion:

| Timezone | Scheduled Time | Notes |
| :--- | :--- | :--- |
| **UTC** (Coordinated Universal Time) | `03:30` | Standard GitHub Actions cron reference |
| **IST** (Indian Standard Time, UTC+5:30) | `09:00 AM` | Target business morning for founder review |

### Changing the Schedule:
To run at a different Indian Standard Time, convert from IST to UTC:
- Subtract 5 hours and 30 minutes from your desired IST time.
- Example: 10:00 AM IST $\rightarrow$ 04:30 UTC $\rightarrow$ cron: `"30 4 * * *"`.
- Example: 08:30 AM IST $\rightarrow$ 03:00 UTC $\rightarrow$ cron: `"0 3 * * *"`.

---

## 3. GitHub Secrets Configuration

All sensitive credentials and API keys are stored in GitHub Secrets and injected at runtime as environment variables. **No secrets are ever hardcoded or printed in logs.**

Navigate to:
**GitHub Repository $\rightarrow$ Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**

### Required Secrets List:

| Secret Name | Description | Required in MOCK | Required in LIVE |
| :--- | :--- | :---: | :---: |
| `GEMINI_API_KEY` | Google Gemini API key for content generation | Yes | Yes |
| `SUPABASE_URL` | Supabase project URL (`https://<id>.supabase.co`) | Optional | Yes |
| `SUPABASE_KEY` | Supabase API key (service_role or publishable) | Optional | Yes |
| `WHATSAPP_ACCESS_TOKEN` | Meta WhatsApp Cloud API System User token | No | Yes |
| `WHATSAPP_PHONE_NUMBER_ID` | Meta WhatsApp sender phone number ID | No | Yes |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Meta WhatsApp Business Account (WABA) ID | No | Yes |
| `WHATSAPP_FOUNDER_PHONE` | Founder's recipient phone in E.164 (`+919876543210`) | No | Yes |
| `WHATSAPP_APP_SECRET` | Meta App Secret for payload HMAC verification | No | Optional |
| `WHATSAPP_VERIFY_TOKEN` | Custom webhook verification token | No | Optional |
| `LINKEDIN_CLIENT_ID` | LinkedIn Developer App Client ID | No | Optional |
| `LINKEDIN_CLIENT_SECRET` | LinkedIn Developer App Client Secret | No | Optional |
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth 2.0 Organization token | No | Yes |
| `LINKEDIN_ORGANIZATION_ID` | Jevyam LinkedIn Organization numeric ID | No | Yes |

### Repository Variables (Settings $\rightarrow$ Variables):
- `APP_BASE_URL`: Public base URL for founder approval links (e.g. `https://agent.jevyam.com` or local tunnel). Default: `http://localhost:8000`.
- `GEMINI_MODEL`: Gemini model version (default: `gemini-2.5-flash`).

---

## 4. Execution Modes: MOCK vs. LIVE

### A. MOCK / DRY-RUN Mode (Default)
- **Flag**: `--dry-run` or `DRY_RUN=true`
- **Behavior**:
  - Uses real Gemini AI to draft content (or simulated mock if offline).
  - Persists post and revision to database.
  - Generates real approval tokens and approval URLs.
  - **Mocks WhatsApp delivery**: Uses `MockWhatsAppProvider` in-memory. **No WhatsApp message is ever sent to a real device.**
  - **Mocks LinkedIn publishing**: No LinkedIn publication is attempted.
  - Safe for all CI testing, staging, and automated daily dry-runs before real credentials are ready.

### B. LIVE Mode
- **Flag**: `--live` or `DRY_RUN=false`
- **Behavior**:
  - Validates that all production credentials exist and are not placeholders (`your_...`).
  - **Strict Refusal**: If WhatsApp, Supabase, Gemini, or LinkedIn credentials are missing, **aborts immediately with exit code 1**. Never silently falls back to mock.
  - Dispatches interactive WhatsApp message to founder's phone.
  - Ready for immediate one-click LinkedIn publishing once founder clicks **APPROVE / YES**.

---

## 5. Daily Idempotency & Duplicate Protection

To prevent accidental duplicate posts caused by job retries or multiple manual triggers:

1. Before generating content, `DailyOrchestrator` queries the database for existing posts matching today's date prefix (`JVY-YYYYMMDD-*`).
2. If an active post (`DRAFT`, `PENDING_APPROVAL`, `APPROVED`, or `PUBLISHED`) already exists for today:
   - The orchestrator logs an `[IDEMPOTENT SKIP]` message.
   - It completes cleanly with exit code `0`.
   - It avoids duplicate AI tokens and duplicate WhatsApp notifications.
3. **Manual Override**: To intentionally generate a second post for the same day, pass `--force` (or check `force: true` in GitHub Actions `workflow_dispatch`). This generates sequence `002`.

---

## 6. Manual Workflow Dispatch in GitHub

You can manually trigger the agent at any time:

1. Go to the **Actions** tab in GitHub.
2. Select **Jevyam Daily AI Marketing Agent** from the left sidebar.
3. Click the **Run workflow** dropdown.
4. Options:
   - **mode**: `mock` (default safe mode) or `live`.
   - **force**: Check to bypass daily idempotency and force generate a new post.
5. Click **Run workflow**.

---

## 7. Local Testing Commands

You can run the exact daily orchestrator locally in PowerShell:

```powershell
# 1. Safe dry-run using in-memory DB and mock Gemini (completely offline, zero credentials needed)
.venv\Scripts\python scripts/daily_run.py --dry-run --mock-gemini --in-memory

# 2. Dry-run using your local .env credentials and Supabase persistence
.venv\Scripts\python scripts/daily_run.py --dry-run

# 3. Force generate new post even if one exists for today
.venv\Scripts\python scripts/daily_run.py --dry-run --force

# 4. Attempt live run (will validate credentials and refuse if missing)
.venv\Scripts\python scripts/daily_run.py --live
```

---

## 8. Failure Handling & Log Inspection

- **Exit Code 0**: Workflow succeeded (either draft created and notification dispatched, or skipped due to idempotency).
- **Exit Code 1**: Workflow failed (missing credentials, AI overload, database failure, or provider error). The GitHub Action job is marked as **Failed**, alerting the team.
- **Log Masking**: Approval tokens are displayed with masking (`appr_r6...1D1o`), and access tokens/secrets are never printed.
