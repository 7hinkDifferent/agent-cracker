from __future__ import annotations

"""Fallback + retry + repair demo core for Hermes."""

import json
from dataclasses import dataclass, field


@dataclass
class ProviderAttempt:
    name: str
    scripted_response: str | None = None
    fail: bool = False


@dataclass
class CredentialPool:
    provider_keys: dict[str, list[str]]
    rotations: dict[str, int] = field(default_factory=dict)

    def next_key(self, provider: str) -> str:
        keys = self.provider_keys[provider]
        index = self.rotations.get(provider, 0) % len(keys)
        self.rotations[provider] = index + 1
        return keys[index]


class RecoveryEngine:
    def repair_tool_name(self, name: str, valid_names: set[str]) -> str | None:
        lowered = name.replace("-", "_")
        if lowered in valid_names:
            return lowered
        return None

    def repair_json_args(self, payload: str) -> dict:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            repaired = payload.replace("'", '"').replace(",}", "}")
            return json.loads(repaired)

    def call_with_fallback(self, attempts: list[ProviderAttempt], pool: CredentialPool) -> str:
        errors: list[str] = []
        for attempt in attempts:
            key = pool.next_key(attempt.name)
            if attempt.fail:
                errors.append(f"{attempt.name} failed with key {key}")
                continue
            return f"provider={attempt.name} key={key} response={attempt.scripted_response}"
        raise RuntimeError(" | ".join(errors))
