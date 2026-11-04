"""Portkey settings for HW6, the `Lecture 3 In Class/app_config.py` pattern.

The only place the model name and the Portkey credentials are read. Everything else
imports `load_settings()` rather than touching the environment, because the two can
disagree before `load_dotenv` has run.

`hw6/` sits one level below the course workspace root, and the shared `.env` that holds
`PORTKEY_API_KEY` lives there. Rather than climbing a fixed number of levels, the loader
walks every ancestor, nearest first. `load_dotenv` does not override values that are
already set, so the nearest `.env` wins.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

#: The only model this project may ever bill. Christine's instruction for HW6
#: (2026-11-03): "we will use gpt-6-luna for this project. Any other model used
#: will cost me points."
#:
#: `OPENAI_MODEL` is still read, but a value naming anything else is **ignored**
#: rather than honoured. The semester default elsewhere in this workspace is
#: `gpt-5.6-luna`, so a stray `OPENAI_MODEL` in the shared workspace `.env` is one
#: `export` away from quietly billing the wrong model here, and nothing in the code
#: would say so. The ignored value is reported on `Settings.model_override_ignored`
#: so the substitution is visible instead of silent.
#:
#: This is also the model `data/prices.json` prices, so cost figures and the model
#: actually billed cannot drift apart.
REQUIRED_OPENAI_MODEL = "gpt-6-luna"
DEFAULT_OPENAI_MODEL = REQUIRED_OPENAI_MODEL


@dataclass(frozen=True)
class Settings:
    portkey_api_key: str
    model_name: str
    portkey_base_url: str
    portkey_provider: str | None
    portkey_config_id: str | None
    model_override_ignored: str | None = None


def _load_dotenv_files() -> None:
    """Load this folder's .env, then each ancestor's. Nearest wins."""
    for directory in (PROJECT_DIR, *PROJECT_DIR.parents):
        load_dotenv(directory / ".env")


def load_settings(model_override: str | None = None) -> Settings:
    _load_dotenv_files()
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PORTKEY_API_KEY is missing. Add it to the workspace .env or this project's .env."
        )

    requested = (model_override or os.getenv("OPENAI_MODEL") or "").strip()
    ignored = requested if requested and requested != REQUIRED_OPENAI_MODEL else None

    return Settings(
        portkey_api_key=api_key,
        model_name=REQUIRED_OPENAI_MODEL,
        portkey_base_url=os.getenv("PORTKEY_BASE_URL", DEFAULT_PORTKEY_BASE_URL),
        portkey_provider=os.getenv("PORTKEY_PROVIDER"),
        portkey_config_id=os.getenv("PORTKEY_CONFIG_ID"),
        model_override_ignored=ignored,
    )


def build_portkey_client(settings: Settings) -> AsyncOpenAI:
    headers = {"x-portkey-api-key": settings.portkey_api_key}
    if settings.portkey_provider:
        headers["x-portkey-provider"] = settings.portkey_provider
    if settings.portkey_config_id:
        headers["x-portkey-config"] = settings.portkey_config_id

    return AsyncOpenAI(
        api_key=settings.portkey_api_key,
        base_url=settings.portkey_base_url,
        default_headers=headers,
    )
