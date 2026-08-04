"""Rewrite daily_stock_analysis imports to app.stock_agent package."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "app" / "stock_agent"

REPLACEMENTS = [
    (r"\bfrom src\.config\b", "from app.stock_agent.dsa_config"),
    (r"\bimport src\.config\b", "import app.stock_agent.dsa_config as src_config"),
    (r"\bfrom src\.storage\b", "from app.stock_agent.dsa_storage"),
    (r"\bimport src\.storage\b", "import app.stock_agent.dsa_storage as src_storage"),
    (r"\bfrom src\.agent\b", "from app.stock_agent.agent"),
    (r"\bimport src\.agent\b", "import app.stock_agent.agent"),
    (r"\bfrom src\.stock_analyzer\b", "from app.stock_agent.stock_analyzer"),
    (r"\bfrom src\.search_service\b", "from app.stock_agent.search_service"),
    (r"\bfrom src\.data\b", "from app.stock_agent.data"),
    (r"\bfrom src\.services\b", "from app.stock_agent.services"),
    (r"\bfrom data_provider\b", "from app.stock_agent.data_provider"),
    (r"\bimport data_provider\b", "import app.stock_agent.data_provider as data_provider"),
]


def rewrite_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, repl in REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    if text != original:
        path.write_text(text, encoding="utf-8")


def main() -> None:
    for py in PKG.rglob("*.py"):
        rewrite_file(py)
    print(f"Rewrote imports under {PKG}")


if __name__ == "__main__":
    main()
