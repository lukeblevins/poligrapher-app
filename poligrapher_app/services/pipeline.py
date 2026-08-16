"""PoliGraph pipeline orchestration.

Runs the four-stage PoliGraph pipeline (crawl/parse → init → annotate → build
graph) for a captured policy. Pure business logic — no HTTP or view concerns.
"""

import json
import logging
import multiprocessing
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import uuid
from contextlib import contextmanager
from typing import Callable

from poligrapher_app.domain.policy_analysis import (
    DocumentCaptureSource,
    GraphKind,
    PolicyDocumentInfo,
)
from poligrapher_app.services.acquisition import (
    crawl_proxy_mode,
    fetch_validated_policy_html,
    fetch_wayback,
    httpx_proxy,
    open_client,
    wayback_snapshot_url,
)

logger = logging.getLogger(__name__)

_CRAWL_PROXY_ENV = (
    "CRAWL_PROXY",
    "CRAWL_PROXY_USERNAME",
    "CRAWL_PROXY_PASSWORD",
)
_CRAWL_ARTIFACTS = (
    "accessibility_tree.json",
    "cleaned.html",
    "readability.json",
    "output.pdf",
)


class PipelineCancelled(Exception):
    """Raised when a running pipeline observes a cancellation request."""


def _swap_into_place(staging_dir: str, output_folder: str) -> None:
    """Atomically replace ``output_folder`` with ``staging_dir``.

    Renames the existing output aside first, moves the freshly-built staging
    dir into place, then discards the backup. On failure the original is
    restored so the pipeline is all-or-nothing.
    """
    backup = output_folder + ".old"
    if os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)

    parent = os.path.dirname(output_folder) or "."
    os.makedirs(parent, exist_ok=True)

    existed = os.path.exists(output_folder)
    if existed:
        os.rename(output_folder, backup)
    try:
        os.rename(staging_dir, output_folder)
    except Exception:
        if existed and not os.path.exists(output_folder):
            os.rename(backup, output_folder)  # best-effort restore
        raise
    if existed:
        shutil.rmtree(backup, ignore_errors=True)


@contextmanager
def _argv(*args):
    # poligrapher's script main() functions (run_annotators, build_graph) use
    # argparse.parse_args() with no parameters, so they read sys.argv directly
    # rather than accepting programmatic arguments. We swap argv temporarily to
    # pass workdir/flags without forking a subprocess.
    old = sys.argv
    sys.argv = list(args)
    try:
        yield
    finally:
        sys.argv = old


@contextmanager
def _crawl_proxy_disabled():
    """Temporarily hide the crawler-specific proxy without affecting HTTP clients."""

    configured = {
        name: os.environ.pop(name)
        for name in _CRAWL_PROXY_ENV
        if name in os.environ
    }
    try:
        yield
    finally:
        os.environ.update(configured)


def _used_http_crawl_fallback(output_dir: str) -> bool:
    try:
        with open(os.path.join(output_dir, "readability.json"), encoding="utf-8") as stream:
            return json.load(stream).get("reason") == "http_fallback"
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
        return False


def _replace_crawl_artifacts(source_dir: str, output_dir: str) -> None:
    for name in _CRAWL_ARTIFACTS:
        source = os.path.join(source_dir, name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(output_dir, name))


def _crawl_html(
    html_crawler,
    path: str,
    output_dir: str,
    pdf_output: str | None = None,
) -> None:
    """Render directly first and use the configured proxy only as a fallback.

    PoliGraph's crawler reads ``CRAWL_PROXY`` directly and therefore otherwise
    routes every browser navigation through it, even when the application is
    configured for ``fallback`` mode. A valid static-HTML fallback remains
    usable, but a successful browser render is preferred because dynamic policy
    pages often expose only a shell to plain HTTP clients.
    """

    remote = urllib.parse.urlparse(path).scheme in ("http", "https")
    fallback_mode = crawl_proxy_mode() == "fallback" and bool(httpx_proxy())
    if not remote or not fallback_mode:
        html_crawler.main(path, output_dir, pdf_output=pdf_output)
        return

    try:
        with _crawl_proxy_disabled():
            html_crawler.main(path, output_dir, pdf_output=pdf_output)
    except Exception as direct_error:  # noqa: BLE001
        if not _should_retry_crawl_via_proxy(path, direct_error):
            raise
        logger.warning(
            "Direct browser navigation failed; retrying through the configured proxy"
        )
        html_crawler.main(path, output_dir, pdf_output=pdf_output)
        return
    if not _used_http_crawl_fallback(output_dir):
        return

    with tempfile.TemporaryDirectory(prefix="poligrapher-proxy-crawl-") as candidate:
        candidate_pdf = os.path.join(candidate, "output.pdf") if pdf_output else None
        try:
            html_crawler.main(path, candidate, pdf_output=candidate_pdf)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Proxy browser fallback failed; keeping validated direct HTML: %s",
                exc,
            )
            return
        if _used_http_crawl_fallback(candidate):
            logger.info("Proxy browser also used static HTML; keeping the direct capture")
            return
        logger.info("Proxy browser recovered a rendered policy page")
        _replace_crawl_artifacts(candidate, output_dir)


