"""Model, Portkey, paths, and limits for the Campus Customs agent team.

- MODEL_NAME: gpt-6-luna for every agent (override with OPENAI_MODEL in .env)
- build_model(): one shared Portkey-routed OpenAI client
- Loads .env from Homework 5 and the class-folder root
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai.models.openai import OpenAIResponsesModel  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402
from pydantic_ai.usage import UsageLimits  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[1]  # Homework 5/
load_dotenv(PROJECT_DIR / ".env")
load_dotenv(PROJECT_DIR.parent / ".env")

DEFAULT_MODEL = "gpt-6-luna"
MODEL_NAME = (os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MCP_SERVER_SCRIPT = PROJECT_DIR / "mcp_server" / "server.py"
AUDIT_TRAIL_PATH = Path(os.getenv("AUDIT_TRAIL_PATH") or PROJECT_DIR / "output" / "audit_trail.json")
# The working copy the agents use (same default and override as the MCP server) and the
# untouched original that POST /reset copies back from.
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB") or PROJECT_DIR / "data" / "campus_customs_new.db")
ORIGINAL_DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_ORIGINAL_DB") or PROJECT_DIR / "data" / "campus_customs.db")

# Token and loop limits for one ticket run. Every agent in the run (Boss plus anyone it
# delegates to) shares the same usage counter, so these cap the whole ticket, not one agent.
TICKET_USAGE_LIMITS = UsageLimits(
    request_limit=40,          # model calls across all agents for one ticket
    tool_calls_limit=60,       # MCP + delegation tool calls across all agents
    total_tokens_limit=250_000,
)
MAX_OUTPUT_TOKENS = 16_000     # per model response; the model's hidden reasoning counts toward this, so 4,000 was too tight for the Boss's final plan
# Reasoning effort per agent (others use the model default). Customer Service only writes a
# short reply, but at the default effort it kept deliberating over its final report for
# 2-3 minutes (up to 16,000 hidden reasoning tokens). The no-internal-info check runs in code
# on every queued draft, so low effort is safe.
REASONING_EFFORT = {"Customer Service": "low"}
MAX_DELEGATION_DEPTH = 3       # Boss -> A -> B -> C, no deeper
MAX_DELEGATIONS_PER_TICKET = 10
AUDIT_TEXT_LIMIT = 1_500       # characters kept per text/tool result in the audit trail

_client: AsyncOpenAI | None = None


def require_api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Put it in a .env file in Homework 5 or the class folder.")
    return key


def build_model() -> OpenAIResponsesModel:
    """One shared Portkey-routed client for all five agents."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key="portkey",
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-api-key": require_api_key(), "x-portkey-provider": "openai"},
        )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=_client))
