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
        "stop_below": r.stop_below,
        "take_above": r.take_above,
    }


def load_theses_from_db(session_factory) -> dict:
    """Return {symbol: meta} from the theses table."""
    from ..storage.models import Thesis

    with session_factory() as s:
        return {t.symbol: _row_to_meta(t) for t in s.query(Thesis).all()}


EDITABLE_FIELDS = ("thesis", "bought_reason", "conviction", "target_weight_pct",
                   "exit_if", "stop_below", "take_above")


def upsert_thesis(session_factory, symbol: str, meta: dict):
    """Create/update one thesis; returns the persisted row.

    Only fields PRESENT in `meta` are written — absent keys are left alone. This matters because
    the iOS app posts the fields it knows about, and a replace-everything upsert would silently
    null out anything it doesn't (a stop loss, say) every time someone edited the thesis text.
    Pass an explicit value (None, or [] for exit_if) to clear a field.
    """
    from ..storage.models import Thesis

    with session_factory() as s:
        row = s.query(Thesis).filter_by(symbol=symbol).one_or_none()
        if row is None:
            row = Thesis(symbol=symbol)
            s.add(row)
        for field in EDITABLE_FIELDS:
            if field in meta:
                value = meta[field]
                if field == "exit_if":
                    value = value or []
                setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        s.commit()
        s.refresh(row)
        return row


def export_theses_to_yaml(session_factory, path: str | Path | None = None) -> int:
    """Write the DB's theses back out to theses.yaml. Returns the number exported.

    The DB became authoritative when the app gained a thesis editor, which left `theses.yaml`
    frozen at whatever seeded it — stale, and misleading to anyone who opens it. Worse, the only
    copy of the reasoning then lives in Postgres. This makes the file an honest export again: a
    human-readable, restorable record that seeds a rebuilt database via seed_theses_from_yaml().

    Writes atomically and keeps one .bak, because this file is gitignored and irreplaceable.
    """
    from ..storage.models import Thesis

    p = Path(path) if path else REPO_ROOT / "theses.yaml"
    with session_factory() as s:
        rows = s.query(Thesis).order_by(Thesis.symbol).all()
        data = {}
        for r in rows:
            entry = {
                "thesis": r.thesis or "",
                "conviction": r.conviction or "medium",
                "target_weight_pct": r.target_weight_pct,
                "bought_reason": r.bought_reason or "",
                "exit_if": list(r.exit_if or []),
            }
            # Only emit the price thresholds when set, so the file stays readable.
            if r.stop_below is not None:
                entry["stop_below"] = r.stop_below
            if r.take_above is not None:
                entry["take_above"] = r.take_above
            data[r.symbol] = entry

    header = (
        "# EXPORTED FROM THE DATABASE by app.reasoning.export_theses — do not hand-edit and expect\n"
        "# it to take effect. Theses are authoritative in the DB (edited from the iOS app); this\n"
        "# file is a readable backup, and the seed for a rebuilt database (seed_theses_from_yaml\n"
        "# only runs when the theses table is empty).\n"
        f"# Exported {datetime.now(timezone.utc).isoformat(timespec='seconds')} — {len(data)} theses.\n\n"
    )
    body = yaml.safe_dump(data, sort_keys=True, allow_unicode=True, width=100)

    if p.exists():
        p.with_suffix(p.suffix + ".bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(header + body, encoding="utf-8")
    tmp.replace(p)
    return len(data)


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
