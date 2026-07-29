"""Stable failure codes and recovery guidance for task and pipeline errors."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FailureDefinition:
    code: str
    stage: str
    retryability: str
    summary: str
    actions: tuple[dict[str, str], ...]

    def public(self, technical_detail: str) -> dict:
        value = asdict(self)
        value["actions"] = list(self.actions)
        value["technical_detail"] = technical_detail
        return value


RETRY = {"action": "retry", "label": "Retry failed companies"}
USE_ARCHIVE = {"action": "use_archive", "label": "Try an archived policy"}
REPLACE_SOURCE = {"action": "replace_source", "label": "Choose another policy source"}
UPLOAD_PDF = {"action": "upload_pdf", "label": "Upload an official policy PDF"}
REVIEW_CONTENT = {"action": "review_content", "label": "Review the extracted policy"}
TRY_OTHER_METHOD = {"action": "try_other_method", "label": "Try the alternate analysis method"}
MODEL_REVIEW = {"action": "model_review", "label": "Review model compatibility"}
REPORT = {"action": "report_diagnostic", "label": "Review diagnostic details"}


def classify_failure(error: BaseException | str) -> dict:
    detail = str(error).strip() or error.__class__.__name__
    text = detail.casefold()

    if "exceeded" in text and ("second" in text or "timeout" in text):
        definition = FailureDefinition(
            "execution.timeout", "execution", "transient",
            "Analysis exceeded its time limit.", (RETRY, REPORT),
        )
    elif "chromium navigation failed" in text or "err_timed_out" in text:
        definition = FailureDefinition(
            "crawl.navigation_failed", "acquisition", "transient",
            "The policy page could not be loaded.", (RETRY, USE_ARCHIVE, REPLACE_SOURCE),
        )
    elif "document is not accessible" in text or "file not found" in text:
        definition = FailureDefinition(
            "source.inaccessible", "acquisition", "manual",
            "The configured policy document is unavailable.", (USE_ARCHIVE, REPLACE_SOURCE, UPLOAD_PDF),
        )
    elif "not like a privacy policy" in text:
        definition = FailureDefinition(
            "source.not_policy", "validation", "manual",
            "The retrieved page does not appear to be a privacy policy.", (REPLACE_SOURCE, UPLOAD_PDF),
        )
    elif "isn't english" in text or "not a usable english" in text:
        definition = FailureDefinition(
            "source.unsupported_language", "validation", "manual",
            "The retrieved policy is not usable English content.", (REPLACE_SOURCE, UPLOAD_PDF),
        )
    elif "no canonical graph elements" in text:
        definition = FailureDefinition(
            "graph.empty", "graph", "manual",
            "The pipeline did not produce a usable knowledge graph.", (REVIEW_CONTENT, TRY_OTHER_METHOD, MODEL_REVIEW),
        )
    elif "did not return a pdf" in text:
        definition = FailureDefinition(
            "pdf.invalid_source", "pdf", "manual",
            "The configured PDF source did not return a PDF.", (REPLACE_SOURCE, UPLOAD_PDF),
        )
    elif "pdf exceeds" in text:
        definition = FailureDefinition(
            "pdf.too_large", "pdf", "manual",
            "The policy PDF exceeds the supported size limit.", (REPLACE_SOURCE, UPLOAD_PDF),
        )
    elif "source is missing from object storage" in text or "saved source" in text:
        definition = FailureDefinition(
            "storage.source_missing", "storage", "manual",
            "The saved source artifact is unavailable.", (REPLACE_SOURCE, UPLOAD_PDF, REPORT),
        )
    elif "needs_source" in text or "could not resolve a policy source" in text:
        definition = FailureDefinition(
            "source.missing", "acquisition", "manual",
            "No usable privacy-policy source is configured.", (REPLACE_SOURCE, UPLOAD_PDF),
        )
    elif "model" in text and any(marker in text for marker in ("incompatible", "trained with", "state_dict")):
        definition = FailureDefinition(
            "model.incompatible", "model", "blocked",
            "The NLP model is not compatible with the current runtime.", (MODEL_REVIEW, REPORT),
        )
    elif "subprocess exited" in text:
        definition = FailureDefinition(
            "execution.subprocess_failed", "execution", "manual",
            "The isolated analysis process exited unexpectedly.", (REPORT,),
        )
    elif "could not enqueue" in text or "queue" in text:
        definition = FailureDefinition(
            "execution.queue_failed", "execution", "transient",
            "The analysis could not be queued.", (RETRY, REPORT),
        )
    else:
        definition = FailureDefinition(
            "execution.unclassified", "execution", "manual",
            "The analysis encountered an unclassified error.", (REPORT,),
        )
    return definition.public(detail)