def _resolve_local_pdf_path(path: str | None) -> str | None:
    if not path:
        return None
    try:
        parsed = urllib.parse.urlparse(path)
        if parsed.scheme == "file":
            return parsed.path
        if parsed.scheme in ("http", "https"):
            return None
    except Exception:
        pass
    abs_path = os.path.abspath(path)
    return abs_path if os.path.isfile(abs_path) else None


def ensure_source_pdf_copy(source_path: str | None, output_dir: str) -> bool:
    """Copy a local source PDF into the provided output directory if missing."""

    source_path = _resolve_local_pdf_path(source_path)
    if not source_path:
        return False

    os.makedirs(output_dir, exist_ok=True)
    dest_path = os.path.join(output_dir, os.path.basename(source_path))
    if os.path.exists(dest_path):
        return True

    try:
        shutil.copy2(source_path, dest_path)
        logger.info("Copied original PDF %s to %s", source_path, dest_path)
        return True
    except Exception as exc:
        logger.warning("Failed to copy source PDF %s -> %s: %s", source_path, dest_path, exc)
        return False

def _url_probe_attempt(url: str, timeout: float, proxy: str | None) -> int:
    """Return one HTTP status; the caller supplies the killable boundary."""

    with open_client(timeout, proxy) as client:
        return client.get(url).status_code


def _url_probe_attempt_child(connection, url: str, timeout: float, proxy: str | None) -> None:
    try:
        connection.send(("ok", _url_probe_attempt(url, timeout, proxy)))
    except BaseException as exc:  # noqa: BLE001
        connection.send(("error", str(exc)))
    finally:
        connection.close()


def _run_url_probe_attempt(
    url: str,
    timeout: float,
    proxy: str | None,
    *,
    max_attempt_seconds: float | None = None,
) -> tuple[int | None, str | None]:
    """Run one reachability probe with a true wall-clock deadline."""

    deadline = max_attempt_seconds or timeout + 5.0
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_url_probe_attempt_child,
        args=(sender, url, timeout, proxy),
    )
    try:
        process.start()
        sender.close()
        process.join(deadline)
        if process.is_alive():
            process.terminate()
            process.join(5.0)
            if process.is_alive():
                process.kill()
                process.join()
            return None, f"reachability probe exceeded {deadline:g} seconds"
        if receiver.poll():
            category, value = receiver.recv()
            return (int(value), None) if category == "ok" else (None, str(value))
        return None, f"reachability probe exited with code {process.exitcode}"
    finally:
        receiver.close()
        if not sender.closed:
            sender.close()


def _url_reachable(
    url: str,
    timeout: float = 15.0,
    attempts: int = 2,
    *,
    allow_browser_challenge: bool = False,
) -> bool:
    """Reachability probe with a realistic browser identity and retries.

    Uses GET (many WAFs reject or stall bare HEAD requests) with the shared
    browser headers, retrying transient timeouts/5xx. A response below 400 (after
    redirect following) counts as reachable. Website callers may also accept a
    403/429 challenge as evidence that a bounded browser navigation is worth
    attempting.
    """
    configured_proxy = httpx_proxy()
    mode = crawl_proxy_mode()
    routes = [configured_proxy] if configured_proxy and mode == "always" else [None]
    if configured_proxy and mode == "fallback":
        routes.append(configured_proxy)
    for proxy in routes:
        for i in range(attempts):
            status, error = _run_url_probe_attempt(url, timeout, proxy)
            if status is not None:
                if status >= 500 and i < attempts - 1:
                    continue
                if status < 400 or (
                    allow_browser_challenge and status in {403, 429}
                ):
                    return True
                break
            if i < attempts - 1:
                continue
            logger.info("Error accessing URL %s: %s", url, error)
    return False


