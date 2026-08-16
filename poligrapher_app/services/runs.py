"""Provider analysis runs: streamlined website↔PDF comparison + one-off uploads.

A *comparison run* fetches a provider's website source once and produces two
graphs — the website-HTML method and a PDF-generated-from-that-page method —
grouped by ``run_group`` so they can be compared. A one-off *upload run* analyses
a user-provided PDF and is never scheduled; it is only re-analysed when the file
changes. Both flow through the TaskRegistry so they appear in the Status Center.
"""

from __future__ import annotations

import hashlib
import logging
import multiprocessing
import os
import tempfile
import urllib.parse
import uuid
import zipfile
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def _download_pdf_attempt(url: str, path: str, max_bytes: int, proxy: str | None) -> None:
    """Perform one PDF transfer. The caller provides the killable boundary."""

    from poligrapher_app.services.acquisition import open_client

    with open_client(45.0, proxy) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            size = 0
            with open(path, "wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Remote policy PDF exceeds the 50 MB limit")
                    output.write(chunk)
    with open(path, "rb") as output:
        if output.read(4) != b"%PDF":
            raise ValueError("Remote policy source did not return a PDF")


def _download_pdf_attempt_child(connection, url, path, max_bytes, proxy) -> None:
    try:
        _download_pdf_attempt(url, path, max_bytes, proxy)
        connection.send(("ok", ""))
    except BaseException as exc:  # noqa: BLE001
        message = str(exc)
        if isinstance(exc, TimeoutError) or "timed out" in message.casefold():
            category = "timeout"
        elif isinstance(exc, ValueError):
            category = "value"
        else:
            category = "runtime"
        connection.send((category, message))
    finally:
        connection.close()


def _run_pdf_download_attempt(
    url: str,
    path: str,
    max_bytes: int,
    proxy: str | None,
    max_attempt_seconds: float,
) -> None:
    """Run one transfer in a process that can be terminated on a hard deadline."""

    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_download_pdf_attempt_child,
        args=(sender, url, path, max_bytes, proxy),
    )
    process.start()
    sender.close()
    process.join(max_attempt_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5.0)
        if process.is_alive():
            process.kill()
            process.join()
        receiver.close()
        raise TimeoutError("Remote policy PDF download timed out at its attempt deadline")

    result = receiver.recv() if receiver.poll() else None
    receiver.close()
    if result is None:
        raise RuntimeError(
            f"Remote policy PDF download process exited with code {process.exitcode}"
        )
    category, message = result
    if category == "ok":
        return
    if category == "timeout":
        raise TimeoutError(message)
    if category == "value":
        raise ValueError(message)
    raise RuntimeError(message)


def _download_remote_pdf(
    url: str,
    destination,
    max_bytes: int = 50 * 1024 * 1024,
    max_attempt_seconds: float = 60.0,
) -> None:
    """Download a policy PDF with the same retry and proxy routes as acquisition."""

    from poligrapher_app.services.acquisition import crawl_proxy_mode, httpx_proxy

    configured_proxy = httpx_proxy()
    mode = crawl_proxy_mode()
    routes = [configured_proxy] if configured_proxy and mode == "always" else [None]
    if configured_proxy and mode == "fallback":
        routes.append(configured_proxy)

    last_error: Exception | None = None
    direct_error: Exception | None = None
    for proxy in routes:
        for attempt in range(2):
            destination.seek(0)
            destination.truncate()
            try:
                temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
                with tempfile.TemporaryDirectory(
                    prefix="poligrapher-pdf-attempt-", dir=temp_root
                ) as attempt_dir:
                    attempt_path = str(Path(attempt_dir) / "policy.pdf")
                    _run_pdf_download_attempt(
                        url,
                        attempt_path,
                        max_bytes,
                        proxy,
                        max_attempt_seconds,
                    )
                    with open(attempt_path, "rb") as downloaded:
                        for chunk in iter(lambda: downloaded.read(1024 * 1024), b""):
                            destination.write(chunk)
                destination.flush()
                destination.seek(0)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if proxy is None:
                    direct_error = exc
                logger.warning(
                    "Remote PDF download failed for %s (route=%s, attempt=%d): %s",
                    url,
                    "proxy" if proxy else "direct",
                    attempt + 1,
                    exc,
                )
    failure = direct_error or last_error
    assert failure is not None
    if "timed out" in str(failure).casefold():
        raise TimeoutError(
            "Remote policy PDF download timed out after all configured attempts"
        ) from failure
    raise failure


