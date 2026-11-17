/**
 * Cloudflare Worker: Telegram Webhook Relay to GitHub Actions
 *
 * Receives interactive Telegram button callbacks (YES / NO), validates secret tokens
 * and founder authorization, immediately answers Telegram callback queries (<200ms),
 * and dispatches event payloads to GitHub Actions for execution.
 */

export default {
  async fetch(request, env, ctx) {
    // 1. Health check & GET handling
    if (request.method === "GET") {
      return new Response(
        JSON.stringify({
          status: "healthy",
          service: "Jevyam Technologies Telegram Webhook Relay",
          version: "1.0.0",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    if (request.method !== "POST") {
      return new Response(
        JSON.stringify({ error: "Method not allowed. Use POST." }),
        { status: 405, headers: { "Content-Type": "application/json" } }
      );
    }

    // 2. Secret Token Verification (X-Telegram-Bot-Api-Secret-Token)
    const expectedSecret = env.TELEGRAM_WEBHOOK_SECRET;
    const incomingSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");

    if (expectedSecret && incomingSecret !== expectedSecret) {
      console.warn("[SECURITY] Rejected request with invalid or missing secret token.");
      return new Response(
        JSON.stringify({ error: "Unauthorized: invalid secret token." }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    // 3. Parse JSON Body
    let update;
    try {
      update = await request.json();
    } catch (err) {
      console.warn("[ERROR] Failed to parse JSON payload from request.");
      return new Response(
        JSON.stringify({ error: "Invalid JSON payload." }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // 4. Handle Direct Message Commands (/start, /help, /status, /run, /id, /chatid)
    if (update.message) {
      const msg = update.message;
      const rawText = (msg.text || "").trim();
      const cmd = rawText.split(/\s+/)[0].toLowerCase();
      const chatId = String(msg.chat?.id || "");
      const senderId = String(msg.from?.id || "");
      const founderId = String(env.TELEGRAM_FOUNDER_CHAT_ID || "8164283098").trim();
      const adminId = String(env.TELEGRAM_ADMIN_CHAT_ID || "1293148688").trim();

      const isFounder = (chatId === founderId || senderId === founderId);
      const isAdmin = (chatId === adminId || senderId === adminId);

      // 4a. /start, /id, /chatid
      if (["/start", "/id", "/chatid", "start", "id"].includes(cmd)) {
        let replyText;
        if (isAdmin) {
          replyText =
            `👋 <b>Jevyam Technologies AI Marketing Bot Relay</b>\n\n` +
            `🆔 <b>Chat ID:</b> <code>${chatId}</code>\n` +
            `👤 <b>Sender ID:</b> <code>${senderId}</code>\n` +
            `📋 <b>Role:</b> ADMIN ✅\n\n` +
            `Your account is authorized as Administrator. You will receive previews of generated posts, ` +
            `operational alerts, and publishing status reports here.\n\n` +
            `Type /help to see available admin commands.`;
        } else if (isFounder) {
          replyText =
            `👋 <b>Jevyam Technologies AI Marketing Bot Relay</b>\n\n` +
            `🆔 <b>Chat ID:</b> <code>${chatId}</code>\n` +
            `👤 <b>Sender ID:</b> <code>${senderId}</code>\n` +
            `📋 <b>Role:</b> FOUNDER / APPROVER ✅\n\n` +
            `Your account is authorized. You will receive daily post approval previews, branded images, ` +
            `and interactive approval buttons here.`;
        } else {
          replyText =
            `👋 <b>Jevyam Technologies AI Marketing Bot Relay</b>\n\n` +
            `🆔 <b>Chat ID:</b> <code>${chatId}</code>\n` +
            `👤 <b>Sender ID:</b> <code>${senderId}</code>\n` +
            `📋 <b>Status:</b> Unregistered User ⚠️\n\n` +
            `This chat is not registered as an authorized account.`;
        }

        await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, replyText);
        return new Response(JSON.stringify({ ok: true, handled: "start_command", role: isAdmin ? "admin" : (isFounder ? "founder" : "unregistered") }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      // 4b. /help
      if (["/help", "help", "/commands"].includes(cmd)) {
        if (!isAdmin) {
          await sendTelegramMessage(
            env.TELEGRAM_BOT_TOKEN,
            chatId,
            "⛔ <b>Access Denied:</b> Administrative commands are restricted to authorized administrators."
          );
          return new Response(JSON.stringify({ ok: false, error: "unauthorized" }), {
            status: 403,
            headers: { "Content-Type": "application/json" },
          });
        }

        const helpText =
          `🛠️ <b>Jevyam Technologies Admin Commands</b>\n\n` +
          `• <code>/status</code> — Inspect system health, relay status, and schedule.\n` +
          `• <code>/run</code> — Trigger daily post generation immediately on GitHub Actions.\n` +
          `• <code>/id</code> — Show your account identifiers.\n` +
          `• <code>/help</code> — Show this commands manual.`;

        await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, helpText);
        return new Response(JSON.stringify({ ok: true, handled: "help_command" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      // 4c. /status
      if (["/status", "status"].includes(cmd)) {
        if (!isAdmin) {
          await sendTelegramMessage(
            env.TELEGRAM_BOT_TOKEN,
            chatId,
            "⛔ <b>Access Denied:</b> Administrative commands are restricted to authorized administrators."
          );
          return new Response(JSON.stringify({ ok: false, error: "unauthorized" }), {
            status: 403,
            headers: { "Content-Type": "application/json" },
          });
        }

        const repoOwner = env.GITHUB_REPO_OWNER || "Saran-227";
        const repoName = env.GITHUB_REPO_NAME || "Jevyam-Agent";

        const statusText =
          `📊 <b>Jevyam Agent System Status</b>\n\n` +
          `⚙️ <b>Relay:</b> Cloudflare Worker Active ✅\n` +
          `🚀 <b>GitHub Repository:</b> <code>${repoOwner}/${repoName}</code>\n` +
          `⏰ <b>Daily Schedule:</b> ~09:00 AM IST (30 3 * * * UTC)\n` +
          `👤 <b>Founder ID:</b> <code>${founderId}</code> (Approver ✅)\n` +
          `🛠️ <b>Admin ID:</b> <code>${adminId}</code> (Administrator ✅)\n\n` +
          `<i>Send /run to trigger daily post generation immediately.</i>`;

        await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, statusText);
        return new Response(JSON.stringify({ ok: true, handled: "status_command" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      // 4d. /run
      if (["/run", "run"].includes(cmd)) {
        if (!isAdmin) {
          await sendTelegramMessage(
            env.TELEGRAM_BOT_TOKEN,
            chatId,
            "⛔ <b>Access Denied:</b> Administrative commands are restricted to authorized administrators."
          );
          return new Response(JSON.stringify({ ok: false, error: "unauthorized" }), {
            status: 403,
            headers: { "Content-Type": "application/json" },
          });
        }

        const repoOwner = env.GITHUB_REPO_OWNER || "Saran-227";
        const repoName = env.GITHUB_REPO_NAME || "Jevyam-Agent";
        const githubToken = env.GITHUB_TOKEN;

        await sendTelegramMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          "⏳ <b>Manual Run Triggered:</b> Dispatching daily post generation to GitHub Actions..."
        );

        if (!githubToken) {
          await sendTelegramMessage(
            env.TELEGRAM_BOT_TOKEN,
            chatId,
            "❌ <b>Error:</b> GITHUB_TOKEN is not configured on Cloudflare Worker."
          );
          return new Response(JSON.stringify({ error: "GITHUB_TOKEN missing" }), { status: 500 });
        }

        const dispatchUrl = `https://api.github.com/repos/${repoOwner}/${repoName}/actions/workflows/daily-marketing.yml/dispatches`;
        try {
          const ghRes = await fetch(dispatchUrl, {
            method: "POST",
            headers: {
              "Accept": "application/vnd.github+json",
              "Authorization": `Bearer ${githubToken}`,
              "X-GitHub-Api-Version": "2022-11-28",
              "User-Agent": "Jevyam-Telegram-Relay-Worker",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ ref: "main", inputs: { force: true } }),
          });

          if (ghRes.status === 204) {
            await sendTelegramMessage(
              env.TELEGRAM_BOT_TOKEN,
              chatId,
              "✅ <b>Workflow Dispatched!</b> GitHub Actions is generating today's post. You will receive a copy of the preview once ready."
            );
            return new Response(JSON.stringify({ ok: true, handled: "run_dispatched" }), { status: 200 });
          } else {
            const errBody = await ghRes.text();
            await sendTelegramMessage(
              env.TELEGRAM_BOT_TOKEN,
              chatId,
              `❌ <b>Dispatch Failed:</b> GitHub returned HTTP ${ghRes.status}.`
            );
            return new Response(JSON.stringify({ error: "dispatch_failed", status: ghRes.status }), { status: 502 });
          }
        } catch (dispatchErr) {
          await sendTelegramMessage(
            env.TELEGRAM_BOT_TOKEN,
            chatId,
            `❌ <b>Network Error:</b> Failed to reach GitHub API: ${dispatchErr.message}`
          );
          return new Response(JSON.stringify({ error: dispatchErr.message }), { status: 502 });
        }
      }

      // Other non-command messages
      return new Response(JSON.stringify({ ok: true, ignored: "non_callback_message" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // 5. Handle Callback Query (Inline Button Click)
    const cb = update.callback_query;
    if (!cb) {
      return new Response(JSON.stringify({ ok: true, ignored: "no_actionable_event" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    const callbackQueryId = cb.id;
    const senderId = String(cb.from?.id || "").trim();
    const chatId = String(cb.message?.chat?.id || senderId).trim();
    const founderId = String(env.TELEGRAM_FOUNDER_CHAT_ID || "8164283098").trim();
    const adminId = String(env.TELEGRAM_ADMIN_CHAT_ID || "1293148688").trim();

    // 5a. Strict Founder Authorization (Only Founder can approve or reject)
    if (senderId !== founderId && chatId !== founderId) {
      if (senderId === adminId || chatId === adminId) {
        console.warn(`[SECURITY] Admin user ${senderId} attempted approval callback.`);
        await answerCallbackQuery(
          env.TELEGRAM_BOT_TOKEN,
          callbackQueryId,
          "⛔ Access Denied: Only the Founder can approve or reject posts.",
          true
        );
        return new Response(
          JSON.stringify({ error: "Forbidden: Admin is not authorized to approve posts." }),
          { status: 403, headers: { "Content-Type": "application/json" } }
        );
      }

      console.warn(`[SECURITY] Unauthorized callback attempt by user ${senderId} in chat ${chatId}.`);
      await answerCallbackQuery(
        env.TELEGRAM_BOT_TOKEN,
        callbackQueryId,
        "⛔ Access Denied: Unauthorized user.",
        true
      );
      return new Response(
        JSON.stringify({ error: "Forbidden: unauthorized Telegram user." }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    // 5b. Parse and Validate Callback Data (format: "<action>:<token>")
    const rawData = String(cb.data || "").trim();
    const separatorIdx = rawData.indexOf(":");
    if (separatorIdx === -1) {
      console.warn("[WARN] Malformed callback data missing ':' separator.");
      await answerCallbackQuery(
        env.TELEGRAM_BOT_TOKEN,
        callbackQueryId,
        "⚠️ Invalid button data.",
        false
      );
      return new Response(
        JSON.stringify({ error: "Invalid callback_data format." }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const action = rawData.substring(0, separatorIdx).toLowerCase().trim();
    const token = rawData.substring(separatorIdx + 1).trim();

    if (!["approve", "reject", "yes", "no"].includes(action) || !token) {
      console.warn(`[WARN] Unrecognized action or empty token in callback.`);
      await answerCallbackQuery(
        env.TELEGRAM_BOT_TOKEN,
        callbackQueryId,
        "⚠️ Unrecognized action.",
        false
      );
      return new Response(
        JSON.stringify({ error: "Unrecognized action or empty token." }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Normalize action name
    const normalizedAction = (action === "approve" || action === "yes") ? "approve" : "reject";

    // 5c. Immediate Telegram Callback Query Acknowledgment (<200ms)
    // NOTE: Does NOT claim final success yet; notifies user that processing has begun.
    const ackText = normalizedAction === "approve"
      ? "Processing approval & publishing..."
      : "Processing revision & regenerating...";

    await answerCallbackQuery(
      env.TELEGRAM_BOT_TOKEN,
      callbackQueryId,
      ackText,
      false
    );

    // 5d. Dispatch to GitHub Actions
    const repoOwner = env.GITHUB_REPO_OWNER || "Saran-227";
    const repoName = env.GITHUB_REPO_NAME || "Jevyam-Agent";
    const githubToken = env.GITHUB_TOKEN;

    if (!githubToken) {
      console.error("[CONFIGURATION] Missing GITHUB_TOKEN environment variable.");
      await sendTelegramMessage(
        env.TELEGRAM_BOT_TOKEN,
        chatId,
        "❌ <b>Relay Configuration Error:</b> GitHub dispatch token is not configured on the Worker."
      );
      return new Response(
        JSON.stringify({ error: "Server misconfiguration: GITHUB_TOKEN missing." }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    const dispatchUrl = `https://api.github.com/repos/${repoOwner}/${repoName}/dispatches`;
    const dispatchPayload = {
      event_type: "telegram-callback",
      client_payload: {
        action: normalizedAction,
        token: token,
        chat_id: chatId,
        user_id: senderId,
        callback_query_id: callbackQueryId,
      },
    };

    try {
      const ghResponse = await fetch(dispatchUrl, {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${githubToken}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "Jevyam-Telegram-Relay-Worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(dispatchPayload),
      });

      if (ghResponse.status === 204) {
        // HTTP 204 No Content is the expected successful response for repository_dispatch
        console.log(`[DISPATCH] Successfully dispatched '${normalizedAction}' event to ${repoOwner}/${repoName}.`);
        return new Response(
          JSON.stringify({ ok: true, status: "dispatched", action: normalizedAction }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      } else {
        const ghErrText = await ghResponse.text();
        console.error(`[DISPATCH ERROR] GitHub returned HTTP ${ghResponse.status}: ${ghErrText.substring(0, 200)}`);

        await sendTelegramMessage(
          env.TELEGRAM_BOT_TOKEN,
          chatId,
          `❌ <b>Dispatch Error:</b> GitHub workflow trigger failed (HTTP ${ghResponse.status}). Please check repository permissions.`
        );

        return new Response(
          JSON.stringify({
            error: "GitHub repository dispatch failed.",
            status_code: ghResponse.status,
          }),
          { status: 502, headers: { "Content-Type": "application/json" } }
        );
      }
    } catch (dispatchErr) {
      console.error(`[NETWORK ERROR] Failed to connect to GitHub API: ${dispatchErr.message}`);
      await sendTelegramMessage(
        env.TELEGRAM_BOT_TOKEN,
        chatId,
        "❌ <b>Network Error:</b> Failed to connect to GitHub Actions API."
      );
      return new Response(
        JSON.stringify({ error: "Network error connecting to GitHub." }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  },
};

/**
 * Answer Telegram callback query to dismiss client loading spinner.
 */
async function answerCallbackQuery(botToken, callbackQueryId, text, showAlert = false) {
  if (!botToken || !callbackQueryId) return;
  try {
    const url = `https://api.telegram.org/bot${botToken}/answerCallbackQuery`;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        callback_query_id: callbackQueryId,
        text: text,
        show_alert: showAlert,
      }),
    });
  } catch (err) {
    console.warn(`[WARN] Failed to answer Telegram callback query: ${err.message}`);
  }
}

/**
 * Send Telegram text message to the founder.
 */
async function sendTelegramMessage(botToken, chatId, text) {
  if (!botToken || !chatId || !text) return;
  try {
    const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: text,
        parse_mode: "HTML",
      }),
    });
  } catch (err) {
    console.warn(`[WARN] Failed to send Telegram message: ${err.message}`);
  }
}

