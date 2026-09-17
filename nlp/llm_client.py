"""
nlp/llm_client.py
------------------
Provider-agnostic LLM client. The rest of the application talks to
`get_llm_client()` and calls `.generate(prompt)` — it never imports
google.genai or any provider SDK directly. This makes it possible to
add a second provider (e.g. OpenRouter) later by adding a new class
here and switching LLM_PROVIDER in .env, with zero changes elsewhere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from config import settings
from utils.logging_config import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """Raised when the LLM fails to produce a usable response."""


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_instruction: str = "") -> str:
        """Return the raw text response from the model."""
        raise NotImplementedError


class GeminiClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not configured.")
        self._model_name = model
        try:
            from google import genai  # imported lazily so the whole app
            self._client = genai.Client(api_key=api_key)
        except ImportError as exc:
            raise LLMError(
                "google-genai package is not installed. "
                "Run: pip install google-genai"
            ) from exc

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system_instruction or None,
                temperature=0.0,
            )
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=config,
            )
            text = (response.text or "").strip()
            if not text:
                raise LLMError("The model returned an empty response.")
            return text
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            logger.error("Gemini generation failed: %s", exc)
            raise LLMError(f"LLM request failed: {exc}") from exc


class OpenRouterClient(BaseLLMClient):
    """
    Placeholder secondary provider. Implemented against OpenRouter's
    OpenAI-compatible chat completions endpoint so it can be dropped in
    without changing prompt_builder or sql_generator.
    """

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY is not configured.")
        self._api_key = api_key
        self._model = model

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        import requests

        try:
            resp = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("OpenRouter generation failed: %s", exc)
            raise LLMError(f"LLM request failed: {exc}") from exc


@lru_cache(maxsize=1)
def get_llm_client() -> BaseLLMClient:
    """Factory that returns the configured provider's client (singleton)."""
    provider = settings.llm.provider.lower()

    if provider == "gemini":
        return GeminiClient(
            api_key=settings.llm.gemini_api_key, model=settings.llm.gemini_model
        )
    if provider == "openrouter":
        return OpenRouterClient(
            api_key=settings.llm.openrouter_api_key,
            model=settings.llm.openrouter_model,
        )

    raise LLMError(f"Unsupported LLM_PROVIDER: {provider}")
