"""Convert an ephemeral PoliGraph workspace into durable canonical results."""

from __future__ import annotations

import os
import zipfile
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo
from poligrapher_app.services.graph import build_cytoscape_elements, graph_statistics
from poligrapher_app.services.storage import artifact_key, get_storage

ARCHIVE_NAMES = {
    "graph-original.yml",
    "graph-original.full.yml",
    "graph-original.graphml",
    "graph.yml",
    "graph.graphml",
    "cleaned.html",
    "output.html",
    "readability.json",
    "accessibility_tree.json",
    "output.pdf",
}


def canonical_results(doc: PolicyDocumentInfo) -> tuple[dict, dict | None]:
    return {"elements": build_cytoscape_elements(doc)}, graph_statistics(doc)


def create_artifact_archive(output_dir: str | Path, archive_path: str | Path) -> int:
    root = Path(output_dir)
    selected = [p for p in root.rglob("*") if p.is_file() and (p.name in ARCHIVE_NAMES or p.suffix in {".txt", ".log"})]
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in selected:
            archive.write(path, path.relative_to(root))
    return len(selected)


def persist_workspace(policy, doc: PolicyDocumentInfo, archive_path: str | Path) -> None:
    graph_data, stats = canonical_results(doc)
    if not graph_data["elements"]:
        raise RuntimeError("Pipeline produced no canonical graph elements")
    create_artifact_archive(doc.output_dir, archive_path)
    key = artifact_key(policy.id)
    get_storage().upload_file(key, archive_path, content_type="application/zip")
    policy.graph_data = graph_data
    policy.graph_stats = stats
    policy.artifact_blob_key = key
    policy.persistence_status = "persisted"


def legacy_graph_data(output_dir: str | Path) -> dict | None:
    doc = PolicyDocumentInfo(str(output_dir), str(output_dir), __import__(
        "poligrapher_app.domain.policy_analysis", fromlist=["DocumentCaptureSource"]
    ).DocumentCaptureSource.WEBPAGE, __import__("datetime").date.today(), False)
    data, _ = canonical_results(doc)
    return data if data["elements"] else None


@contextmanager
def temporary_document(policy, *, restore_artifacts: bool = False):
    """Materialize a policy into an isolated workspace and always clean it up."""
    temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
    with tempfile.TemporaryDirectory(prefix="poligrapher-", dir=temp_root) as workspace:
        root = Path(workspace)
        output = root / "output"
        path = policy.url
        storage = get_storage()
        if policy.source == "pdf":
            if not policy.source_blob_key:
                raise FileNotFoundError("Policy has no durable source PDF")
            source = root / (policy.source_filename or "source.pdf")
            storage.download_file(policy.source_blob_key, source)
            path = str(source)
        if restore_artifacts:
            if not policy.artifact_blob_key:
                raise FileNotFoundError("Policy has no durable artifact archive")
            archive = root / "artifacts.zip"
            storage.download_file(policy.artifact_blob_key, archive)
            output.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(output)
        doc = PolicyDocumentInfo(path, str(output), DocumentCaptureSource(policy.source),
                                 policy.capture_date or date.today(), policy.has_results,
                                 policy.pipeline_errors)
        yield doc, root
