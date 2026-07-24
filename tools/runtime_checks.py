from __future__ import annotations

import os
from typing import Any


REQUIRED_API_KEYS = ("DEEPSEEK_API_KEY", "EXA_API_KEY")
PLACEHOLDER_PREFIXES = ("your_", "replace_", "example_", "changeme")


def validate_runtime(inputs: dict[str, Any]) -> dict[str, Any]:
    """Fail before paid model work when a required API key is missing.

    CrewAI loads ``.env`` before this callback. This function checks only that
    required values exist and are not obvious placeholders; providers still
    validate whether each secret is genuine.
    """

    invalid: list[str] = []
    for name in REQUIRED_API_KEYS:
        value = os.getenv(name, "").strip()
        if not value or value.lower().startswith(PLACEHOLDER_PREFIXES):
            invalid.append(name)

    if invalid:
        names = ", ".join(invalid)
        raise RuntimeError(
            f"Missing required API key(s): {names}. "
            "Add valid values to .env using .env.example as the template."
        )

    query = inputs.get("product_query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(
            "product_query must be a non-empty string. "
            "Pass it with crewai run --inputs."
        )

    return inputs
