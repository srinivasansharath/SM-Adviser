# App Store listing — SM Adviser (store name: StockMarket Adviser)

Paste-ready copy for App Store Connect → your app → **Distribution** (and **App Information**).
The app can't be edited via API on this team, so these are filled in the web UI by hand.

---

## App Information (General)

- **Name:** StockMarket Adviser
- **Subtitle** (max 30): `Daily portfolio intelligence`
- **Primary category:** Finance
- **Secondary category** (optional): Productivity
- **Content rights:** Does not contain, show, or access third-party content (the app itself
  only talks to the user's own server).

---

## Version 1.0 — Product Page

### Promotional Text (max 170)
```
Your self-hosted portfolio, reviewed every morning — clear Hold/Trim/Exit calls with the reasoning behind them, near-live prices, a home-screen widget, and shareable PDF reports.
```

### Description (max 4000)
```
StockMarket Adviser is a private, self-hosted portfolio companion for Indian-market (NSE) investors. You run your own SM Adviser server; this app is simply your window into it — your holdings, your data, your keys, entirely under your control.

Every morning your server reviews each holding against its original investment thesis and gives it a clear call — Hold, Watch, Accumulate, Trim, or Exit — backed by reasoning and evidence, so you can focus on what actually changed instead of daily noise.

WHAT YOU GET
• Home-screen widget — your whole portfolio at a glance, with today / 1-month / 1-year and since-purchase returns
• Near-live prices through the trading day
• Tap any holding for a full analysis one-pager — the six sub-scores, the composite band, the underlying technicals and fundamentals, and a plain-language note explaining exactly how the call was reached
• Share any stock analysis or the full daily report as a PDF
• Connects to YOUR server, Home-Assistant style — no accounts, no tracking, nothing collected by the app

REQUIRES A SELF-HOSTED SERVER
SM Adviser is the front end for the SM Adviser backend, which you host yourself and point at your own market-data and AI credentials. On first launch the app asks for your server's address and access token.

DISCLAIMER
SM Adviser is for personal, informational use only. It is not investment advice, a recommendation, or a solicitation to buy or sell any security. Always do your own research and consult a qualified, registered financial adviser before making investment decisions.
```

### Keywords (max 100, comma-separated, no spaces)
```
portfolio,stocks,shares,investing,widget,analysis,finance,markets,tracker,equity,holdings,NSE
```

### Support URL (required — needs a real web page)
Pick one and put it here:
- The backend repo (if you make it public): `https://github.com/srinivasansharath/SM-Adviser`
- Or a simple GitHub Pages / Notion page with setup + contact
(Apple rejects `mailto:` — it must be an https page.)

### Marketing URL (optional)
Same as support, or leave blank.

---

## App Privacy (nutrition label)
**Data Not Collected.** The app collects no data — it only communicates with the user's own
self-hosted server. Answer "No" to data collection; no tracking; no third-party SDKs.

---

## Age Rating (questionnaire → 4+)
Answer **None / No** to every category (no violence, no mature content, no gambling, no
unrestricted web). Result: **4+**.

---

## App Review Information (for Beta App Review + App Review)
- **Sign-in required:** No account, but the app needs a self-hosted server to show data.
- **Notes:**
```
This app is the front end for a self-hosted server (like the Home Assistant or Nextcloud client apps). Without a configured server it shows a "Connect to your server" setup screen — this is expected behaviour, not a bug. Beta testers run their own open-source SM Adviser backend and enter its address + token. [If a Demo mode is added: tap "Preview demo" on the setup screen to see the app populated with sample data.]
```
- **Contact:** your name, email, phone.

---

## TestFlight
- **Beta App Description:** (same as the App Store description, or a short version)
- **What to Test:**
```
Connect to your self-hosted SM Adviser server (URL + token), then: view your portfolio and the daily headline, switch the Today / 1M / 1Y column, tap a holding to read its analysis one-pager, add the home-screen widget, and try Share-as-PDF on a stock or the full report.
```
- **Feedback email:** your email.

---

## Screenshots (6.9" = 1320 × 2868, portrait)
At least 3, up to 10. Recommended set: (1) portfolio dashboard, (2) a stock analysis one-pager,
(3) the home-screen widget, (4) the connect-to-your-server setup screen. Provide full-resolution
captures; they get resized to 1320 × 2868 for upload.
