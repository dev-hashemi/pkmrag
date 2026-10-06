"""Rate limiting and backoff for LLM inference providers."""

from __future__ import annotations

import random
import re
import threading
import time
from collections import deque
from typing import Callable, Optional

import httpx


def estimate_tokens(text: str) -> int:
    """Fast conservative token estimation (~3.8 chars per token + safety margin)."""
    return max(1, int(len(text) / 3.8) + 10)


def parse_retry_after(response: httpx.Response) -> Optional[float]:
    """Extract retry-after delay in seconds from response headers or error body."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass

    header_ms = response.headers.get("retry-after-ms")
    if header_ms:
        try:
            return float(header_ms) / 1000.0
        except ValueError:
            pass

    try:
        data = response.json()
        msg = str(data.get("error", {}).get("message", ""))
        match = re.search(r"try again in ([\d\.]+)s", msg)
        if match:
            return float(match.group(1))
    except Exception:
        pass

    return None


class RateLimiter:
    """Thread-safe dual sliding-window rate limiter enforcing RPM and TPM."""

    def __init__(
        self,
        rpm: int = 30,
        tpm: int = 8000,
        max_retries: int = 3,
    ) -> None:
        self.rpm = rpm
        self.tpm = tpm
        self.max_retries = max_retries
        self._requests: deque[float] = deque()
        self._tokens: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def acquire(
        self,
        estimated_tokens: int = 500,
        on_wait: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Wait until within RPM and TPM quotas, then reserve permits."""
        if self.rpm <= 0 and self.tpm <= 0:
            return

        while True:
            with self._lock:
                now = time.monotonic()
                # Purge entries older than 60 seconds
                while self._requests and now - self._requests[0] >= 60.0:
                    self._requests.popleft()
                while self._tokens and now - self._tokens[0][0] >= 60.0:
                    self._tokens.popleft()

                wait_rpm = 0.0
                if self.rpm > 0 and len(self._requests) >= self.rpm:
                    wait_rpm = max(0.0, 60.0 - (now - self._requests[0]) + 0.05)

                wait_tpm = 0.0
                current_tokens = sum(t[1] for t in self._tokens)
                if self.tpm > 0 and current_tokens + estimated_tokens > self.tpm:
                    needed = (current_tokens + estimated_tokens) - self.tpm
                    freed = 0
                    oldest = now
                    for t_time, t_val in self._tokens:
                        freed += t_val
                        if freed >= needed:
                            oldest = t_time
                            break
                    wait_tpm = max(0.0, 60.0 - (now - oldest) + 0.05)

                wait_time = max(wait_rpm, wait_tpm)
                if wait_time <= 0.0:
                    rec_time = time.monotonic()
                    if self.rpm > 0:
                        self._requests.append(rec_time)
                    if self.tpm > 0:
                        self._tokens.append((rec_time, estimated_tokens))
                    return

                reason = (
                    f"RPM limit ({len(self._requests)}/{self.rpm})"
                    if wait_rpm >= wait_tpm
                    else f"TPM limit ({current_tokens + estimated_tokens}/{self.tpm})"
                )

            if on_wait:
                on_wait(wait_time, reason)
            time.sleep(wait_time)

    def wait_for_retry(
        self,
        attempt: int,
        retry_after: Optional[float] = None,
        on_wait: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """Handle 429 backoff using Retry-After header or exponential backoff."""
        if retry_after is not None and retry_after > 0:
            delay = retry_after + 0.2
            reason = f"Retry-After ({delay:.1f}s)"
        else:
            delay = min(60.0, (2.0**attempt) + random.uniform(0.1, 0.5))
            reason = f"HTTP 429 backoff attempt {attempt + 1} ({delay:.1f}s)"

        if on_wait:
            on_wait(delay, reason)
        time.sleep(delay)
