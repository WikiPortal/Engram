"""
Engram — LLM Provider Abstraction

Single interface for all LLM calls. Swap providers by setting two env vars:

  LLM_PROVIDER=gemini   + GEMINI_API_KEY    (default)
  LLM_PROVIDER=openai   + OPENAI_API_KEY    (GPT-4o, GPT-4o-mini, etc.)
  LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY (Claude 3.5 Sonnet, etc.)
  LLM_PROVIDER=deepseek + DEEPSEEK_API_KEY  (deepseek-chat, deepseek-reasoner)

Default models per provider (override with LLM_MODEL in .env):
  gemini    → gemini-3-flash-preview
  openai    → gpt-4o-mini
  anthropic → claude-3-5-haiku-20241022
  deepseek  → deepseek-chat

"""

import os
from functools import lru_cache
from config import get_settings

settings = get_settings()


# ── Provider detection ────────────────────────────────────────────

def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").lower().strip()

def get_model() -> str:
    override = os.getenv("LLM_MODEL", "").strip()
    if override:
        return override
    defaults = {
        "gemini":    "gemini-3-flash-preview",
        "openai":    "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "deepseek":  "deepseek-chat",
    }
    return defaults.get(get_provider(), "gemini-3-flash-preview")


# ── Gemini ────────────────────────────────────────────────────────

def _gemini_complete(system: str, user: str) -> str:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY", getattr(settings, "gemini_api_key", ""))
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=get_model(),
        system_instruction=system,
    )
    response = model.generate_content(user)
    return response.text.strip()


def _gemini_chat(system: str, history: list[dict], message: str) -> str:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY", getattr(settings, "gemini_api_key", ""))
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=get_model(),
        system_instruction=system,
    )
    gemini_history = [
        {"role": m["role"], "parts": [m["content"]]}
        for m in history
    ]
    session = model.start_chat(history=gemini_history)
    response = session.send_message(message)
    return response.text.strip()


# ── OpenAI ────────────────────────────────────────────────────────

def _openai_complete(system: str, user: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


def _openai_chat(system: str, history: list[dict], message: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [{"role": "system", "content": system}]
    for m in history:
        # Normalize role: Gemini uses "model", OpenAI uses "assistant"
        role = "assistant" if m["role"] == "model" else m["role"]
        messages.append({"role": role, "content": m["content"]})
    messages.append({"role": "user", "content": message})
    resp = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


# ── Anthropic (Claude) ────────────────────────────────────────────

def _anthropic_complete(system: str, user: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=get_model(),
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip()


def _anthropic_chat(system: str, history: list[dict], message: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages = []
    for m in history:
        role = "assistant" if m["role"] == "model" else m["role"]
        messages.append({"role": role, "content": m["content"]})
    messages.append({"role": "user", "content": message})
    resp = client.messages.create(
        model=get_model(),
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return resp.content[0].text.strip()


# ── DeepSeek (OpenAI-compatible API) ─────────────────────────────

def _deepseek_complete(system: str, user: str) -> str:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    resp = client.chat.completions.create(
        model=get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


def _deepseek_chat(system: str, history: list[dict], message: str) -> str:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    messages = [{"role": "system", "content": system}]
    for m in history:
        role = "assistant" if m["role"] == "model" else m["role"]
        messages.append({"role": role, "content": m["content"]})
    messages.append({"role": "user", "content": message})
    resp = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


# ── Public interface ──────────────────────────────────────────────

_COMPLETE = {
    "gemini":    _gemini_complete,
    "openai":    _openai_complete,
    "anthropic": _anthropic_complete,
    "deepseek":  _deepseek_complete,
}

_CHAT = {
    "gemini":    _gemini_chat,
    "openai":    _openai_chat,
    "anthropic": _anthropic_chat,
    "deepseek":  _deepseek_chat,
}


def complete(system: str, user: str) -> str:
    """
    Single-turn LLM call. Used by extractor, HyDE, graph classifier.
    Raises on error — callers handle gracefully.
    """
    provider = get_provider()
    fn = _COMPLETE.get(provider)
    if not fn:
        raise ValueError(f"Unknown LLM provider: '{provider}'. "
                         f"Set LLM_PROVIDER to one of: gemini, openai, anthropic, deepseek")
    return fn(system, user)


def chat_complete(system: str, history: list[dict], message: str) -> str:
    """
    Multi-turn chat. Used by brain.chat().
    history: list of {"role": "user"|"assistant"|"model", "content": "..."}
    """
    provider = get_provider()
    fn = _CHAT.get(provider)
    if not fn:
        raise ValueError(f"Unknown LLM provider: '{provider}'.")
    return fn(system, history, message)


def provider_info() -> dict:
    """Returns current provider and model — used by /health endpoint."""
    return {"provider": get_provider(), "model": get_model()}