def test_document_url(url: str, *, allow_browser_challenge: bool = False) -> bool:
    """Return True if the URL is a reachable http(s) resource.

    Returns False silently for local paths / non-http schemes to avoid noisy
    errors when the input is an absolute file path.
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
    except Exception:
        return False
    return _url_reachable(
        url,
        allow_browser_challenge=allow_browser_challenge,
    )


def resolve_crawl_url(url: str) -> str:
    """Return a crawlable URL for a live source, with a Wayback fallback.

    If the live URL is reachable or returns a browser-challenge status, use it.
    Otherwise (timeout, DNS failure, or a missing resource) fall back to the
    closest Wayback Machine snapshot. A challenged browser crawl can still use
    the existing post-navigation archive fallback. Raises FileNotFoundError only
    when neither the live URL nor an archived copy is usable.
    """
    # A 403/429 response proves the public URL exists and commonly reflects an
    # HTTP-client challenge. Let the bounded browser crawler try it before
    # falling back to the archive. Binary document checks remain strict.
    if test_document_url(url, allow_browser_challenge=True):
        return url
    original_url = _wayback_original_url(url)
    if original_url:
        logger.warning(
            "Wayback snapshot unreachable, trying its original URL: %s", original_url
        )
        if test_document_url(original_url, allow_browser_challenge=True):
            return original_url
        # Look up another snapshot for the actual source, never for a replay URL.
        url = original_url
    logger.warning("Live URL unreachable, trying Wayback Machine: %s", url)
    # Trust the availability API rather than re-downloading the (often large,
    # slow) archived page just to verify it — that probe was timing out. The
    # crawler navigates it next with a generous timeout.
    snapshot = wayback_snapshot_url(url, raw=False)  # https replay URL for browser nav
    if snapshot:
        logger.info("Using Wayback snapshot for crawl: %s", snapshot)
        return snapshot
    raise FileNotFoundError(f"Document is not accessible or does not exist: {url}")


def _is_wayback_url(url: str) -> bool:
    try:
        hostname = (urllib.parse.urlparse(url).hostname or "").casefold()
    except Exception:
        return False
    return hostname == "web.archive.org" or hostname.endswith(".web.archive.org")


def _wayback_original_url(url: str) -> str | None:
    """Extract the original http(s) source embedded in a Wayback replay URL."""

    if not _is_wayback_url(url):
        return None
    try:
        parsed = urllib.parse.urlparse(url)
        match = re.match(r"^/web/[^/]+/(https?://.+)$", parsed.path, re.IGNORECASE)
        if not match:
            return None
        original = urllib.parse.unquote(match.group(1))
        if parsed.query:
            original = f"{original}?{parsed.query}"
        original_parsed = urllib.parse.urlparse(original)
        if original_parsed.scheme not in ("http", "https") or not original_parsed.netloc:
            return None
        if _is_wayback_url(original):
            return None
        return original
    except (TypeError, ValueError):
        return None


def _should_retry_crawl_from_archive(path: str, error: BaseException) -> bool:
    """Return whether a live website crawl hit the known navigation dead end.

    Keep this deliberately narrow: validation, extraction, cancellation, and
    arbitrary browser errors must retain their original failure semantics.
    """
    try:
        parsed = urllib.parse.urlparse(path)
    except Exception:
        return False
    detail = str(error).casefold()
    return (
        parsed.scheme in ("http", "https")
        and not _is_wayback_url(path)
        and "chromium navigation failed" in detail
        and "http source fallback was unavailable" in detail
    )


def _should_retry_crawl_via_proxy(path: str, error: BaseException) -> bool:
    """Retry only browser/network failures a different egress route may fix."""

    if _should_retry_crawl_from_archive(path, error):
        return True
    try:
        parsed = urllib.parse.urlparse(path)
    except Exception:
        return False
    detail = str(error).casefold()
    return (
        parsed.scheme in ("http", "https")
        and not _is_wayback_url(path)
        and (
            any(f"got http error {status}" in detail for status in (403, 429))
            or "content language unknown isn't english" in detail
        )
    )


def generate_graph_from_html(
    path: str,
    output_folder: str,
    capture_pdf: bool,
    should_cancel: Callable[[], bool] | None = None,
    emit_pdf: bool = False,
    _archive_fallback_attempted: bool = False,
) -> None:
    """Run the PoliGraph pipeline stages for a single input into output_folder.

    The pipeline writes into a private staging directory and is only swapped
    into ``output_folder`` after every stage completes, so a failure or a
    cancellation (via ``should_cancel``) leaves any existing output untouched.
    Cancellation is cooperative and checked between (coarse-grained) stages; a
    stage already executing runs to completion before the next check.
    """
    logger.info(
        "Starting PoliGraph pipeline (capture_pdf=%s) for %s -> %s",
        capture_pdf,
        path,
        output_folder,
    )
    # Normalize file:// URIs to filesystem paths.
    try:
        parsed = urllib.parse.urlparse(path)
        if parsed.scheme == "file":
            path = parsed.path
    except Exception:
        pass

    # Prefer a local file check first to avoid URL probes on file paths.
    if os.path.isfile(path):
        logger.info("Verified local file input: %s", path)
    elif capture_pdf:
        # PDF sources: keep the strict reachability check — swapping in a Wayback
        # snapshot of a binary PDF isn't handled by the PDF-copy step below.
        if not test_document_url(path):
            raise FileNotFoundError(f"Document is not accessible or does not exist: {path}")
        logger.info("Verified remote URL accessibility: %s", path)
    else:
        # Website crawl: fall back to an archived snapshot when the live site is
        # unreachable or bot-blocked, so a transient block doesn't fail the run.
        # A post-navigation retry already came from the Wayback availability
        # API. Do not reject that snapshot with the lightweight reachability
        # probe that archived pages are known to time out on.
        if not (_archive_fallback_attempted and _is_wayback_url(path)):
            path = resolve_crawl_url(path)
        logger.info("Resolved crawlable source: %s", path)

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    # Build into a staging dir seeded from any existing output so cached
    # intermediates (extracted PDF HTML, crawl) are still reused.
    staging = f"{output_folder}.staging-{uuid.uuid4().hex}"
    if os.path.isdir(output_folder):
        shutil.copytree(output_folder, staging)
    else:
        os.makedirs(staging, exist_ok=True)

    try:
        from poligrapher.scripts import (
            build_graph,
            html_crawler,
            init_document,
            pdf_parser,
            run_annotators,
        )

        steps: list[tuple[str, Callable[[], None]]] = []

        if capture_pdf:
            ensure_source_pdf_copy(path, staging)
            html_path = os.path.join(staging, "output.html")

            if not os.path.exists(html_path):
                steps.append(("Extracting PDF to HTML via pdf_parser", lambda: pdf_parser.main(path, staging)))
            else:
                logger.info("Cached PDF conversion detected (%s); skipping pdf_parser", html_path)

            steps.append(
                ("Crawling parsed HTML via html_crawler", lambda: html_crawler.main(html_path, staging))
            )
        else:
            # When emit_pdf is set, the crawl also prints the rendered page to
            # output.pdf so a PDF-parsing analysis can reuse this single fetch.
            pdf_output = os.path.join(staging, "output.pdf") if emit_pdf else None
            steps.append(
                ("Crawling source via html_crawler",
                 lambda: _crawl_html(html_crawler, path, staging, pdf_output=pdf_output))
            )

        def _run_annotators():
            with _argv("run_annotators", staging):
                run_annotators.main()

        def _build_graph_standard():
            with _argv("build_graph", staging):
                build_graph.main()

        def _build_graph_pretty():
            with _argv("build_graph", "--pretty", staging):
                build_graph.main()

        steps.extend(
            [
                ("Initializing document (init_document)", lambda: init_document.main(workdirs=[staging])),
                ("Running annotators", _run_annotators),
                ("Building standard graph", _build_graph_standard),
                ("Building pretty graph", _build_graph_pretty),
            ]
        )

        total_steps = len(steps)
        for idx, (message, step_fn) in enumerate(steps, 1):
            if _cancelled():
                raise PipelineCancelled(f"Cancelled before: {message}")
            logger.info("[%d/%d] %s", idx, total_steps, message)
            step_fn()

        if _cancelled():
            raise PipelineCancelled("Cancelled before finalizing output")

        _swap_into_place(staging, output_folder)
    except BaseException as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if (
            not capture_pdf
            and not _archive_fallback_attempted
            and _should_retry_crawl_from_archive(path, exc)
        ):
            direct_html = fetch_validated_policy_html(path)
            if direct_html:
                parent = os.path.dirname(output_folder) or None
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    prefix="poligrapher-direct-",
                    suffix=".html",
                    dir=parent,
                    delete=False,
                ) as direct_file:
                    direct_file.write(direct_html)
                    direct_path = direct_file.name
                logger.warning(
                    "Live Chromium crawl failed; retrying from validated direct HTML: %s",
                    path,
                )
                try:
                    return generate_graph_from_html(
                        direct_path,
                        output_folder,
                        capture_pdf=False,
                        should_cancel=should_cancel,
                        emit_pdf=emit_pdf,
                        _archive_fallback_attempted=True,
                    )
                finally:
                    try:
                        os.unlink(direct_path)
                    except FileNotFoundError:
                        pass
            archived_html = fetch_wayback(path)
            if archived_html:
                parent = os.path.dirname(output_folder) or None
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    prefix="poligrapher-wayback-",
                    suffix=".html",
                    dir=parent,
                    delete=False,
                ) as archived_file:
                    archived_file.write(archived_html)
                    archived_path = archived_file.name
                logger.warning(
                    "Live Chromium crawl failed; retrying once from materialized Wayback HTML: %s",
                    path,
                )
                try:
                    return generate_graph_from_html(
                        archived_path,
                        output_folder,
                        capture_pdf=False,
                        should_cancel=should_cancel,
                        emit_pdf=emit_pdf,
                        _archive_fallback_attempted=True,
                    )
                finally:
                    try:
                        os.unlink(archived_path)
                    except FileNotFoundError:
                        pass
            snapshot = wayback_snapshot_url(path, raw=False)
            if snapshot and snapshot != path:
                logger.warning(
                    "Live Chromium crawl failed; retrying once from Wayback: %s -> %s",
                    path,
                    snapshot,
                )
                return generate_graph_from_html(
                    snapshot,
                    output_folder,
                    capture_pdf=False,
                    should_cancel=should_cancel,
                    emit_pdf=emit_pdf,
                    _archive_fallback_attempted=True,
                )
        raise

    logger.info("Completed PoliGraph pipeline for %s", output_folder)


def generate_graph(
    policy: PolicyDocumentInfo,
    should_cancel: Callable[[], bool] | None = None,
) -> bool:
    """Run the full PoliGraph pipeline for a single policy document."""
    match policy.source:
        case DocumentCaptureSource.WEBPAGE:
            capture_pdf = False
        case DocumentCaptureSource.PDF:
            capture_pdf = True
        case _:
            raise ValueError(f"Unknown document source: {policy.source}")

    try:
        logger.info("Triggering pipeline for policy %s (source=%s)", policy.path, policy.source)
        generate_graph_from_html(policy.path, policy.output_dir, capture_pdf, should_cancel)
    except PipelineCancelled:
        logger.info("Pipeline cancelled for %s; output left unchanged", policy.output_dir)
        raise
    except SystemExit as exc:
        policy.record_error(f"Pipeline exited early: {exc}")
        raise RuntimeError("Graph generation pipeline exited") from exc
    except BaseException as exc:
        policy.record_error(f"Graph generation failed: {exc}")
        raise
    else:
        logger.info("Pipeline succeeded for %s", policy.output_dir)
        policy.clear_errors()
        return True


def generate_comparison(
    url: str,
    website_dir: str,
    pdf_dir: str,
    should_cancel: Callable[[], bool] | None = None,
) -> Exception | None:
    """Produce two graphs from a single website fetch, for method comparison.

    1. Website method: crawl the live URL, and print that same rendered page to
       ``website_dir/output.pdf``.
    2. PDF-from-page method: run the PDF-parsing path on that emitted PDF (no
       second fetch), yielding a comparable graph in ``pdf_dir``.

    Return the optional PDF method's error after a successful website graph so
    callers can persist that usable result. Website failures still raise.
    """
    logger.info("Comparison run for %s -> website=%s pdf=%s", url, website_dir, pdf_dir)
    generate_graph_from_html(url, website_dir, capture_pdf=False,
                             should_cancel=should_cancel, emit_pdf=True)

    shared_pdf = os.path.join(website_dir, "output.pdf")
    if not os.path.exists(shared_pdf):
        raise RuntimeError("Website crawl did not produce a PDF to compare against")

    try:
        generate_graph_from_html(
            shared_pdf, pdf_dir, capture_pdf=True, should_cancel=should_cancel
        )
    except PipelineCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "PDF-from-page comparison failed; preserving the website graph: %s",
            exc,
        )
        return exc
    return None


def infer_graph_kind(policy: PolicyDocumentInfo) -> GraphKind:
    """Infer the graph kind (STANDARD, LLM, NONE) from artifacts on disk."""
    standard_yml = os.path.join(policy.output_dir, "graph-original.yml")
    # TODO: update this when LLM graph generation is added.
    llm_yml = os.path.join(policy.output_dir, "graph-llm.yml")
    if os.path.exists(llm_yml):
        return GraphKind.LLM
    if os.path.exists(standard_yml):
        return GraphKind.STANDARD
    return GraphKind.NONE
