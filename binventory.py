#!/usr/bin/env python3
"""BinInventory CLI — Terminal interface for BinInventory."""

import sys

try:
    import questionary  # noqa: F401
    from rich.console import Console  # noqa: F401
    import requests  # noqa: F401
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run:  pip install -r requirements.txt")
    sys.exit(1)

import config
import api as api_module
from views import main_menu, login_view


def main() -> None:
    cfg = config.load()
    client = api_module.BinInventoryAPI(
        base_url=cfg.get("base_url", config.DEFAULT_URL),
        token=cfg.get("token"),
    )

    if not cfg.get("token"):
        cfg = login_view(cfg, client)
        if not cfg.get("token"):
            sys.exit(0)

    try:
        main_menu(cfg, client)
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
