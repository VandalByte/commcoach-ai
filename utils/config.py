import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv


def load_config(config_path: str = "config.toml") -> dict:
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def load_env(env_path: str = ".env") -> None:
    load_dotenv(Path(env_path), override=False)


def get_configured_secret(config: dict, key: str, env_key: str) -> str:
    load_env()

    env_value = os.getenv(env_key, "").strip()
    if env_value:
        return env_value

    config_value = config.get(key, "").strip()
    if config_value:
        return config_value

    raise ValueError(
        f"Missing secret. Set {env_key} in your environment/.env or {key} in config.toml."
    )

