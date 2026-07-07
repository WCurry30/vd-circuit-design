import time
from typing import Optional


class TokenTracker:
    def __init__(self):
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    def wrap_client(self, client) -> None:
        original_create = client.chat.completions.create

        def tracked_create(*args, **kwargs):
            response = original_create(*args, **kwargs)
            try:
                usage = response.usage
                if usage:
                    self._total_prompt_tokens += usage.prompt_tokens or 0
                    self._total_completion_tokens += usage.completion_tokens or 0
            except (AttributeError, TypeError):
                pass
            return response

        client.chat.completions.create = tracked_create

    def snapshot(self) -> dict:
        return {
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
            "timestamp": time.time(),
        }

    def delta_since(self, snap: dict) -> int:
        current = self._total_prompt_tokens + self._total_completion_tokens
        previous = snap.get("total_tokens", 0)
        return max(0, current - previous)

    @property
    def total_tokens(self) -> int:
        return self._total_prompt_tokens + self._total_completion_tokens

    def reset(self) -> None:
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
