/**
 * Node.js test suite for Cloudflare Worker: telegram-webhook.js
 */

import assert from "node:assert";
import worker from "./telegram-webhook.js";

const FAKE_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11";
const FAKE_WEBHOOK_SECRET = "super_secret_webhook_token_123456789";
const FOUNDER_CHAT_ID = "8164283098";
const FAKE_GITHUB_TOKEN = "ghp_mockToken1234567890abcdef";

console.log("--- Starting Cloudflare Worker Unit Tests ---");

// Helper to mock global fetch
function createMockFetch(responses = {}) {
  const calls = [];
  const mockFetch = async (url, options = {}) => {
    calls.push({ url, options });
    for (const [pattern, handler] of Object.entries(responses)) {
      if (url.includes(pattern)) {
        return handler(url, options);
      }
    }
    // Default 200 OK
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  return { mockFetch, calls };
}

// 1. Health check test
{
  console.log("Test 1: GET health check");
  const req = new Request("https://relay.workers.dev/", { method: "GET" });
  const res = await worker.fetch(req, {}, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.status, "healthy");
}

// 2. Secret Token Verification
{
  console.log("Test 2: Reject invalid secret token");
  const env = { TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET };
  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": "wrong_secret",
    },
    body: JSON.stringify({}),
  });
  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 403);
  const data = await res.json();
  assert.ok(data.error.includes("invalid secret token"));
}

// 3. Unauthorized User Callback Rejection
{
  console.log("Test 3: Reject unauthorized Telegram user");
  const { mockFetch, calls } = createMockFetch({
    "answerCallbackQuery": () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
  });
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      callback_query: {
        id: "cb_unauth_123",
        from: { id: 999999999 }, // Unauthorized user
        message: { chat: { id: 999999999 } },
        data: "approve:tok_test_123",
      },
    }),
  });

  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 403);
  const data = await res.json();
  assert.ok(data.error.includes("unauthorized"));

  // Verify answerCallbackQuery was called with alert
  const ansCall = calls.find(c => c.url.includes("answerCallbackQuery"));
  assert.ok(ansCall, "answerCallbackQuery should be called for unauthorized user");
  const ansBody = JSON.parse(ansCall.options.body);
  assert.strictEqual(ansBody.show_alert, true);
  assert.ok(ansBody.text.includes("Access Denied"));
}

// 4. Valid Founder YES Callback & GitHub Dispatch
{
  console.log("Test 4: Valid Founder YES callback triggers GitHub repository dispatch");
  const { mockFetch, calls } = createMockFetch({
    "answerCallbackQuery": () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    "api.github.com": () => new Response(null, { status: 204 }), // HTTP 204 No Content
  });
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
    GITHUB_TOKEN: FAKE_GITHUB_TOKEN,
    GITHUB_REPO_OWNER: "Saran-227",
    GITHUB_REPO_NAME: "Jevyam-Agent",
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      callback_query: {
        id: "cb_founder_yes_1",
        from: { id: Number(FOUNDER_CHAT_ID) },
        message: { chat: { id: Number(FOUNDER_CHAT_ID) } },
        data: "approve:tok_valid_yes_123",
      },
    }),
  });

  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.ok, true);
  assert.strictEqual(data.status, "dispatched");
  assert.strictEqual(data.action, "approve");

  // Verify fast answerCallbackQuery was called
  const ansCall = calls.find(c => c.url.includes("answerCallbackQuery"));
  assert.ok(ansCall);
  const ansBody = JSON.parse(ansCall.options.body);
  assert.strictEqual(ansBody.callback_query_id, "cb_founder_yes_1");
  assert.ok(ansBody.text.includes("Processing approval"));

  // Verify GitHub dispatch call
  const ghCall = calls.find(c => c.url.includes("api.github.com"));
  assert.ok(ghCall, "GitHub API dispatch should be executed");
  assert.strictEqual(ghCall.options.method, "POST");
  assert.strictEqual(ghCall.options.headers["Authorization"], `Bearer ${FAKE_GITHUB_TOKEN}`);
  const ghBody = JSON.parse(ghCall.options.body);
  assert.strictEqual(ghBody.event_type, "telegram-callback");
  assert.strictEqual(ghBody.client_payload.action, "approve");
  assert.strictEqual(ghBody.client_payload.token, "tok_valid_yes_123");
  assert.strictEqual(ghBody.client_payload.chat_id, FOUNDER_CHAT_ID);
}

