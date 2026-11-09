"""Loading settings from config.toml and the API key from the environment / .env."""

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flight_deals.deals import DealRules
from flight_deals.models import Region, SearchSpec, TripLength

API_KEY_VAR = "SERPAPI_API_KEY"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    origins: tuple[str, ...]
    currency: str
    searches: tuple[SearchSpec, ...]
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
            searches=_load_searches(raw.get("searches", [])),
            rules=DealRules(
                min_zscore=_positive(deals, "min_zscore"),
                min_saving_pct=_positive(deals, "min_saving_pct"),
                min_history_days=_positive(deals, "min_history_days"),
                min_spread_pct=_positive(deals, "min_spread_pct"),
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
    if not isinstance(config.rules.min_history_days, int) or not isinstance(
        config.history_days, int
    ):
        raise ConfigError("min_history_days and history_days must be whole numbers")
    if config.rules.min_history_days > config.history_days:
        raise ConfigError("min_history_days can't be more than history_days")
    if config.rules.min_saving_pct >= 100:
        raise ConfigError("min_saving_pct must be below 100")
    return config


def _load_searches(raw: list[dict[str, Any]]) -> tuple[SearchSpec, ...]:
    if not raw:
        raise ConfigError("at least one [[searches]] block is required")

    specs = []
    for entry in raw:
        name = entry.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_-]+", name):
            raise ConfigError(f"search name must be lowercase letters, digits, _ or -: {name!r}")
        try:
            region = Region(entry["region"]) if "region" in entry else None
            trip_length = TripLength(entry.get("trip_length", TripLength.ONE_WEEK))
        except ValueError as e:
            raise ConfigError(f"search {name!r}: {e}") from None

        max_stops = entry.get("max_stops")
        if max_stops is not None and max_stops not in (0, 1, 2):
            raise ConfigError(f"search {name!r}: max_stops must be 0, 1 or 2")

        min_minutes = _hours_to_minutes(entry, "min_flight_hours", name)
        max_minutes = _hours_to_minutes(entry, "max_flight_hours", name)
        if min_minutes is not None and max_minutes is not None and min_minutes >= max_minutes:
            raise ConfigError(f"search {name!r}: min_flight_hours must be below max_flight_hours")

        max_price = None
        if "max_price" in entry:
            try:
                max_price = _positive(entry, "max_price")
            except ConfigError as e:
                raise ConfigError(f"search {name!r}: {e}") from None

        specs.append(
            SearchSpec(name, region, trip_length, max_stops, min_minutes, max_minutes, max_price)
        )

    names = [s.name for s in specs]
    if len(set(names)) != len(names):
        raise ConfigError("search names must be unique")
    return tuple(specs)


def _hours_to_minutes(entry: Mapping[str, Any], key: str, name: str) -> int | None:
    if key not in entry:
        return None
    try:
        hours = _positive(entry, key)
    except ConfigError as e:
        raise ConfigError(f"search {name!r}: {e}") from None
    return round(hours * 60)


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
