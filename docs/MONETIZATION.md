# Monetization — go-live checklist

Step-by-step setup for Supabase Auth, Lemon Squeezy payments, and the webhook
server. The dashboard runs on **Streamlit Cloud**; webhooks run on a **separate
host** (Railway, Render, Fly.io, etc.).

---

## Architecture

```
User → Streamlit Cloud (dashboard + Supabase login)
              ↓ same DATABASE_URL
         Supabase Postgres (users, credits, unlocks, funnel events)

User → Lemon Squeezy checkout
       (?checkout[custom][user_id]=…&checkout[custom][niche_key]=…)
              ↓ webhook POST
         Webhook server (FastAPI) → grant credits → unlock that exact niche
              ↓ (dashboard polls)
         Content opens in the tab the user already has open
```

The buyer never has to find their way back to what they paid for: the niche they
were looking at travels with the checkout and is unlocked by the webhook.

---

## Step 1 — Supabase (Auth + DB)

You likely already use Supabase Postgres for scan data. Auth uses the **same project**.

### 1.1 URLs (required for every e-mail / OAuth flow)

1. **Authentication → URL Configuration**
2. **Site URL**: `https://YOUR-APP.streamlit.app`
3. **Redirect URLs**: add the same URL (and `http://localhost:8501` for local work).
4. Put the same value in `APP_BASE_URL` (secrets) — the app builds its OAuth and
   e-mail redirects from it.

### 1.2 Sign-in methods

| Method | Setup | Why it matters |
|--------|-------|----------------|
| **Google** (recommended) | **Auth → Providers → Google**: enable, paste Google OAuth client id/secret, then set `AUTH_GOOGLE_ENABLED=true` | One click, no password, no e-mail round trip — the cheapest signup you can offer |
| **E-mail code** (default on) | Works with the built-in e-mail provider once the template below contains the token | No password to invent; nothing to remember on the next visit |
| **E-mail + password** | **Auth → Providers → Email**: enable | Fallback for people who prefer it |

Google's authorized redirect URI (in Google Cloud Console) must be
`https://YOUR-PROJECT.supabase.co/auth/v1/callback`.

### 1.3 E-mail templates (important)

Streamlit **cannot read URL fragments**, which is where Supabase puts tokens by
default — that is why the untouched templates make "confirm e-mail" and "reset
password" links land on a page that does nothing. Change them to query-param
links under **Authentication → Emails → Templates**:

**Confirm signup**
```html
<a href="{{ .SiteURL }}/?token_hash={{ .TokenHash }}&type=email">Potwierdź e-mail</a>
```

**Reset password**
```html
<a href="{{ .SiteURL }}/?token_hash={{ .TokenHash }}&type=recovery">Ustaw nowe hasło</a>
```

**Magic Link** — add the code so passwordless sign-in works:
```html
<p>Twój kod: <strong>{{ .Token }}</strong></p>
```

With those in place the app finishes the flow itself: confirmation logs the user
straight in, and a recovery link opens the "set a new password" form.

### 1.4 API keys

1. **Project Settings → API**
2. **Project URL** → `SUPABASE_URL`
3. **anon public** key → `SUPABASE_ANON_KEY` (safe in Streamlit secrets)

Auth is called over plain REST (`dashboard/supabase_auth.py`), so no
`supabase-py` dependency is needed.

### 1.5 Database

Use the same `DATABASE_URL` you already use for scans (IPv4 pooler recommended
for Streamlit Cloud). Billing tables (`users`, `credit_ledger`, `unlocked_niches`,
`webhook_events`, `pending_grants`, `funnel_events`) are created automatically on
first dashboard load via `init_db()`.

---

## Step 2 — Lemon Squeezy (products + checkout)

### 2.1 Create products

| Product | Type | Price | Credits / entitlements |
|---------|------|-------|------------------------|
| Single niche | One-time | $19 | 1 credit |
| Pro | Subscription (monthly) | $39/mo | 15 credits/mo + CSV export + full Radar |

> The old **5 credits / $49** pack is hidden by default (`CREDIT_PACK_ENABLED=false`):
> Pro gives 15 credits for less money, so the pack only muddied the choice.
> Webhooks still honour it for anyone who bought it before.

For each product set **Confirmation modal → Redirect URL** to:

```
https://YOUR-APP.streamlit.app/?payment=success
```

### 2.2 Checkout links

Store the **base** URLs (no query params) in secrets:

```toml
LEMONSQUEEZY_CHECKOUT_1_CREDIT = "https://….lemonsqueezy.com/checkout/buy/123456"
LEMONSQUEEZY_CHECKOUT_PRO = "https://….lemonsqueezy.com/checkout/buy/123458"
LEMONSQUEEZY_VARIANT_1_CREDIT = "123456"
LEMONSQUEEZY_VARIANT_PRO = "123458"
```

The dashboard appends, per click:

