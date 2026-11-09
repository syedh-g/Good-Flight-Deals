import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from flight_deals.app import BudgetExceeded, run
from flight_deals.config import ConfigError, load_api_key, load_config
from flight_deals.notify import ConsoleNotifier
from flight_deals.sources.serpapi import SerpApiSource
from flight_deals.store import Store

log = logging.getLogger("flight_deals")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find cheap flights and report new deals.")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    # Destination names include non-ASCII characters; Windows consoles default to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
        api_key = load_api_key(args.env_file)
    except ConfigError as e:
        log.error("%s", e)
        return 2

    source = SerpApiSource(api_key, config.currency)
    with Store.open(config.db_path) as store:
        try:
            result = run(config, source, store, ConsoleNotifier(sys.stdout), datetime.now(UTC))
        except BudgetExceeded as e:
            log.error("%s", e)
            return 1

    if not result.deals:
        print("No new deals today.")
    if result.failed_searches:
        log.error("failed searches: %s", ", ".join(result.failed_searches))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