// 5. Valid Founder NO Callback & GitHub Dispatch
{
  console.log("Test 5: Valid Founder NO callback triggers rejection dispatch");
  const { mockFetch, calls } = createMockFetch({
    "answerCallbackQuery": () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    "api.github.com": () => new Response(null, { status: 204 }),
  });
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
    GITHUB_TOKEN: FAKE_GITHUB_TOKEN,
    GITHUB_REPO_OWNER: "Saran-227",
    GITHUB_REPO_NAME: "Jevyam-Agent",
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      callback_query: {
        id: "cb_founder_no_1",
        from: { id: Number(FOUNDER_CHAT_ID) },
        message: { chat: { id: Number(FOUNDER_CHAT_ID) } },
        data: "reject:tok_valid_no_456",
      },
    }),
  });

  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.action, "reject");

  const ghCall = calls.find(c => c.url.includes("api.github.com"));
  const ghBody = JSON.parse(ghCall.options.body);
  assert.strictEqual(ghBody.client_payload.action, "reject");
  assert.strictEqual(ghBody.client_payload.token, "tok_valid_no_456");
}

// 6. GitHub Dispatch Failure (HTTP 403 from GitHub)
{
  console.log("Test 6: GitHub dispatch failure handled safely");
  const { mockFetch, calls } = createMockFetch({
    "answerCallbackQuery": () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    "sendMessage": () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    "api.github.com": () => new Response(JSON.stringify({ message: "Bad credentials" }), { status: 401 }),
  });
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
    GITHUB_TOKEN: "bad_token",
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      callback_query: {
        id: "cb_fail_1",
        from: { id: Number(FOUNDER_CHAT_ID) },
        message: { chat: { id: Number(FOUNDER_CHAT_ID) } },
        data: "approve:tok_fail_1",
      },
    }),
  });

  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 502);

  // Verify alert message sent to founder
  const sendMsgCall = calls.find(c => c.url.includes("sendMessage"));
  assert.ok(sendMsgCall, "Alert message must be sent to founder on dispatch failure");
  const msgBody = JSON.parse(sendMsgCall.options.body);
  assert.ok(msgBody.text.includes("Dispatch Error"));
}

// 7. Admin /start and /help Commands
{
  console.log("Test 7: Admin /start and /help commands");
  const { mockFetch, calls } = createMockFetch();
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_ADMIN_CHAT_ID: "1293148688",
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
  };

  // Admin /start
  const reqStart = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      message: {
        chat: { id: 1293148688 },
        from: { id: 1293148688 },
        text: "/start",
      },
    }),
  });
  const resStart = await worker.fetch(reqStart, env, {});
  assert.strictEqual(resStart.status, 200);
  const dataStart = await resStart.json();
  assert.strictEqual(dataStart.role, "admin");

  const sendMsgCall = calls.find(c => c.url.includes("sendMessage"));
  assert.ok(sendMsgCall);
  const msgBody = JSON.parse(sendMsgCall.options.body);
  assert.ok(msgBody.text.includes("ADMIN"));

  // Admin /help
  const reqHelp = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      message: {
        chat: { id: 1293148688 },
        from: { id: 1293148688 },
        text: "/help",
      },
    }),
  });
  const resHelp = await worker.fetch(reqHelp, env, {});
  assert.strictEqual(resHelp.status, 200);
}