```
?checkout[custom][user_id]=SUPABASE_UUID
&checkout[email]=buyer@example.com          # prefilled, one less field
&checkout[custom][niche_key]=category:us:6015  # what to unlock on payment
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
   - `order_refunded`
   - `subscription_created`
   - `subscription_payment_success`
   - `subscription_payment_failed`
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
APP_BASE_URL = "https://YOUR-APP.streamlit.app"

# Onboarding: 1 = new accounts get one free unlock (recommended)
SIGNUP_BONUS_CREDITS = "1"
AUTH_GOOGLE_ENABLED = "true"
AUTH_OTP_ENABLED = "true"

LEMONSQUEEZY_CHECKOUT_1_CREDIT = "https://….lemonsqueezy.com/checkout/buy/…"
LEMONSQUEEZY_CHECKOUT_PRO = "https://…"
LEMONSQUEEZY_VARIANT_1_CREDIT = "123456"
LEMONSQUEEZY_VARIANT_PRO = "123458"

# Optional
PRO_MONTHLY_CREDITS = "15"
CREDIT_PACK_ENABLED = "false"
FREE_DAILY_KEYWORD_SCANS = "3"
SUPPORT_EMAIL = "hello@yourdomain.com"
LEMONSQUEEZY_CUSTOMER_PORTAL_URL = "https://your-store.lemonsqueezy.com/billing"
# BILLING_ADMIN_SECRET = "..."  # webhook server only, for grant-credits CLI
```

Redeploy the Streamlit app after saving secrets.

> **Note:** `LEMONSQUEEZY_WEBHOOK_SECRET` is only needed on the **webhook server**,
> not on Streamlit.

> **Local development:** set `MONETIZATION_ENABLED=false` in `.env` for full access
> without login. Leaving it `true` without Supabase keys shows a config error on
> the landing page and nothing else — by design, so a broken deploy never
> silently gives the product away.

---

## Step 5 — Validate config

```bash
python run.py billing-check --strict
```

Expected output: `✅ Billing configuration looks ready.`

---

## Step 6 — End-to-end test

1. Open dashboard → **Załóż konto** → sign up with Google or an e-mail code.
2. Sidebar shows **Kredyty: 1** (the signup bonus).
3. **Analiza** → pick a niche → the gate offers a one-click unlock. Use it: the
   full report opens and the balance drops to 0.
4. Pick a *second* niche → the gate now shows **Pro** and **1 nisza — $19**.
5. Click a plan → pay with the test card → return to the tab you left open.
   Within a few seconds the page refreshes itself and the niche is unlocked.
6. On **Radar**, the CSV button appears only for Pro users.
7. `python run.py funnel --days 1` shows the steps you just walked through.

### Troubleshooting

| Symptom | Check |
|---------|--------|
| Login fails | Supabase Auth enabled, correct URL/anon key |
| Google button missing | `AUTH_GOOGLE_ENABLED=true` **and** `APP_BASE_URL` set |
| Google returns "logowanie wygasło" | `APP_BASE_URL` must be in Supabase → Redirect URLs |
| E-mail code never arrives / has no code | Magic Link template needs `{{ .Token }}` |
| Confirmation / reset link does nothing | Templates must use `?token_hash=…&type=…` (Step 1.3) |
| Credits stay 0 after payment | Webhook server logs; Lemon Squeezy webhook delivery tab |
| Webhook 401 | `LEMONSQUEEZY_WEBHOOK_SECRET` matches on both sides |
| Paid niche not auto-unlocked | Checkout URL must carry `checkout[custom][niche_key]` (auto from the gate) |
| Bought while logged out | Credits are parked on the buyer's e-mail and granted on first login (`pending_grants`) |

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
| `subscription_payment_failed` | Logged only — access continues through dunning |
| `subscription_cancelled` | No change — user keeps Pro until period ends |
| `subscription_expired` | Plan → **Free** — CSV locked; credits & niche unlocks kept |

Payment safety: the idempotency marker is rolled back if a credit grant fails, so
a Lemon Squeezy retry still pays out instead of being swallowed as a duplicate.

---

## Measuring conversion

```bash
python run.py funnel --days 30
```

Steps recorded (`funnel_events`): landing view → signup → login → paywall view →
checkout view → purchase → unlock → Pro activation → refund, plus the two ratios
that matter (signup → purchase, paywall → purchase). Look at **paywall → purchase**
first: if people see the gate and do not buy, the problem is the offer or the
preview, not the traffic.

---

## What users see (pricing)

| Tier | Access |
|------|--------|
| **Free** | Radar (top 5 nisz + 3 nazwy apek/sekcja), Mikro-nisze ranking + podgląd frazy, Analiza preview, **1 darmowe odblokowanie** |
| **1 nisza ($19)** | Full **Analiza** OR **Mikro-nisza** detail for one niche, forever |
| **Pro ($39/mo)** | 15 credits/mo + CSV export on Radar & Mikro-nisze + full Radar rows |