def file_hash(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _score(policy, db, doc=None) -> None:
    from poligrapher_app.api.mapping import policy_doc_from_db, sync_policy_from_doc
    from poligrapher_app.services.scoring import score_gdpr, score_privacy

    doc = doc or policy_doc_from_db(policy)
    score_privacy(doc)
    score_gdpr(doc)
    sync_policy_from_doc(policy, doc, db, commit=False)


def _website_text_hash(policy, db, doc=None) -> str | None:
    from poligrapher_app.api.mapping import policy_doc_from_db
    from poligrapher_app.services.acquisition import content_hash

    try:
        return content_hash((doc or policy_doc_from_db(policy)).get_document_text())
    except Exception:  # noqa: BLE001
        return None


def _mark_failed(policies, db, message: str) -> None:
    """Terminate a run's policies as failed so the UI stops polling 'pending'.

    Reassigns pipeline_errors (rather than mutating in place) so SQLAlchemy
    tracks the change on the plain JSON column.
    """
    for p in policies:
        if not p.graph_data:
            p.pipeline_status = "failed"
        p.pipeline_errors = list(p.pipeline_errors or []) + [message]
    db.commit()


def _persist_generated_method(
    policy,
    doc,
    archive_path: Path,
    db,
    *,
    record_content_hash: bool = False,
) -> Exception | None:
    """Persist one comparison method without discarding its sibling result."""

    from poligrapher_app.services.persistence import persist_workspace

    try:
        _score(policy, db, doc)
        persist_workspace(policy, doc, archive_path)
        if record_content_hash:
            policy.content_hash = _website_text_hash(policy, db, doc)
        db.commit()
        return None
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _mark_failed([policy], db, f"{policy.method} failed: {exc}")
        logger.warning(
            "Comparison method %s failed while preserving sibling results: %s",
            policy.method,
            exc,
        )
        return exc


def _comparison_source_url(provider) -> str | None:
    """Choose the live source when a stored archive only reflects a web challenge."""

    canonical_url = provider.source_url
    verified_fallback = provider.source_final_url or ""
    if provider.source_status != "available":
        return canonical_url
    if verified_fallback.startswith("https://r.jina.ai/"):
        return verified_fallback
    if verified_fallback.startswith("https://web.archive.org/") and (
        not canonical_url or provider.source_http_status not in {403, 429}
    ):
        return verified_fallback
    return canonical_url


def run_comparison(
    provider_id, *, scheduled: bool, registry=None, task_id=None, link_task: bool = True
) -> str:
    """Fetch the provider's website source once and build both method graphs.

    Returns a short status string ('ok', 'unchanged', 'needs_source', 'cancelled').
    """
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy, Provider
    from poligrapher_app.services.acquisition import PolicySourceResolver
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_comparison
    from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo

    should_cancel = (lambda: registry.is_cancelled(task_id)) if (task_id and registry) else None
    db = SessionLocal()
    try:
        provider = db.get(Provider, provider_id)
        if not provider:
            return "needs_source"

        url = _comparison_source_url(provider)
        if not url:
            # Fall back to discovery so a run can proceed without a set source.
            cand = PolicySourceResolver().resolve_candidate(provider.name, provider.domain)
            url = cand.url if cand else None
            if url and not provider.source_url:
                provider.source_url = url
                db.commit()
        if not url:
            return "needs_source"

        # Change detection: skip scheduled runs when the policy text is unchanged.
        if scheduled:
            resolved = PolicySourceResolver().resolve(provider.name, provider.domain, url)
            if resolved is None:
                return "needs_source"
            last = (
                db.query(Policy)
                .filter_by(provider_id=provider.id, method="website")
                .filter(Policy.content_hash.isnot(None))
                .order_by(Policy.created_at.desc())
                .first()
            )
            if last and last.content_hash == resolved.content_hash:
                logger.info("Provider %s policy unchanged; skipping run", provider.name)
                return "unchanged"

        day = date.today()
        grp = uuid.uuid4()
        website = Policy(provider_id=provider.id, url=url, source="webpage", method="website",
                         run_group=grp, scheduled=scheduled, capture_date=day)
        pdf = Policy(provider_id=provider.id, url=url, source="pdf", method="pdf_from_page",
                     run_group=grp, scheduled=scheduled, capture_date=day)
        db.add_all([website, pdf])
        db.commit()
        db.refresh(website)
        db.refresh(pdf)
        if registry and task_id and link_task:
            registry.update(task_id, run_id=str(grp))

        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.TemporaryDirectory(prefix="poligrapher-", dir=temp_root) as workspace:
            web_dir = Path(workspace) / "website"
            pdf_dir = Path(workspace) / "pdf"
            try:
                pdf_generation_error = generate_comparison(
                    url, str(web_dir), str(pdf_dir), should_cancel
                )
                web_doc = PolicyDocumentInfo(url, str(web_dir), DocumentCaptureSource.WEBPAGE,
                                             day, False)
                pdf_doc = PolicyDocumentInfo(str(web_dir / "output.pdf"), str(pdf_dir),
                                             DocumentCaptureSource.PDF, day, False)
                failures = []
                website_error = _persist_generated_method(
                    website,
                    web_doc,
                    Path(workspace) / "website.zip",
                    db,
                    record_content_hash=True,
                )
                if website_error is not None:
                    failures.append(website_error)
                if pdf_generation_error is None:
                    pdf_error = _persist_generated_method(
                        pdf,
                        pdf_doc,
                        Path(workspace) / "pdf.zip",
                        db,
                    )
                    if pdf_error is not None:
                        failures.append(pdf_error)
                else:
                    _mark_failed(
                        [pdf],
                        db,
                        f"pdf_from_page failed: {pdf_generation_error}",
                    )
                    failures.append(pdf_generation_error)
                if len(failures) < 2:
                    return "ok"
                raise RuntimeError(
                    "Both comparison methods failed: "
                    + "; ".join(str(error) for error in failures)
                )
            except PipelineCancelled:
                db.rollback()
                _mark_failed([website, pdf], db, "Run cancelled")
                return "cancelled"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _mark_failed([website, pdf], db, f"Comparison failed: {exc}")
                raise
    finally:
        db.close()


def run_upload(policy_id, *, registry=None, task_id=None) -> str:
    """Analyse a one-off uploaded PDF (never scheduled)."""
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph
    from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo
    from poligrapher_app.services.persistence import persist_workspace
    from poligrapher_app.services.storage import get_storage

    should_cancel = (lambda: registry.is_cancelled(task_id)) if (task_id and registry) else None
    db = SessionLocal()
    try:
        policy = db.get(Policy, policy_id)
        if not policy:
            return "gone"
        if not policy.source_blob_key:
            _mark_failed([policy], db, "Uploaded source is missing from object storage")
            return "gone"
        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.TemporaryDirectory(prefix="poligrapher-", dir=temp_root) as workspace:
            source = Path(workspace) / (policy.source_filename or "source.pdf")
            output = Path(workspace) / "output"
            get_storage().download_file(policy.source_blob_key, source)
            doc = PolicyDocumentInfo(str(source), str(output), DocumentCaptureSource.PDF,
                                     policy.capture_date or date.today(), policy.has_results,
                                     policy.pipeline_errors)
            try:
                generate_graph(doc, should_cancel=should_cancel)
                _score(policy, db, doc)
                persist_workspace(policy, doc, Path(workspace) / "artifacts.zip")
                policy.content_hash = file_hash(str(source))
                db.commit()
                return "ok"
            except PipelineCancelled:
                db.rollback()
                _mark_failed([policy], db, "Run cancelled")
                return "cancelled"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _mark_failed([policy], db, f"Upload analysis failed: {exc}")
                raise
    finally:
        db.close()


def run_remote_pdf(
    provider_id, *, scheduled: bool, registry=None, task_id=None
) -> str:
    """Download an official policy PDF, store it durably, and analyze it."""
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy, Provider
    from poligrapher_app.services.storage import get_storage, source_key

    with SessionLocal() as db:
        provider = db.get(Provider, provider_id)
        if not provider or not provider.source_url:
            return "needs_source"
        url = provider.source_url
        filename = Path(urllib.parse.urlparse(url).path).name or "privacy-policy.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.NamedTemporaryFile(
            prefix="poligrapher-remote-", suffix=".pdf", dir=temp_root
        ) as download:
            _download_remote_pdf(url, download)
            digest = file_hash(download.name)
            existing = (
                db.query(Policy)
                .filter_by(provider_id=provider.id, method="pdf_upload", content_hash=digest)
                .order_by(Policy.created_at.desc())
                .first()
            )
            if existing and existing.has_results:
                return "unchanged"
            policy = Policy(
                provider_id=provider.id,
                url=filename,
                source="pdf",
                method="pdf_upload",
                scheduled=scheduled,
                capture_date=date.today(),
                source_filename=filename,
                content_hash=digest,
            )
            db.add(policy)
            db.commit()
            db.refresh(policy)
            policy.source_blob_key = source_key(policy.id, filename)
            get_storage().upload_file(
                policy.source_blob_key, download.name, content_type="application/pdf"
            )
            db.commit()
            policy_id = policy.id
    return run_upload(policy_id, registry=registry, task_id=task_id)


