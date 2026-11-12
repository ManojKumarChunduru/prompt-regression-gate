"""Finds Playwright for Python and the Mermaid library wherever they are installed.

The evidence tools are dev-time only: neither Playwright nor Mermaid is a dependency of the
package, so they are resolved from the environment and the run fails with a sentence naming
what to install when they are missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def candidate_roots() -> list[Path]:
    roots = [Path.cwd() / "node_modules"]
    if os.environ.get("NODE_PATH"):
        roots += [Path(p) for p in os.environ["NODE_PATH"].split(":") if p]
    if shutil.which("npm"):
        try:
            out = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=True).stdout.strip()
            if out:
                roots.append(Path(out))
        except subprocess.CalledProcessError:
            pass
    roots += [Path("/opt/npm-tools/node_modules"), Path("/usr/lib/node_modules"), Path("/usr/local/lib/node_modules")]
    return [r for r in roots if r.exists()]


def find_mermaid() -> Path | None:
    for root in candidate_roots():
        path = root / "mermaid" / "dist" / "mermaid.min.js"
        if path.exists():
            return path
    return None


def playwright():
    """The sync Playwright API, or an error naming what to install."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:  # pragma: no cover
        raise SystemExit("playwright for Python was not found; pip install playwright && playwright install chromium") from error
    return sync_playwright
