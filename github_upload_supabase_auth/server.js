import "dotenv/config";
import express from "express";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import pg from "pg";

const { Pool } = pg;
const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const port = Number(process.env.PORT || 3000);
const webhookUrl = process.env.N8N_WEBHOOK_URL || "";
const freeRequestsLimit = Number(process.env.FREE_REQUESTS_LIMIT || 5);

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.PGSSL === "true" ? { rejectUnauthorized: false } : undefined
});

const asyncRoute = (handler) => (req, res, next) => {
  Promise.resolve(handler(req, res, next)).catch(next);
};

app.use(express.json({ limit: "1mb" }));
app.use("/assets", express.static(join(__dirname, "assets")));

function requireDatabaseConfig() {
  if (!process.env.DATABASE_URL) {
    const error = new Error("DATABASE_URL is not configured");
    error.status = 500;
    throw error;
  }
}

async function initializeDatabase() {
  requireDatabaseConfig();
  await pool.query("select 1");
}

async function tableExists(client, tableName) {
  const result = await client.query(
    `select exists (
       select 1
       from information_schema.tables
       where table_schema = 'public' and table_name = $1
     ) as exists`,
    [tableName]
  );
  return Boolean(result.rows[0]?.exists);
}

function formatHistoryRow(row) {
  const createdAt = new Date(row.created_at);
  return {
    id: row.id,
    question: row.question,
    answer: row.answer,
    date: createdAt.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }) + ", " +
      createdAt.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
    vehicle: row.vehicle || "Укажите машину • Укажите мотор • Укажите привод",
    type: row.request_type || "Текстовый запрос",
    status: row.status || "Сохранено",
    createdAt: row.created_at
  };
}

async function getUserContext(client, webUserId) {
  if (await tableExists(client, "app_users")) {
    await client.query(
      `insert into app_users (id, source, username, first_name, updated_at)
       values ($1, 'web', 'web_user', 'Web', now())
       on conflict (id) do update set updated_at = excluded.updated_at`,
      [webUserId]
    );
    return { userId: webUserId, mode: "app_users" };
  }

  if (await tableExists(client, "users") && await tableExists(client, "user_sessions")) {
    const session = await client.query(
      "select user_id from user_sessions where session_token = $1",
      [webUserId]
    );

    if (session.rows[0]?.user_id) {
      await client.query("update user_sessions set last_seen_at = now() where session_token = $1", [webUserId]);
      return { userId: session.rows[0].user_id, mode: "users" };
    }

    const user = await client.query(
      `insert into users (name, subscription_plan, subscription_status, last_login)
       values ('Web user', 'free', 'inactive', now())
       returning id`
    );
    const userId = user.rows[0].id;

    await client.query(
      `insert into user_sessions (session_token, user_id, source, device)
       values ($1, $2, 'web', 'browser')`,
      [webUserId, userId]
    );

    return { userId, mode: "users" };
  }

  const error = new Error("No supported users table found in Supabase");
  error.status = 500;
  throw error;
}

async function getQuota(client, userContext) {
  let plan = "free";
  let status = "inactive";
  let limit = freeRequestsLimit;

  if (userContext.mode === "users" && await tableExists(client, "subscriptions")) {
    const subscription = await client.query(
      `select plan, status, requests_limit
       from subscriptions
       where user_id = $1
       order by updated_at desc, created_at desc
       limit 1`,
      [userContext.userId]
    );

    const row = subscription.rows[0];
    if (row) {
      plan = row.plan || plan;
      status = row.status || status;
      if (row.status === "active") limit = row.requests_limit;
    }
  }

  const usage = await client.query(
    `select count(*)::int as used
     from diagnostic_requests
     where user_id = $1 and created_at >= date_trunc('month', now())`,
    [userContext.userId]
  );

  const used = usage.rows[0]?.used || 0;
  const unlimited = status === "active" && limit === null;

  return {
    plan,
    status,
    limit,
    used,
    remaining: unlimited ? null : Math.max(Number(limit || 0) - used, 0),
    unlimited
  };
}

function ensureQuotaAvailable(quota) {
  if (quota.unlimited) return;
  if (quota.used >= Number(quota.limit || 0)) {
    const error = new Error("Лимит запросов исчерпан. Обновите подписку или дождитесь нового периода.");
    error.status = 429;
    error.limitReached = true;
    error.quota = quota;
    throw error;
  }
}

