from pathlib import Path

import pytest

from flight_deals.config import ConfigError, load_api_key, load_config

REPO_CONFIG = Path(__file__).parent.parent / "config.toml"


def test_repo_config_loads():
    config = load_config(REPO_CONFIG)
    assert config.origins == ("LHR", "LGW", "STN", "LTN", "BHX", "MAN")
    assert config.currency == "GBP"
    assert config.db_path == REPO_CONFIG.parent / "data" / "flight_deals.db"


def test_invalid_origin_rejected(tmp_path):
    text = REPO_CONFIG.read_text(encoding="utf-8").replace('"LHR"', '"heathrow"')
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="origins"):
        load_config(path)


def test_negative_number_rejected(tmp_path):
    text = REPO_CONFIG.read_text(encoding="utf-8").replace("max_price = 40", "max_price = -1")
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="max_price"):
        load_config(path)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_api_key_environment_wins_over_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SERPAPI_API_KEY=from-file\n", encoding="utf-8")
    assert load_api_key(env_file, {"SERPAPI_API_KEY": "from-env"}) == "from-env"
    assert load_api_key(env_file, {}) == "from-file"


def test_api_key_quotes_and_comments_handled(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nSERPAPI_API_KEY="abc123"\n', encoding="utf-8")
    assert load_api_key(env_file, {}) == "abc123"


def test_missing_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SERPAPI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="SERPAPI_API_KEY"):
        load_api_key(env_file, {})
