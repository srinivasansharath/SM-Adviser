"""Export the database's theses back to theses.yaml.

    python -m app.reasoning.export_theses [path]

The DB is authoritative (the iOS app edits it). This keeps a human-readable, restorable copy on
disk — otherwise your written reasoning exists only inside Postgres.
"""

from __future__ import annotations

import sys

from ..storage.db import default_session_factory
from .theses import export_theses_to_yaml


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    n = export_theses_to_yaml(default_session_factory(), path)
    print(f"exported {n} theses to {path or 'theses.yaml'}")


if __name__ == "__main__":
    main()
