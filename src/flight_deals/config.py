"""Loading settings from config.toml and the API key from the environment / .env."""

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flight_deals.deals import DealRules

API_KEY_VAR = "SERPAPI_API_KEY"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    origins: tuple[str, ...]
    currency: str
    rules: DealRules
    history_days: int
    alert_cooldown_days: int
    monthly_search_limit: int
    db_path: Path


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML in {path}: {e}") from None

    try:
        search, deals, budget = raw["search"], raw["deals"], raw["budget"]
        origins = tuple(search["origins"])
        currency = search["currency"]
        config = Config(
            origins=origins,
            currency=currency,
            rules=DealRules(
                max_price=_positive(deals, "max_price"),
                min_drop_pct=_positive(deals, "min_drop_pct"),
                min_history=_positive(deals, "min_history"),
            ),
            history_days=_positive(deals, "history_days"),
            alert_cooldown_days=_positive(deals, "alert_cooldown_days"),
            monthly_search_limit=_positive(budget, "monthly_search_limit"),
            db_path=path.parent / raw.get("storage", {}).get("db_path", "data/flight_deals.db"),
        )
    except KeyError as e:
        raise ConfigError(f"missing setting in {path}: {e}") from None

    if not origins or not all(isinstance(o, str) and re.fullmatch(r"[A-Z]{3}", o) for o in origins):
        raise ConfigError("search.origins must be a non-empty list of 3-letter IATA codes")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ConfigError("search.currency must be a 3-letter currency code, e.g. GBP")
    return config


def _positive(section: Mapping[str, Any], key: str) -> Any:
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ConfigError(f"{key} must be a positive number, got {value!r}")
    return value


def load_api_key(env_file: Path, environ: Mapping[str, str] = os.environ) -> str:
    """Read the API key from the environment, falling back to a .env file."""
    key = environ.get(API_KEY_VAR, "").strip()
    if not key and env_file.exists():
        key = _read_env_file(env_file).get(API_KEY_VAR, "")
    if not key:
        raise ConfigError(f"{API_KEY_VAR} is not set (add it to {env_file} or the environment)")
    return key


def _read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values
