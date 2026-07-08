"""PoliGraph pipeline orchestration.

Runs the four-stage PoliGraph pipeline (crawl/parse → init → annotate → build
graph) for a captured policy. Pure business logic — no HTTP or view concerns.
"""

import ipaddress
import logging
import os
import shutil
import sys
import urllib.parse
import uuid
from contextlib import contextmanager
from typing import Callable

import httpx

from poligrapher_app.domain.policy_analysis import (
    DocumentCaptureSource,
    GraphKind,
    PolicyDocumentInfo,
)

logger = logging.getLogger(__name__)


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


def is_ip_address(s: str) -> bool:
    try:
        return bool(ipaddress.ip_address(s))
    except ValueError:
        return False


def validate_url(url: str) -> dict:
    """Validate URL format and accessibility."""
    if not url or not url.strip():
        return {"valid": False, "message": "No URL provided"}

    url = url.strip()

    try:
        result = urllib.parse.urlparse(url)
        if not all([result.scheme, result.netloc]):
            return {"valid": False, "message": "Invalid URL format"}
    except Exception:
        return {"valid": False, "message": "Invalid URL format"}

    hostname = result.netloc.split(":")[0]
    if is_ip_address(hostname):
        return {"valid": False, "message": "IP addresses not allowed. Please use domain names"}

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; PrivacyPolicyAnalyzer/1.0)"}
        response = httpx.head(url, headers=headers, follow_redirects=True, timeout=10.0)
        if response.status_code == 405:  # Method not allowed
            response = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
        if not response.is_success:
            return {
                "valid": False,
                "message": f"URL not accessible (Status code: {response.status_code})",
            }
    except Exception as e:
        return {"valid": False, "message": f"Error accessing URL: {str(e)}"}

    return {"valid": True, "message": "URL is valid"}


def test_document_url(url: str) -> bool:
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

    try:
        response = httpx.head(url, follow_redirects=True, timeout=10.0)
        if response.status_code == 405:  # Method not allowed
            response = httpx.get(url, follow_redirects=True, timeout=10.0)
        return response.status_code == 200
    except Exception as e:
        logger.error("Error accessing URL %s: %s", url, str(e))
        return False


def generate_graph_from_html(
    path: str,
    output_folder: str,
    capture_pdf: bool,
    should_cancel: Callable[[], bool] | None = None,
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
    elif not test_document_url(path):
        raise FileNotFoundError(f"Document is not accessible or does not exist: {path}")
    else:
        logger.info("Verified remote URL accessibility: %s", path)

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
            steps.append(
                ("Crawling source via html_crawler", lambda: html_crawler.main(path, staging))
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
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
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
