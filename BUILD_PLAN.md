# Indian Market Portfolio Intelligence Agent — Refined Build Plan

**Version:** 1.0 (implementation plan) · **Date:** 2026-07-10
**Companion to:** `Zerodha_Indian_Market_Portfolio_Agent_Spec.docx`

> **Boundary (unchanged from spec):** Read-only, advisory decision-support. No automated trading. Every recommendation carries reasoning, confidence, and evidence. Commercial/public use requires SEBI IA/RA review — this plan assumes **private personal use**.

---

## 0. Locked decisions

| Decision | Choice | Why |
|---|---|---|
| **Agent host** | Dedicated **Intel NUC** running Ubuntu Server LTS, headless, 24/7 | Right home for systemd timers, Docker, FastAPI; isolates the server from machines you use |
| **iOS build host** | **Mac mini** (Xcode) | Native SwiftUI WidgetKit can only be built/signed on macOS |
| **Phone ↔ NUC link** | **Tailscale** private network | Phone reaches `widget.json` anywhere, encrypted, no public exposure — satisfies spec's "private environment" |
| **Language** | Python 3.12 | Matches spec; best Zerodha/data ecosystem |
| **Broker SDK** | `kiteconnect` (pykiteconnect) | Official Zerodha SDK |
| **DB** | **PostgreSQL** in Docker on the NUC, via SQLAlchemy + Alembic | Durable audit store; SQLAlchemy keeps it swappable; Alembic for schema evolution |
| **Analytics** | pandas, numpy, **pandas-ta** | pandas-ta is pure-Python (avoids ta-lib's C build pain) |
| **Scheduler** | **systemd timer** on the NUC | More robust than cron; logs to journald; handles failures/retries |
| **API layer** | **FastAPI + uvicorn**, bearer-token auth | Serves `widget.json` to the phone widget |
| **LLM reasoning** | **Anthropic Claude API** — Sonnet 5 for daily runs, Opus 4.8 for weekly deep-dives | Strong reasoning; you're already in the Claude ecosystem; cost-tiered by cadence |
| **iOS widget** | **Native SwiftUI WidgetKit** app | Your choice — Apple-Stocks-grade polish |
| **Secrets (V1)** | `.env` (gitignored, `chmod 600`) + `pyotp` for Kite TOTP; **age-encrypted** secrets file as the step-up | Practical for personal use; vault noted as future hardening |

### Recurring cost budget
Verified against Zerodha docs (2026-07): **no separate historical-data add-on** — the ₹500/month
Connect plan bundles real-time + historical candles. Holdings/positions are on the **free Personal**
plan, so **Phase 1 costs ₹0**; the ₹500/month is only needed from **Phase 2** (candles/technicals).

| Item | Cost |
|---|---|
| Kite Connect — Personal plan (holdings/positions) | **Free** (Phase 1) |
| Kite Connect — Connect plan (real-time + historical candles, bundled) | ₹500 / month (from Phase 2) |
| Anthropic API (daily Sonnet + occasional Opus) | ~₹500–1,500 / month, usage-dependent |
| Apple Developer Program (persistent widget signing) | $99 / year *(see §7)* |
| Hosting | ₹0 (your NUC + home power) |
| **Approx. total (once fully live)** | **~₹1,000–2,000 / month + $99/yr** |

---

## 1. The two hard problems (solve these first, everything else is plumbing)

### 1a. Zerodha's daily token expiry
Kite's `access_token` expires every morning and normally needs an interactive login with TOTP 2FA. Full automation requires refreshing it **before** the morning job.

**Approach:** `auth/kite_login.py` performs a headless login using your `api_key`, `api_secret`, Kite user id, password, and **TOTP secret** (via `pyotp`) to obtain the daily `request_token` → `access_token`, cached to an encrypted file with the day's date. The morning job depends on this step succeeding; on failure it alerts you (Telegram/push) and runs in degraded mode (holdings snapshot only, no fresh analytics).

> This is grey-area vs. Kite ToS but standard for personal automation. Keep it strictly personal.

### 1b. Data beyond your portfolio
Kite gives you **your holdings + prices + candles**. It does **not** give fundamentals, filings, news, or new-stock ideas. Locked sources:

| Need | Source | Notes |
|---|---|---|
| Holdings, P&L, positions, orders | **Kite Connect** | Official |
| Historical candles (24-day technicals) | **yfinance / NSE bhavcopy (FREE)** behind a swappable market-data connector | Kite historical (₹500/mo) is an optional drop-in later — free covers the EOD daily-run need |
| **Daily market activity / order flow** *(see §5.5)* | **NSE/BSE daily bhavcopy + delivery data, bulk/block deals, FII/DII flows** | Free/official; the buy-vs-sell "who's-behind-the-move" layer |
| Corporate actions & announcements | **NSE/BSE official pages** | Free, authoritative, primary thesis-change signal |
| Fundamentals (revenue, margins, ROCE, debt, valuation) | **screener.in** (scrape) | Grey-area ToS; personal use. Trendlyne/Tickertape as alternates |
| News | RSS from Moneycontrol/ET/BusinessLine + optional news API | Allowlist only; social tips excluded or labeled low-confidence |
| Sentiment | **LLM over the above** | Not a separate feed — derived |
| New-stock screening | **screener.in custom screens** → LLM synthesis | Clearly labeled Low/Medium confidence |

---

## 2. Repository structure

```
portfolio-agent/
  app/
    auth/
      kite_login.py          # daily token refresh (TOTP)
    connectors/
      zerodha.py             # holdings, positions, orders, candles
      market_data.py         # index candles, gap-fill
      fundamentals.py        # screener.in fetch/parse
      news.py                # RSS + NSE/BSE announcements (allowlisted)
    analytics/
      technicals.py          # 1/5/20D returns, RSI, MAs, vol spike, rel-strength
      fundamentals.py        # score financial quality/trajectory
      portfolio_risk.py      # concentration, sector, drawdown, correlation
      order_flow.py          # delivery %, volume, bulk/block deals, FII/DII (§5.5)
      screener.py            # new-stock idea generation
    reasoning/
      prompts.py             # prompt templates + guardrail wrappers
      recommender.py         # per-stock scoring -> classification
      thesis.py              # thesis-change detection vs stored thesis
    reports/
      daily_report.py        # markdown/HTML report
      widget_json.py         # writes widget.json for the iOS app
    api/
      main.py                # FastAPI: /widget.json (auth), /report/latest
    storage/
      models.py              # SQLAlchemy models
      db.py                  # session/engine
    safety/
      guardrails.py          # bounded-language enforcement, disclaimers
    jobs/
      morning_run.py         # orchestrates the full daily workflow
  ios/
    PortfolioWidget/         # Xcode project (built on Mac mini)
  migrations/                # Alembic
  tests/
  config.example.yaml
  theses.yaml                # YOUR original reason for owning each stock
  pyproject.toml
  README.md
```

**`theses.yaml` is the heart of the product** — it encodes *why you bought each stock*, so the agent can judge "is the thesis still intact?" rather than just reacting to price. Example:
```yaml
TCS:
  thesis: "Durable cash generation + dividend; large-cap IT stability anchor."
  conviction: high
  target_weight_pct: 8
  exit_if:
    - "Two consecutive quarters of revenue decline"
    - "Dividend policy materially cut"
    - "Large-deal TCV collapses / attrition spikes structurally"
```

---

## 3. Data model (audit-first — spec §12 requirement)

Every daily run is **immutable and reproducible**. Core tables:

- `snapshots(id, run_date, kind, payload_json, source, fetched_at)` — raw inputs frozen
- `holdings(run_date, symbol, qty, avg_price, ltp, pnl, weight_pct, sector)`
- `metrics(run_date, symbol, ret_1d, ret_5d, ret_20d, drawdown, rsi, vol_spike, rel_strength)`
- `scores(run_date, symbol, thesis, fundamental, technical, valuation, news_risk, portfolio_fit)`
- `recommendations(run_date, symbol, classification, confidence, reason, evidence_json, prev_classification)`
- `reports(run_date, format, path, summary)`
- `events(run_date, symbol, type, title, url, severity)` — announcements/news
- `llm_calls(run_date, model, prompt_hash, tokens, cost, output_ref)` — cost + audit trail

`prev_classification` enables the **"what changed since last report"** diff you asked for.

---

## 4. Daily morning workflow (`jobs/morning_run.py`)

Fires via systemd timer ~**07:30 IST** (before 09:15 open). Idempotent per `run_date`.

1. **Refresh token** (`auth/kite_login.py`) → fail loud if it can't.
2. **Fetch & freeze** holdings, positions, orders, trades, instrument master → `snapshots`.
3. **Candles**: last 24 trading days for each holding + NIFTY 50 / NIFTY 500 / relevant sector indices.
4. **Research pull**: NSE/BSE announcements, results calendar, allowlisted news, fundamentals (delta vs last run).
5. **Compute position metrics** → `metrics`.
6. **Compute portfolio metrics**: total P&L, concentration, sector exposure, winners/losers, drawdown, correlation clusters.
7. **Thesis checks** per stock against `theses.yaml` (`reasoning/thesis.py`).
8. **Score & classify** (`reasoning/recommender.py`) → Hold / Watch / Accumulate / Trim / Exit Candidate, with **diff vs previous day**.
9. **LLM narrative** (`reasoning/`) — summarize changes, cite evidence, flag open questions. Guardrails enforce bounded language (no "will go up", no "sell tomorrow for sure").
10. **Render** report (HTML/markdown) + **write `widget.json`**.
11. **Persist** everything to DB (`reports`, `recommendations`, `llm_calls`).
12. **Deliver**: email/Telegram push of the report; widget endpoint now serves fresh data.
13. **(Weekly)** new-stock screen + Opus deep-dive appended.

---

## 5. Scoring → classification (research-backed)

> Fully derived from `RESEARCH_DECISION_METHODS.md` (5-way research pass on how real investors
> decide). That doc is the source of truth for thresholds; this section is the model design.

### 5.0 The governing principle (the safeguard)
**A falling price is not a sell signal; falling fundamentals are.** So the model triggers on two
tracks, which directly serves the user's goal ("know when to exit and not lose money"):

- **Technical / price signals → WATCH + risk alerts** (never force a sell alone — anti-whipsaw).
- **Fundamental / thesis / governance signals → TRIM / EXIT.**
- **Valuation-extreme → TRIM only** (a great business at a stretched price is trimmed, not dumped).
- **Solvency or governance breach → EXIT regardless of every other score** (hard override).

### 5.1 Six sub-scores, each normalized 0–100 (higher = more bullish)
Pipeline per metric: winsorize (±3σ / 5th–95th pct) → normalize (sector-relative **percentile rank**
default, or `50 + 16.7×clip(z,−3,3)`) → sign so higher is better.

| Sub-score | Raw inputs | Method |
|---|---|---|
| **Thesis** | `theses.yaml` `exit_if` checks; conviction rubric; count of active deterioration signals | confidence-bearing |
| **Fundamental** | ROCE/ROE level+trend, margin trend, rev/EPS growth, interest coverage, D/E, OCF/PAT, FCF sign | quality composite (MSCI/Novy-Marx style) |
| **Technical** | 12-1 momentum, price vs 50/200-DMA, RSI(14) regime, rel-strength vs Nifty, volume | fast-decaying; refresh daily |
| **Valuation** | sector-relative P/E, EV/EBITDA, P/B, FCF yield; percentile vs own 5-yr range | always sector-neutralize |
| **News-risk** *(inverted)* | analyst-revision breadth, news sentiment polarity, event flags | high risk → low score |
| **Portfolio-fit** | position weight vs cap, sector & top-5 concentration, correlation cluster, drawdown state | penalizes concentration |

### 5.2 Composite → classification
`composite = Σ(wᵢ × sub-scoreᵢ)`. **Default weights (medium-term):** Fundamental 25 · Valuation 20 ·
Technical 20 · Thesis 15 · News-risk 12 · Portfolio-fit 8. Equal-ish weighting is deliberate — factor
timing is hard; don't over-tune before Phase 5 backtesting. A **confidence factor** C∈[0.5,1] (from data
completeness + signal agreement) pulls the effective score toward 50 when evidence is thin.