async function saveDiagnosticRequest(client, { userContext, question, answer, requestType = "Текстовый запрос" }) {
  const saved = await client.query(
    `insert into diagnostic_requests (user_id, question, answer, request_type, status, source)
     values ($1, $2, $3, $4, 'saved', 'web')
     returning id, question, answer, request_type, status, created_at`,
    [userContext.userId, question, answer, requestType]
  );

  return formatHistoryRow(saved.rows[0]);
}

async function getHistory(client, userContext) {
  const result = await client.query(
    `select id, question, answer, request_type, status, created_at
     from diagnostic_requests
     where user_id = $1
     order by created_at desc
     limit 50`,
    [userContext.userId]
  );
  return result.rows.map(formatHistoryRow);
}

async function askN8n({ prompt, userId, vehicle }) {
  if (!webhookUrl) {
    return "Демо-ответ: подключите N8N_WEBHOOK_URL в .env. Начните с проверки ремня, роликов, генератора и помпы, затем считайте ошибки OBD2.";
  }

  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: prompt,
      text: prompt,
      prompt,
      source: "web",
      userId,
      user_id: userId,
      raw_user_id: userId,
      chat_id: userId,
      username: "web_user",
      first_name: "Web",
      vehicle
    })
  });

  if (!response.ok) throw new Error("n8n webhook returned an error");

  const raw = await response.text();
  try {
    const data = JSON.parse(raw);
    return data.reply || data.answer || data.message || data.output || JSON.stringify(data, null, 2);
  } catch (error) {
    return raw;
  }
}

app.get("/api/health", asyncRoute(async (req, res) => {
  requireDatabaseConfig();
  await pool.query("select 1");
  res.json({ ok: true, database: "postgresql" });
}));

app.get("/api/history", asyncRoute(async (req, res) => {
  requireDatabaseConfig();
  const webUserId = String(req.query.userId || "").trim();
  if (!webUserId) return res.status(400).json({ error: "userId is required" });

  const client = await pool.connect();
  try {
    const userContext = await getUserContext(client, webUserId);
    const items = await getHistory(client, userContext);
    const quota = await getQuota(client, userContext);
    res.json({ items, quota });
  } finally {
    client.release();
  }
}));

app.post("/api/history", asyncRoute(async (req, res) => {
  requireDatabaseConfig();
  const webUserId = String(req.body.userId || "").trim();
  const question = String(req.body.question || "").trim();
  const answer = String(req.body.answer || "").trim();
  if (!webUserId || !question || !answer) {
    return res.status(400).json({ error: "userId, question and answer are required" });
  }

  const client = await pool.connect();
  try {
    const userContext = await getUserContext(client, webUserId);
    const item = await saveDiagnosticRequest(client, {
      userContext,
      question,
      answer,
      requestType: req.body.type || "Текстовый запрос"
    });
    res.status(201).json({ item });
  } finally {
    client.release();
  }
}));

app.post("/api/chat", asyncRoute(async (req, res) => {
  requireDatabaseConfig();
  const webUserId = String(req.body.userId || "").trim();
  const prompt = String(req.body.prompt || req.body.message || "").trim();
  const vehicle = req.body.vehicle || {};
  if (!webUserId || !prompt) return res.status(400).json({ error: "userId and prompt are required" });

  const client = await pool.connect();
  try {
    const userContext = await getUserContext(client, webUserId);
    const quota = await getQuota(client, userContext);
    ensureQuotaAvailable(quota);

    const answer = await askN8n({ prompt, userId: webUserId, vehicle });
    const item = await saveDiagnosticRequest(client, {
      userContext,
      question: prompt,
      answer,
      requestType: "Текстовый запрос"
    });

    const updatedQuota = {
      ...quota,
      used: quota.used + 1,
      remaining: quota.unlimited ? null : Math.max(Number(quota.limit || 0) - quota.used - 1, 0)
    };

    res.json({ answer, item, quota: updatedQuota });
  } finally {
    client.release();
  }
}));

app.get("/", (req, res) => {
  res.sendFile(join(__dirname, "index.html"));
});

app.use((error, req, res, next) => {
  console.error(error);
  res.status(error.status || 500).json({
    error: error.message || "Server error",
    limitReached: Boolean(error.limitReached),
    quota: error.quota
  });
});

initializeDatabase()
  .then(() => {
    app.listen(port, () => {
      console.log(`CarDiagnostic AI is running on http://localhost:${port}`);
    });
  })
  .catch((error) => {
    console.error("Failed to initialize PostgreSQL:", error.message);
    process.exit(1);
  });
