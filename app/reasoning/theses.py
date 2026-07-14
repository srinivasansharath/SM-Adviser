"""Per-stock investment thesis + exit conditions.

Theses live in the database (editable from the app). `theses.yaml` remains a one-time seed and
an import/export convenience. The rest of the pipeline consumes the same
`{symbol: {thesis, conviction, target_weight_pct, bought_reason, exit_if[]}}` dict either way.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..config import REPO_ROOT


def load_theses(path: str | Path | None = None) -> dict:
    """Load from theses.yaml (the seed/fallback source)."""
    p = Path(path) if path else REPO_ROOT / "theses.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _row_to_meta(r) -> dict:
    return {
        "thesis": r.thesis,
        "bought_reason": r.bought_reason,
        "conviction": r.conviction,
        "target_weight_pct": r.target_weight_pct,
        "exit_if": r.exit_if or [],
    }


def load_theses_from_db(session_factory) -> dict:
    """Return {symbol: meta} from the theses table."""
    from ..storage.models import Thesis

    with session_factory() as s:
        return {t.symbol: _row_to_meta(t) for t in s.query(Thesis).all()}


def upsert_thesis(session_factory, symbol: str, meta: dict):
    """Create/update one thesis; returns the persisted row."""
    from ..storage.models import Thesis

    with session_factory() as s:
        row = s.query(Thesis).filter_by(symbol=symbol).one_or_none()
        if row is None:
            row = Thesis(symbol=symbol)
            s.add(row)
        row.thesis = meta.get("thesis")
        row.bought_reason = meta.get("bought_reason")
        row.conviction = meta.get("conviction")
        row.target_weight_pct = meta.get("target_weight_pct")
        row.exit_if = meta.get("exit_if") or []
        row.updated_at = datetime.now(timezone.utc)
        s.commit()
        s.refresh(row)
        return row


def seed_theses_from_yaml(session_factory, path: str | Path | None = None) -> int:
    """One-time migration: if the theses table is empty, populate it from theses.yaml.
    Returns the number of rows seeded (0 if the table already has data)."""
    from ..storage.models import Thesis

    with session_factory() as s:
        if s.query(Thesis).first() is not None:
            return 0
        y = load_theses(path)
        n = 0
        for sym, meta in (y or {}).items():
            s.add(Thesis(
                symbol=sym, thesis=(meta or {}).get("thesis"),
                bought_reason=(meta or {}).get("bought_reason"),
                conviction=(meta or {}).get("conviction"),
                target_weight_pct=(meta or {}).get("target_weight_pct"),
                exit_if=(meta or {}).get("exit_if") or [],
                updated_at=datetime.now(timezone.utc),
            ))
            n += 1
        s.commit()
        return n