// 8. Admin /status Command
{
  console.log("Test 8: Admin /status command reports system status");
  const { mockFetch, calls } = createMockFetch();
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_ADMIN_CHAT_ID: "1293148688",
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      message: {
        chat: { id: 1293148688 },
        from: { id: 1293148688 },
        text: "/status",
      },
    }),
  });
  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.handled, "status_command");

  const sendMsgCall = calls.find(c => c.url.includes("sendMessage"));
  assert.ok(sendMsgCall);
  const msgBody = JSON.parse(sendMsgCall.options.body);
  assert.ok(msgBody.text.includes("System Status"));
  assert.ok(msgBody.text.includes("1293148688"));
}

// 9. Admin /run Command Dispatches Workflow to GitHub Actions
{
  console.log("Test 9: Admin /run command dispatches workflow to GitHub Actions");
  const { mockFetch, calls } = createMockFetch({
    "api.github.com": () => new Response(null, { status: 204 }),
  });
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_ADMIN_CHAT_ID: "1293148688",
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
    GITHUB_TOKEN: FAKE_GITHUB_TOKEN,
    GITHUB_REPO_OWNER: "Saran-227",
    GITHUB_REPO_NAME: "Jevyam-Agent",
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      message: {
        chat: { id: 1293148688 },
        from: { id: 1293148688 },
        text: "/run",
      },
    }),
  });
  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.handled, "run_dispatched");

  const ghCall = calls.find(c => c.url.includes("daily-marketing.yml/dispatches"));
  assert.ok(ghCall, "GitHub Actions dispatch should be invoked");
  const ghBody = JSON.parse(ghCall.options.body);
  assert.strictEqual(ghBody.inputs.force, true);
}

// 10. Unauthorized User Rejected From Admin Commands
{
  console.log("Test 10: Unauthorized user rejected from admin commands");
  const { mockFetch, calls } = createMockFetch();
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_ADMIN_CHAT_ID: "1293148688",
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      message: {
        chat: { id: 999888777 },
        from: { id: 999888777 },
        text: "/run",
      },
    }),
  });
  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 403);
  const data = await res.json();
  assert.strictEqual(data.error, "unauthorized");

  const sendMsgCall = calls.find(c => c.url.includes("sendMessage"));
  assert.ok(sendMsgCall);
  const msgBody = JSON.parse(sendMsgCall.options.body);
  assert.ok(msgBody.text.includes("Access Denied"));
}

// 11. Admin CANNOT Trigger Founder Approval Callbacks
{
  console.log("Test 11: Admin CANNOT trigger founder approval callbacks");
  const { mockFetch, calls } = createMockFetch();
  globalThis.fetch = mockFetch;

  const env = {
    TELEGRAM_WEBHOOK_SECRET: FAKE_WEBHOOK_SECRET,
    TELEGRAM_FOUNDER_CHAT_ID: FOUNDER_CHAT_ID,
    TELEGRAM_ADMIN_CHAT_ID: "1293148688",
    TELEGRAM_BOT_TOKEN: FAKE_BOT_TOKEN,
  };

  const req = new Request("https://relay.workers.dev/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Bot-Api-Secret-Token": FAKE_WEBHOOK_SECRET,
    },
    body: JSON.stringify({
      callback_query: {
        id: "cb_admin_attempt",
        from: { id: 1293148688 }, // Admin trying to click YES button
        message: { chat: { id: 1293148688 } },
        data: "approve:tok_test_123",
      },
    }),
  });
  const res = await worker.fetch(req, env, {});
  assert.strictEqual(res.status, 403);
  const data = await res.json();
  assert.ok(data.error.includes("Admin is not authorized to approve posts"));

  // Check alert sent via answerCallbackQuery
  const ansCall = calls.find(c => c.url.includes("answerCallbackQuery"));
  assert.ok(ansCall);
  const ansBody = JSON.parse(ansCall.options.body);
  assert.strictEqual(ansBody.show_alert, true);
  assert.ok(ansBody.text.includes("Only the Founder can approve"));
}

console.log("--- All Cloudflare Worker Unit Tests Passed Successfully! ---");

