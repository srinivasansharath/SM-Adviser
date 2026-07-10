# How Stock Trade Decisions Are Made — Research Findings

**Purpose:** ground the agent's scoring/classification model in how real investors and traders
actually decide. Compiled 2026-07-10 from a 5-way parallel web-research pass (exit/risk,
thesis-break, selection/entry, signal fusion, India-specific). Citations at the end of each
section. The consolidated rule catalog (§7) feeds directly into `BUILD_PLAN.md §5`.

---

## 0. The one principle everything rests on

> **A falling *price* is not a sell signal. Falling *fundamentals* are.**

Every source converges on this. The costly investor error is anchoring — refusing to sell a
deteriorating business because you're down and waiting to "get back to even." The agent's job,
and the user's stated #1 goal ("know when to exit and not lose money"), is precisely to
distinguish **"the market disagrees with me" (hold)** from **"the business proved me wrong" (sell)**.
The intellectual-honesty test the whole literature shares: *"If I didn't own this today, would I
buy it at this price?"* A "no" means sell.

Design consequence: **price/technical signals trigger WATCH and risk alerts; fundamental,
thesis, and governance signals trigger TRIM/EXIT.** Price alone never forces a downgrade
(anti-whipsaw). This split is the backbone of the scoring model.

---

## 1. Exit & risk management

