# Phase 5 — LinkedIn Publishing Layer

## 1. Overview & Architecture

Phase 5 implements the automated, production-ready publishing integration for the **Jevyam Technologies AI Marketing Agent**, dispatching approved LinkedIn drafts directly to the official **Jevyam Technologies LinkedIn Company Page**.

```text
Gemini Content Pipeline
         ↓
Post stored in Supabase (PENDING_APPROVAL)
         ↓
Founder Approval Request (WhatsApp / Web)
         ↓
      APPROVED
         ↓
ApprovalService.approve_post()
         ↓
PublishingService.publish_approved_post(post_id)
         ↓
1. Idempotency Check: Already published?
   → If yes, return existing URN and skip dispatch
2. Approval Verification:
   → If not APPROVED, refuse and raise PostNotApprovedError
3. Audit Log:
   → Insert PENDING record in publications table
4. LinkedIn REST Client (POST /rest/posts):
   → Author: urn:li:organization:<org_id>
   → Commentary: Hook + Caption + Hashtags
   → Visibility: PUBLIC
         ↓
    [201 Created]
         ↓
5. Master Post Updated:
   → status = PUBLISHED
   → linkedin_post_id = urn:li:share:<id>
   → published_at = now()
6. Audit Record Updated:
   → status = PUBLISHED
   → external_post_id = urn:li:share:<id>
         ↓
Confirmation returned to Approval API & WhatsApp
```

---

## 2. LinkedIn Credentials & Organization Configuration

Configure the following variables in `.env`:

```env
# LinkedIn API Configuration (Phase 5)
LINKEDIN_CLIENT_ID=your_linkedin_client_id_here
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret_here
LINKEDIN_ACCESS_TOKEN=AQ...your_access_token_here
LINKEDIN_ORGANIZATION_ID=12345678
AUTO_PUBLISH_ON_APPROVAL=true
```

### Where to Find `LINKEDIN_ORGANIZATION_ID`
1. Log in to LinkedIn with the administrator account of the **Jevyam Technologies** Company Page.
2. Navigate to your Company Page admin view (e.g. `https://www.linkedin.com/company/12345678/admin/page-posts/published/`).
3. The numeric ID in the URL is your `LINKEDIN_ORGANIZATION_ID` (e.g. `12345678`).
4. The publisher automatically normalizes this to the URN format: `urn:li:organization:12345678`.

---

## 3. LinkedIn OAuth 2.0 Scope Requirements

To publish posts to a LinkedIn Company Page, your LinkedIn Developer App requires:

| Scope | Purpose |
| :--- | :--- |
| `w_organization_social` | Required to create, modify, and delete posts on behalf of an Organization. |
| `r_organization_social` | Required to retrieve posts, comments, and engagement analytics. |
| `r_organization_admin` | Required to verify admin status on the company page. |

> [!IMPORTANT]
> The LinkedIn member whose access token is provided must hold an **Organization Administrator** or **Content Admin** role on the Jevyam Technologies LinkedIn Company Page.

---

## 4. Idempotency & Duplicate Protection

To prevent accidental duplicate posts on the official company page from network retries, double-clicks on WhatsApp buttons, or server restarts:

1. **Database-Level Guard**: Before contacting LinkedIn, `PublishingService` inspects the post record in Supabase. If `post.status == PostStatus.PUBLISHED` or `post.linkedin_post_id` is populated, the method immediately returns the existing publication result with `is_duplicate: True` without making any network call.
2. **Audit Trail**: Every publication attempt creates an entry in the `publications` table with timestamps, target URNs, and status (`PENDING`, `PUBLISHED`, `FAILED`).
3. **Approval Status Validation**: The service strictly enforces that only posts with `status == APPROVED` and an active `APPROVED` approval token can be dispatched. Content in `DRAFT`, `PENDING_APPROVAL`, `REJECTED`, or `REGENERATING` states is categorically rejected.

---

## 5. API Endpoints

The FastAPI server exposes these publishing endpoints:

- `POST /posts/{post_id}/publish` — Manually trigger or retry publication for an approved post.
- `GET /posts/{post_id}/publications` — Fetch the complete audit log of publication attempts for a post.

---

## 6. Running Unit Tests

All LinkedIn unit tests use mocked HTTP clients. No live LinkedIn credentials or API calls are required to run the test suite:

```bash
# Run LinkedIn publishing unit tests
pytest tests/test_linkedin_publishing.py -v

# Run the complete project test suite
pytest
```
