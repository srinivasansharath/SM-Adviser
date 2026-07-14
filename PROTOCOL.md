# SM Adviser API — Protocol & Compatibility

The iOS app and the server are deployed independently (the app updates slowly through the App
Store; each person self-hosts a server they update on their own schedule). This document is the
**contract** between them, so they can evolve without breaking each other.

Machine-readable spec: **[`docs/openapi.json`](docs/openapi.json)** (auto-generated from FastAPI).

## Versioning

- **`api_version`** — an integer, the contract version. It appears in `/meta` and in every
  `widget.json`. It is bumped **only on a breaking change**.
- **`server_version`** — informational SemVer of the backend build (in `/meta`).
- Current: **`api_version = 2`**. (The unversioned payloads served to the 1.x app are
  retroactively "version 1"; v2 is the first explicitly-versioned contract.)

## Compatibility rules

**Within a major `api_version`, only additive changes are allowed:**
- ✅ Add a new optional field, a new endpoint, or a new `feature`.
- ❌ Never remove, rename, or repurpose an existing field. Never make an optional field required.

**Clients (the app) must:**
- **Ignore unknown fields** (Swift `Codable` does this by default).
- **Tolerate missing fields** (treat every data field as optional).
- **Negotiate via `/meta`** — gate features on what the server advertises; don't assume.

**A breaking change** (rare) bumps `api_version` and is served alongside the old version for a
deprecation window (e.g. path-versioned `/v3/...`), so old apps keep working until they update.

## Capability negotiation — `GET /meta`

Open (no auth), like `/health`. The app calls it on connect to adapt gracefully.
```json
{
  "api_version": 2,
  "server_version": "2.0.0",
  "features": ["widget", "stock_analysis", "full_report", "intraday"],
  "min_app_build": 1
}
```
- `features` — advertise a capability only when the server can serve it. The app hides UI for
  features a server doesn't list (e.g. an older server without `stock_analysis` → no tap-through).
- `min_app_build` — the oldest app build this server supports; the app warns if it is older.
- The app should also warn "update your server" if the server's `api_version` is **older** than
  the app needs.

## Endpoints (v2)

| Method | Path | Auth | Returns | Feature |
|---|---|---|---|---|
| GET | `/health` | open | `{"status":"ok"}` | — |
| GET | `/meta` | open | capability/version JSON | — |
| GET | `/widget.json` | bearer | portfolio snapshot (see below) | `widget` |
| GET | `/stock/{symbol}` | bearer | analysis one-pager (HTML) | `stock_analysis` |
| GET | `/report/latest` | bearer | full daily report (HTML) | `full_report` |
| GET | `/theses` | bearer | list of per-stock theses (JSON) | `thesis_editing` |
| PUT | `/theses/{symbol}` | bearer | upsert one thesis; returns it (JSON) | `thesis_editing` |

Auth is a bearer token: `Authorization: Bearer <WIDGET_API_TOKEN>` (per user/instance).

**HTML endpoints are inherently forward-compatible** — the app renders whatever HTML the server
returns, so `/stock` and `/report` can change freely without a contract bump. The only *structured*
contract is **`widget.json`** (+ `/meta`).

### `widget.json` shape (the structured contract)
Full schema in `docs/openapi.json` (`WidgetPayload`). Key fields:
- Top level: `api_version`, `as_of`, `prices_as_of?`, `headline?`, `portfolio`, `holdings[]`, `disclaimer`.
- `portfolio`: `value`, `day_change_pct?`, `total_pnl?`, `total_return_pct?`, `attention_count?`.
- each holding: `symbol`, `name?`, `ltp?`, `change_pct?` (today), `ret_20d?` (1M), `ret_252d?` (1Y),
  `return_pct?` (since buy), `pnl?`, `classification?`, `confidence?`, `thesis_status?`, `flag?`.
- All numeric fields may be `null`; the server never emits `NaN`/`Inf`.

### Theses (app-editable, `thesis_editing` feature)
The investment thesis per holding lives in the DB and is edited from the app. A thesis is
`{symbol, thesis?, bought_reason?, conviction? (high|medium|low), target_weight_pct?, exit_if?: string[], updated_at?}`.
- `GET /theses` → array of theses.
- `PUT /theses/{symbol}` → body is the thesis (without `symbol`); creates or updates it. The next
  morning run scores against the updated thesis.
Servers seed the table once from `theses.yaml`, then it's DB-owned.

## For server implementers
Anyone can implement a compatible server — the app is an open client (Home-Assistant style). Serve
the endpoints above, satisfy the `widget.json` schema, and advertise your `features` in `/meta`.
The contract is enforced in CI by a schema test against `WidgetPayload`.
