"""Policy analysis domain entities used by the Gradio app.

Historically the UI + experimental notebooks accessed policy metadata, file
paths, and derived scores by passing around raw rows from one or more CSV
files (e.g., columns like `provider`, `policy_path`, `score`, flags, etc.).
That approach caused several problems:

1. Tight coupling / duplication: Every place that needed policy data re‑built
    file system paths (often slightly differently) and re‑implemented checks
    like "does the graph image exist?".
2. Brittle refactors: Renaming a column or changing artifact names required
    hunting through ad‑hoc DataFrame code across the app.
3. Implicit semantics: There was no obvious, typed distinction between a
    provider (company), a *captured* document (PDF vs scraped HTML bundle), and
    an *analysis result* (score associated with a chosen graph representation).
4. Mixed concerns: Text extraction logic sometimes leaked into UI callbacks.

This module replaces the ad‑hoc CSV row passing pattern with light‑weight
entity classes that encapsulate behavior, hide path conventions, and make the
intent explicit. Enumerations (`DocumentCaptureSource`, `GraphKind`) provide
closed sets instead of free‑form strings, reducing silent typos.

Key concepts:
* PolicyDocumentInfo  -> a concrete captured policy (folder of artifacts) and
                                 utilities to extract its raw text.
* PolicyAnalysisResult -> an analysis *outcome* (e.g., score produced from a
                                  particular graph flavor) tied back to a document.
* PolicyDocumentProvider -> groups multiple documents + results for a single
                                     organization (company) and centralizes its output
                                     directory naming.

When adding new artifact types or analysis dimensions, extend the relevant
entity (e.g., another helper on PolicyDocumentInfo) rather than sprinkling new
CSV columns + path logic across the UI. This keeps downstream code declarative
and easier to test.
"""

from datetime import date, datetime, timezone
from enum import Enum
import json
from collections import Counter
from statistics import mean, median
from typing import Iterable
import os

from bs4 import BeautifulSoup
import networkx as nx
import pymupdf4llm

from poligrapher.graph_utils import yaml_load_graph

class DocumentCaptureSource(Enum):
    """Origin / capture modality of a policy.

    Replaces prior string literals (e.g., 'pdf', 'html', 'web') scattered in
    CSV rows. Using an Enum gives IDE autocomplete + guards against typos.
    """

    PDF = "pdf"
    WEBPAGE = "webpage"

class GraphKind(Enum):
    """Type of knowledge graph / extraction variant used for scoring.

    STANDARD: the traditional pipeline graph (token + annotator edges).
    LLM: an alternative / experimental graph derived via LLM summarization.
    NONE: placeholder when a score exists independent of a graph variant.
    """

    STANDARD = "standard"
    LLM = "llm"
    NONE = "none"

class PipelineStatus(Enum):
    """Lifecycle state of the pipeline for a captured document."""

    PENDING = "pending"
    """The pipeline has not produced artifacts and no blocking errors were recorded."""

    SUCCEEDED = "succeeded"
    """Expected graph artifacts are present and no blocking errors exist."""

    FAILED = "failed"
    """Blocking errors were recorded that prevented graph generation."""