| Composite (with ±3 pt hysteresis) | Classification |
|---|---|
| ≥ 75 | **Accumulate Candidate** |
| 60–74 | **Watch** (constructive — add on confirmation) |
| 45–59 | **Hold** |
| 30–44 | **Trim Candidate** |
| < 30 | **Exit Candidate** |

**Hysteresis:** require the score to cross ~3 pts *further* to change a rating than to keep it (kills churn).
Widen the bands when confidence C is low or for illiquid/small-caps (Morningstar uncertainty-scaling).

### 5.3 Hard-override rules (fire regardless of composite → straight to EXIT-CANDIDATE)
Interest coverage < 1.5× · net-debt/EBITDA > 4× & rising · **auditor resignation (12 mo)** · qualified/adverse
audit opinion · **promoter pledge > 50% or invocation** · SEBI/ED/IT/GST action / NCLT-IBC · **Beneish M > −1.78**
· **Altman Z < 1.81** · dividend cut by a consistent payer · FCF negative 2 yrs while PAT positive.

### 5.4 Confidence-decay state machine (the exit engine)
`Core → Watch → Exit-Candidate → Exit`. Each independent active deterioration signal costs 1 conviction
point: **1 signal = monitor, ≥2 = Watch, ≥3 (or any solvency/governance signal) = Exit-Candidate.** Any
Exit-Candidate gets a **"would I buy this today?" re-underwrite** against the original entry screen — fail ⇒ Exit, pass ⇒ back to Watch.

