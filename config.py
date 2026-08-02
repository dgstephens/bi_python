import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".binventory"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_URL = "https://bin-inventory-backend-a5156630dc89.herokuapp.com/api"


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"base_url": DEFAULT_URL}


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def clear_auth(cfg: dict) -> dict:
    for key in ("token", "userId", "email"):
        cfg.pop(key, None)
    save(cfg)
    return cfg