class PolicyDocumentInfo:
    """Encapsulates a single captured policy artifact set.

    Attributes
    -----------
    path: Original source path (file system path for PDF or root of scraped
          HTML bundle). Maintained for provenance.
    output_dir: Working directory produced by the pipeline (contains
                accessibility_tree.json, cleaned.html, document.pickle,
                graph-original.yml, knowledge_graph.png, etc.). Centralized so
                callers don't rebuild paths manually.
    source: Capture modality (Enum) -> replaces earlier free‑form CSV field.
    capture_date: Date the policy was captured (previously often stored as a
                  string column). Use a date object to make comparisons &
                  formatting explicit.
    has_results: Convenience flag signaling if any analyses have been run.

    Behavior
    --------
    Provides helper predicates (has_graph / has_image) and text extraction
    logic that used to live inside UI callbacks or notebook cells.
    """

    path: str
    output_dir: str
    source: DocumentCaptureSource
    capture_date: date
    has_results: bool = False
    errors: list[dict]
    score: float | None
    latest_privacy_result: dict | None
    latest_gdpr_result: dict | None

    def __init__(
        self,
        path: str,
        output_dir: str,
        source: DocumentCaptureSource,
        capture_date: date,
        has_results: bool,
        errors: Iterable[str] | None = None,
    ):
        self.path = path  # Raw source path for traceability
        self.output_dir = output_dir  # Pipeline workdir root
        self.source = source
        self.capture_date = capture_date
        self.has_results = has_results
        self.errors = []
        self.score = None
        self.latest_privacy_result = None
        self.latest_gdpr_result = None
        if errors:
            self.extend_errors(errors)

    @staticmethod
    def _make_error_entry(message: str) -> dict:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }

    @staticmethod
    def _normalize_error_value(value) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        if isinstance(value, dict):
            msg = value.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
        return None

    def _add_error(self, message: str, timestamp: str | None = None):
        if not message:
            return
        if any(entry.get("message") == message for entry in self.errors):
            return
        entry = {
            "message": message,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
        self.errors.append(entry)
        self.has_results = False

    @staticmethod
    def _resolve_artifact_path(output_dir: str, candidates: tuple[str, ...]) -> str | None:
        if not os.path.exists(output_dir):
            return None
        for candidate in candidates:
            path = os.path.join(output_dir, candidate)
            if os.path.exists(path):
                return path
        return None

    def get_graph_yaml_path(self) -> str | None:
        """Return the canonical YAML graph artifact path if present."""

        return self._resolve_artifact_path(
            self.output_dir,
            ("graph-original.yml", "graph.yml"),
        )

    def get_graphml_path(self) -> str | None:
        """Return the canonical GraphML graph artifact path if present."""

        return self._resolve_artifact_path(
            self.output_dir,
            ("graph-original.graphml", "graph.graphml"),
        )

    def has_graph(self) -> bool:
        """True if a graph YAML exists for this document.

        Centralizes canonical filename ("graph-original.yml") so changes only
        occur here vs. many string literals previously embedded in CSV logic.
        """
        return self.get_graph_yaml_path() is not None

    def has_graphml(self) -> bool:
        """True if a GraphML export exists for this document."""

        return self.get_graphml_path() is not None

    def has_image(self) -> bool:
        """True if the rendered graph image artifact exists."""
        png_path = os.path.join(self.output_dir, "knowledge_graph.png")
        return os.path.exists(self.output_dir) and os.path.exists(png_path)

    def load_graphml(self) -> nx.DiGraph:
        """Load the pretty GraphML representation for this document."""

        graphml_path = self.get_graphml_path()
        if not graphml_path:
            raise FileNotFoundError(f"No GraphML file found in {self.output_dir}")
        return nx.read_graphml(graphml_path)

    def load_graph_yaml(self) -> nx.MultiDiGraph:
        """Load the canonical YAML graph artifact for this document."""

        yaml_path = self.get_graph_yaml_path()
        if not yaml_path:
            raise FileNotFoundError(f"No graph YAML file found in {self.output_dir}")
        with open(yaml_path, "r", encoding="utf-8") as fin:
            return yaml_load_graph(fin)

    def load_graph_artifacts(self) -> dict:
        """Return both graph representations needed by downstream scorers."""

        yaml_path = self.get_graph_yaml_path()
        graphml_path = self.get_graphml_path()
        return {
            "graph_yaml_path": yaml_path,
            "graphml_path": graphml_path,
            "yaml_graph": self.load_graph_yaml() if yaml_path else None,
            "graphml_graph": self.load_graphml() if graphml_path else None,
        }

    def get_graph_statistics(self) -> dict | None:
        """Compute graph summary statistics for the document's YAML graph."""

        if not self.has_graph():
            return None

        yaml_graph = self.load_graph_yaml()
        node_count = yaml_graph.number_of_nodes()
        edge_count = yaml_graph.number_of_edges()

        node_type_counts = Counter(
            str(data.get("type", "UNKNOWN")) for _, data in yaml_graph.nodes(data=True)
        )
        edge_type_counts = Counter(
            str(key or data.get("relationship") or "UNKNOWN")
            for _, _, key, data in yaml_graph.edges(keys=True, data=True)
        )
        edge_name_counts = Counter(
            f"{src} -> {dst} [{key or data.get('relationship') or 'UNKNOWN'}]"
            for src, dst, key, data in yaml_graph.edges(keys=True, data=True)
        )

        undirected_graph = nx.Graph()
        undirected_graph.add_nodes_from(yaml_graph.nodes(data=True))
        undirected_graph.add_edges_from((src, dst) for src, dst in yaml_graph.edges())

        degrees = [degree for _, degree in undirected_graph.degree()]
        in_degrees = [degree for _, degree in yaml_graph.in_degree()]
        out_degrees = [degree for _, degree in yaml_graph.out_degree()]

        components = (
            list(nx.connected_components(undirected_graph))
            if node_count
            else []
        )
        component_sizes = sorted((len(component) for component in components), reverse=True)
        largest_component_nodes = (
            undirected_graph.subgraph(max(components, key=len)).copy()
            if components
            else nx.Graph()
        )

        avg_shortest_path = None
        if largest_component_nodes.number_of_nodes() > 1:
            try:
                avg_shortest_path = nx.average_shortest_path_length(
                    largest_component_nodes
                )
            except Exception:
                avg_shortest_path = None

        top_degree_nodes = sorted(
            undirected_graph.degree(),
            key=lambda item: (-item[1], str(item[0])),
        )[:10]
        top_in_degree_nodes = sorted(
            yaml_graph.in_degree(),
            key=lambda item: (-item[1], str(item[0])),
        )[:10]
        top_out_degree_nodes = sorted(
            yaml_graph.out_degree(),
            key=lambda item: (-item[1], str(item[0])),
        )[:10]

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "node_type_counts": dict(node_type_counts),
            "edge_type_counts": dict(edge_type_counts),
            "edge_name_counts": dict(edge_name_counts),
            "degree": {
                "min": min(degrees) if degrees else 0,
                "max": max(degrees) if degrees else 0,
                "mean": mean(degrees) if degrees else 0.0,
                "median": median(degrees) if degrees else 0.0,
            },
            "in_degree": {
                "min": min(in_degrees) if in_degrees else 0,
                "max": max(in_degrees) if in_degrees else 0,
                "mean": mean(in_degrees) if in_degrees else 0.0,
                "median": median(in_degrees) if in_degrees else 0.0,
            },
            "out_degree": {
                "min": min(out_degrees) if out_degrees else 0,
                "max": max(out_degrees) if out_degrees else 0,
                "mean": mean(out_degrees) if out_degrees else 0.0,
                "median": median(out_degrees) if out_degrees else 0.0,
            },
            "density": nx.density(undirected_graph) if node_count > 1 else 0.0,
            "average_clustering": (
                nx.average_clustering(undirected_graph)
                if node_count > 1
                else 0.0
            ),
            "transitivity": nx.transitivity(undirected_graph) if node_count > 2 else 0.0,
            "component_count": len(components),
            "largest_component_size": component_sizes[0] if component_sizes else 0,
            "largest_component_ratio": (
                (component_sizes[0] / node_count) if component_sizes and node_count else 0.0
            ),
            "average_shortest_path_largest_component": avg_shortest_path,
            "isolated_nodes": len(list(nx.isolates(undirected_graph))),
            "self_loop_count": nx.number_of_selfloops(yaml_graph),
            "top_degree_nodes": top_degree_nodes,
            "top_in_degree_nodes": top_in_degree_nodes,
            "top_out_degree_nodes": top_out_degree_nodes,
        }

    def format_graph_statistics_markdown(self) -> str:
        """Render graph statistics as concise Markdown for the UI."""

        stats = self.get_graph_statistics()
        if not stats:
            return ""

        def _fmt_counter(counter_map: dict[str, int], limit: int = 12) -> str:
            if not counter_map:
                return "_None_"
            items = sorted(counter_map.items(), key=lambda item: (-item[1], item[0]))[:limit]
            return ", ".join(f"`{name}`: {count}" for name, count in items)

        def _fmt_node_list(items: list[tuple[str, int]], limit: int = 5) -> str:
            if not items:
                return "_None_"
            return ", ".join(f"`{node}` ({degree})" for node, degree in items[:limit])

        avg_path = stats.get("average_shortest_path_largest_component")
        avg_path_text = f"{avg_path:.2f}" if isinstance(avg_path, (int, float)) else "n/a"

        lines = [
            "**Graph Statistics**",
            "",
            f"- Nodes: `{stats['node_count']}`",
            f"- Edges: `{stats['edge_count']}`",
            f"- Node types: {_fmt_counter(stats['node_type_counts'])}",
            f"- Edge types: {_fmt_counter(stats['edge_type_counts'])}",
            f"- Edge names: {_fmt_counter(stats['edge_name_counts'])}",
            (
                f"- Degree (undirected): min `{stats['degree']['min']}`, max `{stats['degree']['max']}`, "
                f"mean `{stats['degree']['mean']:.2f}`, median `{stats['degree']['median']:.2f}`"
            ),
            (
                f"- In-degree: min `{stats['in_degree']['min']}`, max `{stats['in_degree']['max']}`, "
                f"mean `{stats['in_degree']['mean']:.2f}`, median `{stats['in_degree']['median']:.2f}`"
            ),
            (
                f"- Out-degree: min `{stats['out_degree']['min']}`, max `{stats['out_degree']['max']}`, "
                f"mean `{stats['out_degree']['mean']:.2f}`, median `{stats['out_degree']['median']:.2f}`"
            ),
            (
                f"- Density: `{stats['density']:.4f}` | Clustering: `{stats['average_clustering']:.4f}` | "
                f"Transitivity: `{stats['transitivity']:.4f}`"
            ),
            (
                f"- Components: `{stats['component_count']}` | Largest component: "
                f"`{stats['largest_component_size']}` nodes (`{stats['largest_component_ratio']:.1%}` of graph)"
            ),
            (
                f"- Avg shortest path (largest component): `{avg_path_text}` | "
                f"Isolated nodes: `{stats['isolated_nodes']}` | Self-loops: `{stats['self_loop_count']}`"
            ),
            f"- Top hubs: {_fmt_node_list(stats['top_degree_nodes'])}",
            f"- Top in-degree nodes: {_fmt_node_list(stats['top_in_degree_nodes'])}",
            f"- Top out-degree nodes: {_fmt_node_list(stats['top_out_degree_nodes'])}",
        ]
        return "\n".join(lines)

    def _extract_text_from_webpage(self, path: str) -> str:
        """Aggregate visible text from stored HTML files.

        Previously: code in notebooks iterated over a directory, parsed each
        HTML with BeautifulSoup, and concatenated <p> text inline. Encapsulate
        that once so consumers just call get_document_text().
        """
        policy_text = ""
        for fname in os.listdir(path):
            if fname.endswith(".html"):
                fpath = os.path.join(path, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        soup = BeautifulSoup(f.read(), "html.parser")
                        for tag in soup.find_all(
                            ["p", "li", "h1", "h2", "h3", "h4", "div"]
                        ):
                            policy_text += tag.get_text() + "\n"
                except Exception:
                    continue
        return policy_text

    def _extract_text_from_pdf(self, path: str) -> str:
        """Extract raw text from the first PDF in the folder.

        Consolidates PDF parsing logic (previously replicated where needed).
        If multiple PDFs ever need support, evolve the selection rule here
        without touching callers.
        """
        # get first pdf item in folder
        pdf_path = None
        for fname in os.listdir(path):
            if fname.endswith(".pdf"):
                pdf_path = os.path.join(path, fname)
                break

        if not pdf_path:
            raise FileNotFoundError("No PDF file found")

        policy_text = ""
        doc = pymupdf4llm.pymupdf.open(pdf_path)
        for page in doc:
            text = page.get_text()
            policy_text += text + "\n"
        return policy_text

    def get_document_text(self) -> str:
        """Unified text accessor (source‑aware).

        Hides modality branching so calling code does not duplicate if/else
        logic. Returns empty string on unsupported sources for resilience.
        """
        if self.source == DocumentCaptureSource.PDF:
            return self._extract_text_from_pdf(self.output_dir)
        elif self.source == DocumentCaptureSource.WEBPAGE:
            return self._extract_text_from_webpage(self.output_dir)
        return ""

    @property
    def pipeline_status(self) -> PipelineStatus:
        """Return the pipeline lifecycle status for this document."""

        if self.errors:
            return PipelineStatus.FAILED
        if self.has_graph():
            return PipelineStatus.SUCCEEDED
        return PipelineStatus.PENDING

    @property
    def pipeline_failed(self) -> bool:
        """Convenience boolean for quickly checking pipeline failure."""

        return self.pipeline_status is PipelineStatus.FAILED

    def record_error(self, message: str):
        """Record a pipeline error message preventing graph generation."""

        normalized = (message or "").strip()
        if not normalized:
            return
        self._add_error(normalized)

    def extend_errors(self, messages: Iterable[str]):
        """Record multiple error messages at once."""

        if not messages:
            return
        for message in messages:
            timestamp = None
            if isinstance(message, dict):
                timestamp = message.get("timestamp") if isinstance(message.get("timestamp"), str) else None
                message = message.get("message")
            normalized = self._normalize_error_value(message)
            if normalized:
                self._add_error(normalized, timestamp)

    def clear_errors(self):
        """Reset any recorded pipeline errors."""

        self.errors.clear()

    def get_errors(self) -> list[dict]:
        """Return a copy of the recorded pipeline errors."""

        return [dict(entry) for entry in self.errors]

    def get_error_messages(self) -> list[str]:
        """Return just the error messages in insertion order."""

        return [entry.get("message", "") for entry in self.errors]

    def serialize_errors(self) -> str:
        """Serialize recorded errors for persistence."""

        return json.dumps(self.errors, ensure_ascii=False)

    def load_errors_from_string(self, data: str | None):
        """Replace recorded errors from a serialized string."""

        if not data:
            self.errors.clear()
            return
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = data

        cleaned: list[dict] = []

        def _add_if_new(msg: str, timestamp: str | None = None):
            if not msg:
                return
            if any(entry.get("message") == msg for entry in cleaned):
                return
            cleaned.append(
                {
                    "message": msg,
                    "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                }
            )

        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    msg = self._normalize_error_value(item)
                    ts = item.get("timestamp") if isinstance(item, dict) else None
                    if msg:
                        _add_if_new(msg, ts if isinstance(ts, str) else None)
                else:
                    msg = self._normalize_error_value(item)
                    if msg:
                        _add_if_new(msg)
        elif isinstance(parsed, dict):
            msg = self._normalize_error_value(parsed)
            ts_val = parsed.get("timestamp") if isinstance(parsed, dict) else None
            if msg:
                _add_if_new(msg, ts_val if isinstance(ts_val, str) else None)
        else:
            msg = self._normalize_error_value(parsed)
            if msg:
                _add_if_new(msg)

        self.errors = cleaned

    def set_privacy_result(self, result: dict | None):
        """Record the latest basic privacy scoring result."""

        self.latest_privacy_result = result
        if result and result.get("success"):
            self.score = result.get("total_score")

    def set_gdpr_result(self, result: dict | None):
        """Record the latest GDPR scoring result."""

        self.latest_gdpr_result = result
        if result and result.get("success"):
            self.score = result.get("total_score")

class PolicyAnalysisResult:
    """Represents the outcome of analyzing a document with a specific graph kind.

    Encapsulates (document ↔ score ↔ graph variant) triple that used to be
    spread across multiple CSV columns. Keeping this as a distinct object lets
    us associate future metadata (confidence intervals, method version, etc.)
    without schema churn across the UI.
    """

    document: PolicyDocumentInfo
    score: float
    kind: GraphKind
    analysis_type: str
    details: dict | None

    def __init__(
        self,
        document: PolicyDocumentInfo,
        score: float,
        kind: GraphKind,
        analysis_type: str = "privacy",
        details: dict | None = None,
    ):
        self.document = document
        self.score = score
        self.kind = kind
        self.analysis_type = analysis_type
        self.details = details

    def get_graph_image_path(self) -> str:
        """Return the canonical graph image path for the linked document."""
        return os.path.join(self.document.output_dir, "knowledge_graph.png")

class PolicyDocumentProvider:
    """Represents a single organization (company) that owns policies.

    Collates its documents and analysis results. Previously, grouping logic
    lived in Pandas groupby chains over provider columns. Centralizing here
    gives a single place to evolve naming (e.g., output directory slug rules)
    and attach provider metadata (industry, region, risk tier, etc.).
    """

    def __init__(self, name: str, industry: str = "Unknown", documents: list[PolicyDocumentInfo] = None, results: list[PolicyAnalysisResult] = None):
        self.name = name
        self.documents = documents if documents is not None else []
        self.results = results if results is not None else []
        self.industry = industry
        # Central slug formatting; previously duplicated with subtle variations.
        self.output_dir = f"./output/{name.replace(' ', '_')}"

    def add_document(self, document: PolicyDocumentInfo):
        """Attach a new captured policy to this provider."""
        self.documents.append(document)

    def add_result(self, result: PolicyAnalysisResult):
        """Record an analysis result for one of the provider's documents."""
        self.results.append(result)