**Classification is deterministic rules first (transparent, testable, backtestable), LLM narrates second —
never the reverse.** Every classification is logged with its six sub-scores + weights so a discretionary
override is auditable. All thresholds live in `config.yaml`, tuned in Phase 5.

### 5.5 Market-activity / order-flow sentiment *(added requirement)*
Beyond price, monitor **who is actually buying and selling** each holding daily — this reveals the
*conviction* behind a move and is a strong, India-specific sentiment input. It is **confirmation, not a
standalone trigger** (per the research: sentiment gates other signals, it doesn't drive exits alone).

| Signal | What it tells us | Source (free/official) |
|---|---|---|
| **Delivery volume & delivery %** | Shares taken to demat vs intraday churn. High delivery % on up-days = genuine accumulation; low = speculative froth. *India's cleanest conviction signal.* | NSE/BSE daily bhavcopy (delivery) |
| **Volume vs 20/50-day average** | Volume spike confirms (or fails to confirm) a price move | Kite candles / bhavcopy |
| **Bulk & block deals** | Large named trades in *your* stocks — institutional/big-player accumulation or distribution | NSE/BSE daily bulk & block deals |
| **FII/DII net flows** | Aggregate (and where disclosed, stock-level) institutional buy/sell pressure = market-wide risk-on/off | NSE/BSE / exchange dailies |
| **Advance/decline & delivery-based buy pressure** | Breadth context for the move | bhavcopy |

**How it plugs into the model:**
- Feeds the **Technical** sub-score (volume-confirmed vs unconfirmed moves) and the **News-risk/sentiment**
  sub-score (distribution by big players raises risk; accumulation lowers it).
- Acts as a **confidence modulator (C)** — e.g. a WATCH driven by a price drop that coincides with heavy
  *delivery-based selling / block-deal distribution* gets higher confidence and can escalate; the same
  price drop on thin, low-delivery volume stays a low-confidence WATCH (anti-whipsaw holds).
- **Never flips Hold→Exit by itself** — it strengthens or weakens signals the fundamentals/thesis already raised.

**Build placement:** data **ingestion in Phase 2** (alongside candles — same bhavcopy/exchange feeds);
**used in scoring/narrative in Phase 4**. New module: `analytics/order_flow.py`.

---

## 6. Phased delivery (each phase independently runnable & tested)

| Phase | Scope | Done when |
|---|---|---|
| **0** | Repo skeleton, config, secrets, Postgres+Docker on NUC, Alembic schema, **mock portfolio** | `pytest` green; runs with zero real credentials |
| **1** | Zerodha auth (TOTP refresh) + read-only holdings/positions connector | Daily snapshot lands in DB from your real account |
| **2** | Candle ingestion + technical metrics + index comparison + **order-flow ingestion** (delivery %, volume, bulk/block, FII/DII — §5.5) | 24-day analytics per holding |
| **3** | Deterministic report + **`widget.json`** (no LLM yet) | HTML report + JSON served by FastAPI over Tailscale |
| **4** | LLM narrative + citations + guardrails + classifications | Evidence-backed daily report with Hold/Watch/Trim/Exit |
| **5** | Backtesting + recommendation QA | Watch/Trim/Exit flags scored at 7/30/90 days; thresholds tuned |
| **6** | New-stock screening module | Weekly labeled ideas with reasoning |
| **7** | **SwiftUI WidgetKit app** + delivery (email/Telegram) | Widget on your home screen showing prices + recommendations |
| **8 (future)** | Mutual funds (Coin/MF): XIRR, overlap, direct-vs-regular, allocation | Unified stock+MF view |

> Phases 3 and 7 together deliver the widget. You can pull Phase 7's *backend half* (the JSON) forward into Phase 3 and build the app once data flows.

---

## 7. iOS Native Widget (SwiftUI WidgetKit)

**Built on the Mac mini in Xcode.**

- **Project shape:** a thin container app + a **Widget Extension** target. The container app holds settings (endpoint URL, bearer token, entered once).
- **Data flow:** Widget's `TimelineProvider` fetches `https://<nuc-tailscale-name>/widget.json` with a bearer token → decodes into Swift models → renders.
- **`widget.json` shape:**
  ```json
  {
    "as_of": "2026-07-10T07:35:00+05:30",
    "portfolio": { "value": 2450000, "day_change_pct": -0.8, "attention_count": 3 },
    "holdings": [
      { "symbol": "TCS", "name": "Tata Consultancy",
        "ltp": 3890.5, "change_pct": 1.2,
        "classification": "Hold", "confidence": "Medium-High",
        "thesis_status": "intact" }
    ]
  }
  ```
- **Widget families:** `systemMedium` (top movers + attention count), `systemLarge` (fuller list). Color the classification badge (Hold=neutral, Watch=amber, Exit=red).
- **Refresh:** `TimelineProvider` requests a reload ~hourly; the meaningful refresh is post-morning-run. WidgetKit budgets refreshes, so don't expect tick-by-tick — this is a **daily-recommendation** widget, not a live ticker (that matches the product intent).
- **Signing:** use the **$99/yr Apple Developer Program**. The free personal team works but **re-provisioning expires every 7 days** — unacceptable for a home-screen widget you want to persist. Paid = install once, valid a year.
- **Networking:** Tailscale on the iPhone puts the NUC in reach anywhere; the widget just hits the tailnet hostname over HTTPS (self-signed cert pinned, or Tailscale's own MagicDNS + serve).

---

## 8. Security checklist (spec §12)

- [ ] Kite read-only where possible; **never** enable order APIs in V1
- [ ] Secrets in `.env` (chmod 600, gitignored); TOTP secret + tokens **age-encrypted** at rest
- [ ] Postgres fields with account id / tokens / holdings encrypted at column level
- [ ] NUC firewalled; widget endpoint reachable **only** over Tailscale, bearer-token required
- [ ] Every external call + every recommendation logged (`llm_calls`, `events`)
- [ ] Source allowlist enforced in `connectors/news.py`; social tips excluded or labeled low-confidence
- [ ] Disclaimers embedded in every report and widget ("decision support, not advice")

---

## 9. Open decisions for you (before Phase 4+)

1. **Fundamentals source** — screener.in scrape (free, grey-area) vs a paid API (Trendlyne/Tickertape). Affects reliability & ToS comfort.
2. **News API** — free RSS only, or budget for a paid news feed for better sentiment coverage.
3. **Delivery channel** — email, Telegram bot, or both, in addition to the widget.
4. **Apple Developer Program** — confirm you'll enroll ($99/yr) for a persistent widget.
5. **Backtest horizon** — how many months of history to seed Phase 5 QA.

---

## 10. Immediate next step

Start **Phase 0**: scaffold the repo, Docker Postgres on the NUC, Alembic schema, and a **mock portfolio** so the whole pipeline runs end-to-end with zero credentials. That de-risks everything before we touch your live Zerodha account.
