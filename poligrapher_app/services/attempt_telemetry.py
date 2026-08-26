"""Durable, non-blocking signals for policy-attempt ML evaluation.

Telemetry collection must never decide whether an analysis runs. It records
cheap preflight metadata and capture-quality artifacts so candidate models can
be evaluated later behind the normal promotion gates.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from typing import Any

import httpx

TELEMETRY_SCHEMA_VERSION = "policy-attempt-telemetry-v1"
_CHALLENGE_STATUSES = frozenset({401, 403, 406, 429, 451})
_CHALLENGE_MARKERS = (
    "captcha",
    "cloudflare",
    "access denied",
    "bot detection",
    "verify you are human",
)


def probe_source_metadata(url: str, timeout: float = 5.0) -> dict[str, Any]:
    """Collect response headers without consuming the response body.

    Failures are returned as categorical metadata and never raised. The final
    URL itself is intentionally omitted so training data remains identity-free.
    """

    from poligrapher_app.services.acquisition import open_client, registrable_domain

    started = time.perf_counter()
    result: dict[str, Any] = {
        "attempted": True,
        "succeeded": False,
        "elapsed_ms": 0,
    }
    try:
        with open_client(timeout) as client:
            with client.stream("GET", url) as response:
                raw_content_length = response.headers.get("content-length")
                try:
                    content_length = int(raw_content_length) if raw_content_length else None
                except ValueError:
                    content_length = None
                original_domain = registrable_domain(url)
                final_domain = registrable_domain(str(response.url))
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                result.update({
                    "succeeded": True,
                    "http_status": response.status_code,
                    "content_type": content_type.casefold() or "unknown",
                    "content_length": content_length,
                    "redirect_count": len(response.history),
                    "cross_domain_redirect": bool(
                        original_domain and final_domain and original_domain != final_domain
                    ),
                    "challenge_detected": response.status_code in _CHALLENGE_STATUSES,
                })
    except (httpx.HTTPError, OSError, ValueError) as exc:
        result["error_type"] = type(exc).__name__
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def new_attempt_telemetry(
    *,
    probe: dict[str, Any] | None = None,
    analysis_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "analysis_path": analysis_path,
        "preflight": dict(probe or {"attempted": False}),
        "capture": {},
    }


def telemetry_for_policy(policy, *, probe_remote: bool = True) -> dict[str, Any]:
    existing = dict(policy.acquisition_telemetry or {})
    if existing.get("schema_version") == TELEMETRY_SCHEMA_VERSION:
        return existing
    parsed = urllib.parse.urlparse(policy.url or "")
    probe = (
        probe_source_metadata(policy.url)
        if probe_remote and parsed.scheme in {"http", "https"}
        else None
    )
    return new_attempt_telemetry(probe=probe, analysis_path=policy.method)


def _file_size(directory: str, name: str) -> int | None:
    try:
        return os.path.getsize(os.path.join(directory, name))
    except OSError:
        return None


def record_capture_snapshot(
    telemetry: dict[str, Any] | None,
    directory: str,
    *,
    elapsed_ms: float,
) -> None:
    """Record features available after capture but before graph construction."""

    if telemetry is None:
        return
    readability_length = None
    fallback_kind = "none"
    try:
        with open(os.path.join(directory, "readability.json"), encoding="utf-8") as stream:
            readability = json.load(stream)
        raw_length = readability.get("length")
        readability_length = int(raw_length) if raw_length is not None else None
        fallback_kind = str(readability.get("reason") or "none")
    except (OSError, ValueError, TypeError, AttributeError):
        pass

    capture = {
        "succeeded": True,
        "elapsed_ms": round(elapsed_ms, 3),
        "readability_text_chars": readability_length,
        "cleaned_html_bytes": _file_size(directory, "cleaned.html"),
        "accessibility_tree_bytes": _file_size(directory, "accessibility_tree.json"),
        "rendered_pdf_bytes": _file_size(directory, "output.pdf"),
        "fallback_kind": fallback_kind,
    }
    telemetry["capture"] = capture


def record_attempt_failure(
    telemetry: dict[str, Any] | None,
    exc: BaseException,
    *,
    stage: str,
) -> None:
    if telemetry is None:
        return
    message = str(exc).casefold()
    telemetry["failure"] = {
        "stage": stage,
        "error_type": type(exc).__name__,
        "challenge_detected": any(marker in message for marker in _CHALLENGE_MARKERS),
    }


def enriched_ml_features(telemetry: dict[str, Any]) -> dict[str, Any]:
    """Flatten only signals available before costly annotation/graph stages."""

    preflight = telemetry.get("preflight") or {}
    capture = telemetry.get("capture") or {}
    return {
        "telemetry_analysis_path": telemetry.get("analysis_path", "unknown"),
        "probe_succeeded": bool(preflight.get("succeeded")),
        "probe_http_status": str(preflight.get("http_status", "missing")),
        "probe_content_type": preflight.get("content_type", "missing"),
        "probe_content_length": preflight.get("content_length") or 0,
        "probe_content_length_known": preflight.get("content_length") is not None,
        "probe_redirect_count": preflight.get("redirect_count") or 0,
        "probe_cross_domain_redirect": bool(preflight.get("cross_domain_redirect")),
        "probe_challenge_detected": bool(preflight.get("challenge_detected")),
        "capture_succeeded": bool(capture.get("succeeded")),
        "capture_elapsed_ms": capture.get("elapsed_ms") or 0,
        "readability_text_chars": capture.get("readability_text_chars") or 0,
        "cleaned_html_bytes": capture.get("cleaned_html_bytes") or 0,
        "accessibility_tree_bytes": capture.get("accessibility_tree_bytes") or 0,
        "rendered_pdf_bytes": capture.get("rendered_pdf_bytes") or 0,
        "capture_fallback_kind": capture.get("fallback_kind", "missing"),
    }