def run_archived_comparison(
    original_policy_id, website_policy_id, pdf_policy_id, *, registry=None, task_id=None
) -> str:
    """Build a new comparison from a previously archived website capture."""
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy
    from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo
    from poligrapher_app.services.persistence import persist_workspace
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph_from_html
    from poligrapher_app.services.storage import get_storage

    should_cancel = (lambda: registry.is_cancelled(task_id)) if (task_id and registry) else None
    with SessionLocal() as db:
        original = db.get(Policy, original_policy_id)
        website = db.get(Policy, website_policy_id)
        pdf = db.get(Policy, pdf_policy_id)
        if not original or not website or not pdf or not original.artifact_blob_key:
            if website or pdf:
                _mark_failed([policy for policy in (website, pdf) if policy], db, "Saved source is unavailable")
            return "gone"

        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.TemporaryDirectory(prefix="poligrapher-rerun-", dir=temp_root) as workspace:
            root = Path(workspace)
            archive_path = root / "source.zip"
            try:
                get_storage().download_file(original.artifact_blob_key, archive_path)
                with zipfile.ZipFile(archive_path) as archive:
                    members = {
                        Path(member.filename).name: member
                        for member in archive.infolist()
                        if not member.is_dir()
                    }
                    html_member = members.get("output.html") or members.get("cleaned.html")
                    pdf_member = members.get("output.pdf")
                    if not html_member or not pdf_member:
                        _mark_failed([website, pdf], db, "Saved website copy is incomplete")
                        return "gone"
                    html_path = root / Path(html_member.filename).name
                    pdf_path = root / "output.pdf"
                    html_path.write_bytes(archive.read(html_member))
                    pdf_path.write_bytes(archive.read(pdf_member))

                web_dir = root / "website"
                pdf_dir = root / "pdf"
                generate_graph_from_html(
                    str(html_path), str(web_dir), capture_pdf=False, should_cancel=should_cancel
                )
                generate_graph_from_html(
                    str(pdf_path), str(pdf_dir), capture_pdf=True, should_cancel=should_cancel
                )
                web_doc = PolicyDocumentInfo(
                    str(html_path), str(web_dir), DocumentCaptureSource.WEBPAGE,
                    website.capture_date or date.today(), False,
                )
                pdf_doc = PolicyDocumentInfo(
                    str(pdf_path), str(pdf_dir), DocumentCaptureSource.PDF,
                    pdf.capture_date or date.today(), False,
                )
                _score(website, db, web_doc)
                _score(pdf, db, pdf_doc)
                persist_workspace(website, web_doc, root / "website.zip")
                persist_workspace(pdf, pdf_doc, root / "pdf.zip")
                website.content_hash = _website_text_hash(website, db, web_doc)
                db.commit()
                return "ok"
            except PipelineCancelled:
                db.rollback()
                _mark_failed([website, pdf], db, "Run cancelled")
                return "cancelled"
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _mark_failed([website, pdf], db, f"Archived comparison failed: {exc}")
                raise
