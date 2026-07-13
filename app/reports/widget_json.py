"""widget.json — the payload the iOS WidgetKit app (Phase 7) reads over Tailscale.

Kept small and forward-compatible: Phase 4 will add `classification`/`confidence`/`thesis_status`
per holding. For now each holding carries price, day change, and the preliminary risk flag.
"""

from __future__ import annotations

import json
from pathlib import Path

_DISCLAIMER = "Personal informational use, not investment advice."


def build_widget(data: dict, as_of: str | None = None, narrative: dict | None = None) -> dict:
    p = data["portfolio"]
    notes = (narrative or {}).get("holdings") or {}
    holdings = []
    for r in data["holdings"]:
        note = notes.get(r["symbol"]) if isinstance(notes.get(r["symbol"]), dict) else {}
        holdings.append(
            {
                "symbol": r["symbol"],
                "name": r["name"],
                "ltp": r["ltp"],
                # Period returns the widget's middle column cycles through: today / 1M / 1Y.
                "change_pct": round(r["day_change_pct"], 2) if r["day_change_pct"] is not None else None,
                "ret_20d": r["ret_20d"],      # ~1 month
                "ret_252d": r["ret_252d"],    # ~1 year
                "return_pct": r["return_pct"],  # since-purchase return %
                "pnl": round(r["pnl"], 0) if r.get("pnl") is not None else None,  # since-purchase ₹ gain
                "rel_strength": r["rel_strength"],
                "classification": r.get("classification"),
                "confidence": r.get("confidence"),
                "thesis_status": note.get("thesis_status"),
                "flag": r["flag"],
                "flag_reason": (r.get("rec_reason") or (r["reasons"][0] if r["reasons"] else None)),
            }
        )
    return {
        "as_of": as_of or data["run_date"],
        "headline": (narrative or {}).get("executive") or None,
        "portfolio": {
            "value": p["value"],
            "day_change_pct": p["day_change_pct"],
            "total_pnl": p["total_pnl"],
            "total_return_pct": p.get("total_return_pct"),
            "attention_count": p["attention_count"],
        },
        "holdings": holdings,
        "disclaimer": _DISCLAIMER,
    }


def write_widget(data: dict, output_dir: Path, as_of: str | None = None, narrative: dict | None = None) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "widget.json"  # stable name; the widget always reads the latest
    path.write_text(json.dumps(build_widget(data, as_of, narrative), indent=2), encoding="utf-8")
    return path