### Stop-losses (systematic + discretionary)
- **Fixed-%:** momentum/trading uses a hard **−7-8%** from buy (O'Neil/CAN SLIM); long-term core uses **−15-25%**. `stop = entry × (1−x)`. Simple but volatility-blind → whipsaws on high-beta names.
- **Volatility (ATR):** `stop = close − m×ATR(14)`, **m = 2-3.5 (3 default)**. Auto-scales to each stock's noise. **Chandelier Exit** (trailing): `HighestHigh(22) − 3×ATR(22)`.
- **Trailing:** ratchets up, never down; locks gains, guaranteed to give some back at the top.
- **Time-based:** exit "dead money" that hasn't performed in N days, or event trades after the catalyst.
- *Discretionary overlay:* humans widen/tighten the multiple by conviction, liquidity, and whether a drop is news-driven vs. market-wide.

### Position sizing
- **Fixed-fractional (the professional core):** risk a constant **1-2% of equity per position**. `shares = (equity × risk%) / (entry − stop)`. Ties size to stop distance → volatile names get smaller allocations automatically.
- **Kelly:** `f* = (b·p − q)/b`; full Kelly maximizes growth but has brutal drawdowns and is hypersensitive to a mis-estimated win-rate. Practitioners use **half-Kelly** (~75% of the growth, far less drawdown). Treat as an upper bound.
- **Volatility targeting / inverse-vol:** `wᵢ ∝ 1/σᵢ`; portfolio leverage = `target_vol / realized_vol` (target ~10-12% annualized). **Risk parity** adds correlations; **equal-weight** ignores risk (simple, robust).

### Portfolio-level limits
Single-position **5-10%** (aggressive 10-15%); sector **20-30%** with **≥8 sectors**; **top-5 < 40%**;
max-drawdown circuit-breakers de-risk at **−10 to −15%**, halt new risk at **−20%**; cap aggregate
exposure to clusters with pairwise **correlation > 0.7**.

*Sources:* StockCharts/CFI/QuantifiedStrategies (Chandelier & ATR), Enlightened Stock Trading & JournalPlus (Kelly), InvestResolve (risk parity), Guardfolio & HDFC (concentration), Motley Fool & TIKR (sell disciplines), Wikipedia/VantagePoint (CAN SLIM), CFA Institute.

---

## 2. Thesis-break & sell discipline

Fisher's three reasons to sell: **wrong facts** (original analysis flawed), **changing facts**
(business deteriorated), **better opportunity** (capital scarcity). Concrete deterioration signals:

- **Revenue deceleration** — sustained slope (18→15→11→7%), *organic*; stagnation while peers grow = market-share loss.
- **Margin compression** — most alarming at the **gross-margin** line (business-model weakness, not just cost inflation).
- **Falling returns on capital** — ROCE/ROIC/ROE drifting toward the cost of capital (25%→12%). *The single most important moat-erosion signal.*
- **Cash-flow divergence** — net income rising while CFO stagnates; rising receivables/inventory; negative/declining FCF.
- **Rising leverage** — climbing net-debt/EBITDA, falling interest coverage. *The one that causes permanent capital loss.*
- **Management/capital-allocation flags** — guidance credibility loss, value-destructive M&A, dilution, dividend cuts, promoter pledging (India), auditor/CFO resignations.

**One signal = monitor; two = downgrade; three+ (or any solvency/governance signal) = exit-candidate.**

**Earnings season** is the natural re-underwriting cadence: beat/miss vs. estimates (quality of
beat matters more than headline), **guidance cuts**, and **downward analyst-revision breadth/velocity**
(downgrades are rarer and more predictive than upgrades). **Valuation-driven** action is a *trim*,
rarely a full exit — a great business at a stretched multiple (P/E in the top decile of its own
5-yr range) is reduced to target weight, not abandoned.

*Sources:* TIKR (deterioration/sell), Safal Niveshak (value-investing sell course), Motley Fool, Sigtrix & HeyGoTrade (revisions), FE Training (rebalancing).

---

## 3. Stock selection & entry (new-idea surfacing)

**Valuation bands** (always sector/history-relative): PEG **<1** attractive; EV/EBITDA **<8** cheap /
**>15** rich; P/E vs. own 5-yr median; FCF yield **4-8%** normal; P/B core for banks (judged vs. ROE).

**Quality gates:** **ROCE & ROE >15% (>20% excellent), consistent 5-yr**; stable/expanding margins;
**D/E <1 (<0.5 strong)**; interest coverage **>3**; OCF/PAT ≈1 (cash-backed earnings); revenue/EPS
CAGR **>10-15%**.

**Composite frameworks:**
- **Piotroski F-Score (0-9, ≥7-8 bullish):** 4 profitability (positive ROA, positive OCF, rising ROA, OCF>NI) + 3 leverage/liquidity (lower LT-debt ratio, higher current ratio, no dilution) + 2 efficiency (higher gross margin, higher asset turnover).
- **Greenblatt Magic Formula:** rank universe on **Earnings Yield (EBIT/EV)** + **Return on Capital (EBIT/capital employed)**; buy top combined-rank.
- **Morningstar/Buffett moat** — five sources: **intangibles, switching costs, network effect, cost advantage, efficient scale**; Wide (>20yr) / Narrow (~10yr) / None. Manifests as sustained high ROCE + margin stability.

**Technical entry (timing, not selection):** price **> 50-DMA & 200-DMA**, **golden cross**; breakout
on **volume ≥1.5× avg**; **RSI(14) 50-70** (veto buys >75 or >15% above 50-DMA — wait for a pullback).

*Sources:* Wikipedia (Piotroski, Magic Formula), GuruFocus (Greenblatt), Morningstar & VanEck (moat), Screener.in (screens), TradingSim/Strike (golden cross), Ventura/Piranha (valuation ratios).

---

## 4. Signal fusion & composite scoring

**The five academic factors:** Value (cheap), Momentum (**12-1**: cumulative return months t-12→t-2,
skip last month), Quality/Profitability (Novy-Marx gross profitability; MSCI = z-scores of ROE,
D/E, earnings variability), Size, Low-volatility/defensive.

**Combining incompatible metrics — the standard pipeline:**
1. **Winsorize** raw metrics (MSCI clips at **±3σ**).
2. **Normalize** — either **z-score** `(x−mean)/σ` (within-sector) or **percentile rank** (robust to outliers, loses magnitude).
3. **Aggregate within a factor** (average component z-scores).
4. **Aggregate across factors** — **equal-weight is the default** (factor timing is hard; equal-weight maximizes diversification).

**Fundamental + technical + sentiment fusion:** weighted sum of normalized sub-scores; **fundamentals
weighted highest for medium-term** horizons, technical/sentiment higher for short-term. Sentiment is
best used to **confirm/gate** other signals, not traded alone. Quantify sentiment via analyst-revision
breadth, news polarity (NLP/LLM −1..+1), and news volume.

**Score → action:** bucket the continuous composite into ratings via **threshold bands on the
cross-sectional distribution**; **confidence/uncertainty widens the bands** (Morningstar: higher
uncertainty ⇒ wider margin of safety before buy/sell triggers); add **hysteresis buffers** to prevent
churn. **Systematic core + discretionary override, both logged** is the consensus design.

*Sources:* AQR (factor/multi-factor, systematic-vs-discretionary), MSCI (quality & multi-factor methodology), Jegadeesh-Titman (momentum), Novy-Marx & AlphaArchitect (profitability), Morningstar (quant rating), arXiv/MDPI (sentiment fusion), Man/Acadian (conviction).

---

## 5. India-specific red flags & regulatory context

- **Promoter pledging:** rising pledge % of promoter holding is a distress signal (margin-call →
  invocation → price crash feedback loop). Caution **>25%**, high-risk **>50%**; watch **QoQ deltas**.
  Disclosed in the quarterly **Shareholding Pattern** (LODR Reg. 31); event disclosure within 7 working days.
- **Governance flags:** **auditor resignation** mid-term (strongest single flag, esp. citing "lack of
  audit evidence"); qualified/adverse opinions; frequent CFO/auditor churn; high/rising **related-party
  transactions**; declining promoter holding; large contingent liabilities; SEBI/ED/IT/GST actions;
  ASM/GSM surveillance; delayed filings.
- **Forensic scores:** **Beneish M-Score > −1.78** (earnings manipulation); **Altman Z < 1.81**
  (distress; 1.81-2.99 grey); cumulative **CFO/PAT < 0.7** (cash-vs-profit divergence); **DSO up >20% YoY**.
- **SEBI IA/RA:** a **personal, read-only, single-owner** alerting tool is **outside** registration —
  no clients, no consideration, no publication. Registration + prominent disclaimers become mandatory
  the moment outputs are shared, sold, or published. Label all outputs "personal informational use,
  not investment advice."
- **Results-season cadence** (FY ends 31 Mar): Q1 Jul-Aug, Q2 Oct-Nov, Q3 Jan-Feb, Q4+annual Apr-May;
  ≥2 working days' board-meeting notice; file within 45 days (60 annual). **Intensify monitoring to
  daily during these windows; event-driven alerts run continuously; weekly off-season.**

*Sources:* SEBI (shareholding disclosure, RA regs Dec-2024, RA guidelines Jan-2025), Vinod Kothari & TaxGuru (pledging), Moneylife, BFC Capital (promoter holding).

---

## 6. Data sources (access reality for an automated agent)

| Layer | Source | Reality |
|---|---|---|
| **Real-time events** | NSE/BSE announcements, shareholding pattern, insider trades, board meetings | Authoritative. NSE has anti-bot (session/cookie handling); BSE more scrape-friendly. |
| **Ratings actions** | CRISIL / ICRA / CARE pages | Downgrades = strong exit signals. |
| **Fundamentals** | Screener.in (free-ish, 10-yr data, rate-limited), Trendlyne (paid API, forensic scores, pledge alerts), Tijori (segment data, subscription) | Periodic pulls; respect rate limits; prefer paid API where compliance matters. |
| **Forensic confirmation** | MCA21 (charges/pledges, RPTs, director data) | Pay-per-document, no bulk API — on-demand deep-dive only. |
| **Portfolio + prices** | Zerodha Kite | Your holdings, P&L, candles (historical add-on). |

---

## 7. Consolidated rule catalog → agent mapping

The five sections produced ~70 rule candidates. Deduped and grouped by which **sub-score** they
feed and which **action** they can trigger. Full thresholds live in `config.yaml`; this is the
design source of truth. See `BUILD_PLAN.md §5` for the composite-scoring recipe that consumes them.

**Trigger philosophy:** `Technical/price → WATCH + risk alert` · `Fundamental/thesis/governance → TRIM/EXIT` · `Valuation-extreme → TRIM only` · `Solvency or governance → EXIT regardless of other scores`.

### Sub-score → raw inputs
- **Thesis** — `theses.yaml` `exit_if` checks; conviction rubric; count of active deterioration signals.
- **Fundamental** — ROCE/ROE level & trend, margin trend, revenue/EPS growth, interest coverage, D/E, OCF/PAT, FCF sign. (Novy-Marx/MSCI quality composite.)
- **Technical** — 12-1 momentum, price vs 50/200-DMA, RSI(14) regime, relative strength vs Nifty, volume.
- **Valuation** — sector-relative P/E, EV/EBITDA, P/B, FCF yield; percentile vs own 5-yr range.
- **News-risk** (inverted) — analyst-revision breadth, news sentiment polarity, event flags (results miss, guidance cut, SEBI action, rating downgrade).
- **Portfolio-fit** — position weight vs cap, sector concentration, top-5 concentration, correlation cluster, drawdown state.

### Hard override rules (fire regardless of composite)
- Interest coverage **< 1.5×**, or net-debt/EBITDA **> 4×** & rising → **EXIT-CANDIDATE**
- **Auditor resignation** (12 mo), qualified/adverse opinion, SEBI/ED/IT action, NCLT/IBC → **EXIT-CANDIDATE**
- Promoter pledge **> 50%** or any **invocation** → **EXIT-CANDIDATE**
- **Beneish M > −1.78** or **Altman Z < 1.81** → forensic flag, escalate
- Dividend cut by a consistent payer → **EXIT-CANDIDATE**
- Single position **> 15%** → hard TRIM alert; drawdown from peak **> 12%** → portfolio de-risk alert

### Anti-whipsaw guards
- Price drawdown with **no active fundamental signal** stays **HOLD**.
- **Hysteresis:** require the composite to cross ~3 pts *further* to change rating than to hold it.
- **Confidence factor** C∈[0.5,1] from data completeness + signal agreement; low C pulls the effective score toward 50 (neutral) → thin-evidence names stay Hold/Watch.

---

## 8. Key takeaways for the build
1. **Two-track triggering** (price→Watch, fundamentals→Exit) is the core safeguard logic and directly serves the user's goal.
2. **A confidence-decay state machine** (Core→Watch→Exit-Candidate, +1 signal at a time) is more robust than a single threshold.
3. **India governance/forensic layer** (pledging, auditor exits, Beneish/Altman, ratings) catches the disasters that lose the most money — prioritize these data feeds.
4. **Equal-weight composite + sector-relative normalization + hysteresis** is the defensible default; avoid over-tuning weights before Phase 5 backtesting.
5. **Personal single-user tool is SEBI-clear** — keep the disclaimer, never publish outputs.
