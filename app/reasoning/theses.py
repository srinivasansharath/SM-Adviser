"""Load theses.yaml — the per-stock investment thesis + exit conditions."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..config import REPO_ROOT


def load_theses(path: str | Path | None = None) -> dict:
    """Return {symbol: {thesis, conviction, target_weight_pct, bought_reason, exit_if[]}}."""
    p = Path(path) if path else REPO_ROOT / "theses.yaml"
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
