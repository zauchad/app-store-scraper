# Monetization — go-live checklist (Phase 1)

Step-by-step setup for Supabase Auth, Lemon Squeezy payments, and the webhook
server. The dashboard runs on **Streamlit Cloud**; webhooks run on a **separate
host** (Railway, Render, Fly.io, etc.).

---

## Architecture

```
User → Streamlit Cloud (dashboard + Supabase login)
              ↓ same DATABASE_URL
         Supabase Postgres (users, credits, unlocks)

User → Lemon Squeezy checkout (?checkout[custom][user_id]=…)
              ↓ webhook POST
         Webhook server (FastAPI) → grant credits / set Pro plan
```

---

## Step 1 — Supabase (Auth + DB)

You likely already use Supabase Postgres for scan data. Auth uses the **same project**.

### 1.1 Enable Auth

1. [Supabase Dashboard](https://supabase.com/dashboard) → your project → **Authentication**.
2. **Providers** → Email → enable **Email** sign-in.
3. For faster onboarding during beta, you can disable “Confirm email” under
   **Authentication → Providers → Email** (re-enable before public launch).

### 1.2 API keys

1. **Project Settings → API**
2. Copy **Project URL** → `SUPABASE_URL`
3. Copy **anon public** key → `SUPABASE_ANON_KEY` (safe in Streamlit secrets)

### 1.3 Database

Use the same `DATABASE_URL` you already use for scans (IPv4 pooler recommended
for Streamlit Cloud). Billing tables (`users`, `credit_ledger`, `unlocked_niches`,
`webhook_events`) are created automatically on first dashboard load via `init_db()`.

---

## Step 2 — Lemon Squeezy (products + checkout)

### 2.1 Create products

In [Lemon Squeezy](https://app.lemonsqueezy.com/) create three products:

| Product | Type | Price | Credits / entitlements |
|---------|------|-------|------------------------|
| Single analysis | One-time | $19 | 1 credit |
| Niche pack | One-time | $49 | 5 credits |
| Pro | Subscription (monthly) | $39/mo | 15 credits/mo + CSV export |

For each product, set **Confirmation modal → Redirect URL** (optional) to your
Streamlit app so users return after paying:

```
https://YOUR-APP.streamlit.app/?payment=success
```

The dashboard shows a “payment received, refresh balance” notice automatically.

### 2.2 Checkout links

Each product has a share link like:

```
https://YOURSTORE.lemonsqueezy.com/checkout/buy/VARIANT_ID
```

The dashboard appends the logged-in user automatically:

```
…?checkout[custom][user_id]=SUPABASE_USER_UUID
```

Store the **base** URLs (without query params) in secrets:

```toml
LEMONSQUEEZY_CHECKOUT_1_CREDIT = "https://….lemonsqueezy.com/checkout/buy/123456"
LEMONSQUEEZY_CHECKOUT_5_CREDITS = "https://….lemonsqueezy.com/checkout/buy/123457"
LEMONSQUEEZY_CHECKOUT_PRO = "https://….lemonsqueezy.com/checkout/buy/123458"
LEMONSQUEEZY_VARIANT_1_CREDIT = "123456"
LEMONSQUEEZY_VARIANT_5_CREDITS = "123457"
LEMONSQUEEZY_VARIANT_PRO = "123458"
```

Variant IDs are used by the **webhook server** to map payments → credit amounts.

### 2.3 Test mode

Use Lemon Squeezy **test mode** first. Test card: `4242 4242 4242 4242`.

---

## Step 3 — Webhook server (separate deploy)

Streamlit Cloud cannot receive inbound webhooks. Deploy the FastAPI app elsewhere.

### 3.1 Deploy (Railway example)

1. New project → **Deploy from GitHub repo**.
2. Set **Start command**:
   ```bash
   uvicorn billing.webhook_server:app --host 0.0.0.0 --port $PORT
   ```
   Or use the included `Dockerfile` / `Procfile`.
3. **Environment variables** (same DB as dashboard):
   ```env
   DATABASE_URL=postgresql+psycopg2://…
   LEMONSQUEEZY_WEBHOOK_SECRET=your_random_secret_6_to_40_chars
   LEMONSQUEEZY_VARIANT_1_CREDIT=123456
   LEMONSQUEEZY_VARIANT_5_CREDITS=123457
   LEMONSQUEEZY_VARIANT_PRO=123458
   PRO_MONTHLY_CREDITS=15
   ```
4. Note the public URL, e.g. `https://your-app.up.railway.app`.

### 3.2 Register webhook in Lemon Squeezy

1. **Settings → Webhooks → Create webhook**
2. **URL**: `https://your-app.up.railway.app/webhooks/lemon-squeezy`
3. **Signing secret**: same string as `LEMONSQUEEZY_WEBHOOK_SECRET`
4. **Events** (register all of these):
   - `order_created`
   - `subscription_created`
   - `subscription_payment_success`
   - `subscription_cancelled`
   - `subscription_expired`

### 3.3 Health check

```bash
curl https://your-app.up.railway.app/health
# → {"status":"ok"}
```

---

## Step 4 — Streamlit Cloud secrets

In **App → Settings → Secrets**, add:

```toml
DATABASE_URL = "postgresql+psycopg2://…"

MONETIZATION_ENABLED = "true"
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_ANON_KEY = "eyJ…"

LEMONSQUEEZY_CHECKOUT_1_CREDIT = "https://….lemonsqueezy.com/checkout/buy/…"
LEMONSQUEEZY_CHECKOUT_5_CREDITS = "https://…"
LEMONSQUEEZY_CHECKOUT_PRO = "https://…"
LEMONSQUEEZY_VARIANT_1_CREDIT = "123456"
LEMONSQUEEZY_VARIANT_5_CREDITS = "123457"
LEMONSQUEEZY_VARIANT_PRO = "123458"

# Optional
PRO_MONTHLY_CREDITS = "15"
SIGNUP_BONUS_CREDITS = "0"
```

Redeploy the Streamlit app after saving secrets.

> **Note:** `LEMONSQUEEZY_WEBHOOK_SECRET` is only needed on the **webhook server**,
> not on Streamlit.

---

## Step 5 — Validate config

Locally (with `.env` mirroring prod secrets):

```bash
python run.py billing-check --strict
```

Expected output: `✅ Billing configuration looks ready.`

---

## Step 6 — End-to-end test

1. Open dashboard → sidebar **Konto** → **Rejestracja** → create account.
2. Confirm sidebar shows **Kredyty: 0** (or signup bonus if configured).
3. Go to **Analiza** → pick a niche → see free preview + paywall.
4. Click **Pro — $39/mo** (or 1-credit pack) → complete test checkout.
5. Wait ~10s → refresh dashboard → credits should increase.
6. Click **Odblokuj (1 kredyt)** → full analysis appears.
7. On **Radar**, CSV button should appear only for Pro users.

### Troubleshooting

| Symptom | Check |
|---------|--------|
| Login fails | Supabase Auth enabled, correct URL/anon key |
| Credits stay 0 after payment | Webhook server logs; Lemon Squeezy webhook delivery tab |
| Webhook 401 | `LEMONSQUEEZY_WEBHOOK_SECRET` matches on both sides |
| Credits granted to wrong user | Checkout URL must include `checkout[custom][user_id]` (auto from dashboard) |
| `missing user_id` in webhook logs | User must buy while logged in (links append user_id) |

### Simulate webhook locally (no Lemon Squeezy)

```bash
python run.py billing-check --simulate-webhook --user-id YOUR_SUPABASE_UUID
python run.py billing-check --simulate-webhook --user-id YOUR_UUID --event subscription_created --variant pro
python run.py billing-check --simulate-webhook --user-id YOUR_UUID --event subscription_expired
```

---

## Subscription lifecycle

| Event | What happens |
|-------|----------------|
| `subscription_created` / `subscription_resumed` | Plan → **Pro** (CSV export enabled) |
| `subscription_payment_success` | +15 credits/mo, plan stays **Pro** |
| `subscription_cancelled` | No change — user keeps Pro until period ends |
| `subscription_expired` | Plan → **Free** — CSV locked; credits & niche unlocks kept |

---

## Next steps (Phase 1 polish)

- Mikro-nisze detail paywall

---

## What users see (pricing)

| Tier | Access |
|------|--------|
| **Free** | Radar (top 5 nisz + 3 nazwy apek/sekcja), Mikro-nisze browse, Analiza preview |
| **1 credit ($19)** | Full Analiza for one niche, forever |
| **5 credits ($49)** | Five niche unlocks |
| **Pro ($39/mo)** | 15 credits/mo + CSV export on Radar & Mikro-nisze |
