# Phase 4 — WhatsApp Approval Notification System

## 1. Architecture Overview

Phase 4 integrates an automated, interactive WhatsApp notification and approval layer for the **Jevyam Technologies AI Marketing Agent**.

```
Daily Content Generation (Pipeline)
               ↓
    Post Stored in Supabase (PENDING_APPROVAL)
               ↓
    WhatsApp Approval Notification (Meta Cloud API / Interactive Buttons)
               ↓
       Founder Receives WhatsApp Message
       • Post ID & Revision
       • Opening Hook
       • Complete Caption & Hashtags
       • Companion Visual / Image Link
       • Interactive Buttons: [APPROVE / YES] [REGENERATE / NO]
               ↓
       Founder Taps Action Button
               ↓
   Meta Cloud API Webhook Callback (POST /webhook/whatsapp)
   • Signature Verification (HMAC-SHA256)
   • Idempotency & Replay Protection (Message ID deduplication)
   • Action & Token Extraction
               ↓
       ┌───────────────────────────────┴───────────────────────────────┐
       ▼                                                               ▼
   APPROVE / YES                                                REGENERATE / NO
       ↓                                                               ↓
ApprovalService.approve_post()                       ApprovalService.reject_and_regenerate()
       ↓                                                               ↓
Post → APPROVED                                      Post → REGENERATING → DRAFT
Approval → APPROVED                                  Approval → REJECTED
Confirmation WhatsApp Sent                           New Revision Generated in Supabase
(Ready for Phase 5 LinkedIn Dispatch)                 New Approval Dispatched to WhatsApp
```

---

## 2. Selected Provider & Technical Justification

- **Selected Provider**: **Official Meta WhatsApp Cloud API** (Graph API `v21.0`).
- **Why Selected**:
  1. **₹0 / Free-Tier Cost**: In Meta Developer Sandbox mode, test phone numbers provide free messaging to verified recipient numbers (the founder). No credit card or business payment is required.
  2. **Native Interactive Buttons**: Supported out-of-the-box (`quick_reply` interactive buttons) with machine-readable payloads (`approve:<token>` and `regenerate:<token>`).
  3. **Media Support**: Supports image headers and attachments directly with the post draft.
  4. **Security & Compliance**: Fully compliant with WhatsApp Terms of Service, preventing account bans associated with unofficial automation.
  5. **Cloud-Native & CI Compatible**: Standard HTTPS REST requests callable from anywhere, including GitHub Actions runners.

---

## 3. Free-Tier & Testing Constraints

1. **Test Recipient Phone Verification**:
   - In Meta Developer Sandbox mode, messages can only be delivered to phone numbers verified in the Meta Developer Console (up to 5 numbers). The founder's phone number must be added and verified with a one-time OTP.
2. **Session / 24-Hour Messaging Window**:
   - Free-form messages can be sent within a 24-hour service window after the user messages the business.
   - For business-initiated notifications outside 24 hours, standard Meta pre-approved templates or Developer Test Number messages are used.
3. **Public Webhook Endpoint**:
   - Meta requires an HTTPS URL to deliver webhook callbacks. During local development, tunneling tools such as **Cloudflare Tunnel** or **ngrok** are required.

---

## 4. Required Meta Developer Setup

To configure live WhatsApp messaging with Meta:

1. **Create a Meta Developer Account**:
   - Visit [developers.facebook.com](https://developers.facebook.com/) and register.
2. **Create an App**:
   - Select **Other** > **Business** app type.
   - Add **WhatsApp** product to your app.
3. **Obtain Test Credentials**:
   - Navigate to **WhatsApp** > **API Setup**.
   - Note the **Temporary Access Token** (or generate a permanent System User Token under Business Settings).
   - Note the **Phone Number ID** (e.g., `109876543210987`).
   - Note the **WhatsApp Business Account ID**.
4. **Register Founder's Phone Number**:
   - In the **To** dropdown, select **Manage Phone Number List**.
   - Add the founder's phone number with country code (e.g. `+91XXXXXXXXXX`) and enter the verification code received via SMS/WhatsApp.
5. **Configure Webhook**:
   - In the Meta App Dashboard, go to **WhatsApp** > **Configuration**.
   - Set **Callback URL** to `https://<your-public-domain>/webhook/whatsapp`.
   - Set **Verify Token** to the value of `WHATSAPP_VERIFY_TOKEN` (e.g., `jevyam_verify_token`).
   - Under **Webhook Fields**, subscribe to `messages`.

---

## 5. Required Environment Variables

Configure these in your local `.env`:

```env
# WhatsApp Configuration (Phase 4)
WHATSAPP_PROVIDER=meta                       # 'meta' for live Graph API, 'mock' for local tests
WHATSAPP_ACCESS_TOKEN=EAAB...                # System User or Developer Access Token
WHATSAPP_PHONE_NUMBER_ID=109876543210987    # Meta Phone Number ID
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098   # Meta WhatsApp Business Account ID
WHATSAPP_VERIFY_TOKEN=jevyam_verify_token    # Secret string for GET webhook verification
WHATSAPP_FOUNDER_PHONE=+919876543210        # Founder recipient phone number
WHATSAPP_APP_SECRET=your_meta_app_secret     # Meta App Secret for X-Hub-Signature-256 check
WHATSAPP_API_VERSION=v21.0
```

---

## 6. Local Development & Webhook Tunneling

To test incoming button callbacks locally:

1. **Start the FastAPI Server**:
   ```bash
   python main.py
   # Or: uvicorn api.main:app --port 8000 --reload
   ```

2. **Expose Localhost via Cloudflare Tunnel or ngrok**:
   ```bash
   ngrok http 8000
   # Or: cloudflared tunnel --url http://localhost:8000
   ```

3. **Configure Meta Webhook**:
   - Paste the public HTTPS URL into the Meta Developer Console: `https://<subdomain>.ngrok-free.app/webhook/whatsapp`.
   - Enter your `WHATSAPP_VERIFY_TOKEN`.
   - Click **Verify and Save**.

---

## 7. Testing Instructions

All automated tests use mocked HTTP clients or the in-memory `MockWhatsAppProvider`. No real WhatsApp messages or network calls are made during normal test runs:

```bash
# Run complete test suite (Phase 1 to Phase 4)
pytest

# Run only WhatsApp integration tests
pytest tests/test_whatsapp.py -v
```

### Optional Live Sandbox Integration Test
To run a live end-to-end dispatch against Meta Cloud API (requires valid credentials in `.env`):
```bash
set RUN_LIVE_WHATSAPP_TESTS=1
pytest tests/test_whatsapp.py -k test_live_whatsapp_api
```

---

## 8. GitHub Actions Compatibility

- Meta WhatsApp Cloud API is a stateless REST endpoint.
- Scheduled workflows (e.g. daily cron at 08:00 IST) can generate posts, store them in Supabase, and invoke `WhatsAppService.send_post_approval_notification(post_id)` directly from the GitHub Actions runner.
- Webhook callbacks are handled by the running FastAPI approval server deployed to a cloud host (Fly.io, Render, Railway, or VPS).

---

## 9. Next Steps for Phase 5

Phase 5 will implement:
- **LinkedIn Publishing API Integration**: Dispatches approved posts (`status == APPROVED`) to LinkedIn Personal Profile or Company Page via OAuth 2.0.
- **Media Asset Upload**: Registers and uploads generated companion images to LinkedIn Assets API.
- **Audit Logging**: Persists published LinkedIn Post URN and timestamp back into Supabase `posts.linkedin_post_id` and `posts.published_at`.
