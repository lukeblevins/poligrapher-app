import html as html_lib
import ipaddress
import json
import os
import urllib.parse
import logging as logger
import httpx
import shutil
from typing import Callable
from matplotlib import pyplot as plt
import networkx as nx
import yaml

from poligrapher_app.policy_analysis import (
    DocumentCaptureSource,
    GraphKind,
    PolicyDocumentInfo,
)
from poligrapher_app.analysis.privacy_scorer import PrivacyScorer

from poligrapher.scripts import (
    build_graph,
    html_crawler,
    pdf_parser,
    run_annotators,
    init_document,
)

logger = logger.getLogger(__name__)


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
        logger.warning(
            "Failed to copy source PDF %s -> %s: %s", source_path, dest_path, exc
        )
        return False


def is_ip_address(s):
    try:
        return bool(ipaddress.ip_address(s))
    except ValueError:
        return False


def validate_url(url: str) -> dict:
    """Validate URL format and accessibility"""
    if not url or not url.strip():
        return {"valid": False, "message": "No URL provided"}

    url = url.strip()

    # Parse URL
    try:
        result = urllib.parse.urlparse(url)
        if not all([result.scheme, result.netloc]):
            return {"valid": False, "message": "Invalid URL format"}
    except Exception:
        return {"valid": False, "message": "Invalid URL format"}

    # Check for IP addresses
    hostname = result.netloc.split(":")[0]
    if is_ip_address(hostname):
        return {
            "valid": False,
            "message": "IP addresses not allowed. Please use domain names",
        }

    # Check accessibility
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; PrivacyPolicyAnalyzer/1.0)"}
        response = httpx.head(url, headers=headers, follow_redirects=True, timeout=10.0)
        if response.status_code == 405:  # Method not allowed
            response = httpx.get(
                url, headers=headers, follow_redirects=True, timeout=10.0
            )
        if not response.is_success:
            return {
                "valid": False,
                "message": f"URL not accessible (Status code: {response.status_code})",
            }
    except Exception as e:
        return {"valid": False, "message": f"Error accessing URL: {str(e)}"}

    return {"valid": True, "message": "URL is valid"}


def visualize_graph(policy: PolicyDocumentInfo):
    """
    Create and save a knowledge-graph PNG from a YAML export.

    Reads "graph-original.full.yml" in policy.output_dir, builds a graph
    from top-level "nodes" and "links", draws the graph,
    and writes "<output_dir>/knowledge_graph.png".

    Parameters
    ----------
    policy : PolicyDocumentInfo
        Must provide output_dir (path to directory with the YAML file).

    Returns
    -------
    str
        Path to the saved PNG.

    Raises
    ------
    FileNotFoundError
        If the YAML file is missing.
    yaml.YAMLError, KeyError, TypeError, ValueError, OSError
        On parse, data, drawing, or file I/O errors.

    Notes
    -----
    In headless environments set an appropriate matplotlib backend (e.g., "Agg").
    """
    output_folder = policy.output_dir
    yml_file = os.path.join(output_folder, "graph-original.full.yml")
    output_png = os.path.join(output_folder, "knowledge_graph.png")
    if not os.path.exists(yml_file):
        raise FileNotFoundError("YML file not found for visualization.")
    with open(yml_file, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    G = nx.DiGraph()
    for node in data.get("nodes", []):
        G.add_node(node["id"], type=node["type"])
    for link in data.get("links", []):
        G.add_edge(link["source"], link["target"], label=link["key"])
    plt.figure(figsize=(20, 15), facecolor="white")
    pos = nx.spring_layout(G, k=0.5)
    nx.draw(
        G,
        pos,
        with_labels=True,
        node_size=3000,
        node_color="lightblue",
        edge_color="gray",
    )
    edge_labels = nx.get_edge_attributes(G, "label")
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.title("Knowledge Graph")
    plt.savefig(output_png, facecolor="white")
    plt.close()
    return output_png


def generate_cytoscape_html(policy: PolicyDocumentInfo) -> str:
    """Return a self-contained HTML string with an interactive cytoscape.js graph.

    Loads graph-original.full.yml and renders nodes/edges using cytoscape.js
    loaded from CDN. Returns an empty string if the YAML file is missing.
    """
    yml_file = os.path.join(policy.output_dir, "graph-original.full.yml")
    if not os.path.exists(yml_file):
        return ""

    with open(yml_file, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    elements = []
    for node in data.get("nodes", []):
        node_id = node["id"]
        node_type = node.get("type", "DATA")
        elements.append({"data": {"id": node_id, "label": node_id, "type": node_type}})

    for i, link in enumerate(data.get("links", [])):
        elements.append({
            "data": {
                "id": f"e{i}",
                "source": link["source"],
                "target": link["target"],
                "label": link.get("key", ""),
            }
        })

    elements_json = json.dumps(elements)

    # gr.HTML injects via innerHTML, so <script> tags are never executed by the
    # browser. Wrapping in an <iframe srcdoc="..."> creates a fresh browsing
    # context where the full document (including scripts) runs normally.
    inner = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #fafafa; color: #333; }}
  #cy {{ width: 100%; height: calc(100% - 28px); }}
  #legend {{
    font-size: 12px; padding: 4px 10px; line-height: 1.8;
    background: rgba(255,255,255,0.9); display: inline-block;
  }}
  @media (prefers-color-scheme: dark) {{
    html, body {{ background: #1e1e2e; color: #cdd6f4; }}
    #legend {{ background: rgba(30,30,46,0.9); }}
  }}
</style>
</head>
<body>
<div id="legend">
  <span id="dot-data">&#9679;</span> DATA &nbsp;
  <span id="dot-actor">&#9679;</span> ACTOR &nbsp;
  <span id="dot-we">&#9679;</span> we
</div>
<div id="cy"></div>
<script src="https://unpkg.com/cytoscape/dist/cytoscape.min.js"></script>
<script>
(function() {{
  var THEMES = {{
    light: {{
      nodeBg:     '#74b9ff',
      nodeText:   '#1a1a2e',
      actorBg:    '#fab1a0',
      weBg:       '#55efc4',
      edgeLine:   '#636e72',
      edgeText:   '#555555',
      edgeLabelBg:'#ffffff',
      subsum:     '#6c5ce7',
      subsumBy:   '#a29bfe',
      coref:      '#b2bec3',
      dotData:    '#2980b9',
      dotActor:   '#c0392b',
      dotWe:      '#27ae60',
    }},
    dark: {{
      nodeBg:     '#89b4fa',
      nodeText:   '#1e1e2e',
      actorBg:    '#f38ba8',
      weBg:       '#a6e3a1',
      edgeLine:   '#9399b2',
      edgeText:   '#cdd6f4',
      edgeLabelBg:'#1e1e2e',
      subsum:     '#cba6f7',
      subsumBy:   '#b4befe',
      coref:      '#585b70',
      dotData:    '#89b4fa',
      dotActor:   '#f38ba8',
      dotWe:      '#a6e3a1',
    }},
  }};

  function buildStyle(t) {{
    return [
      {{
        selector: 'node',
        style: {{
          'label': 'data(label)',
          'font-size': '11px',
          'text-valign': 'center',
          'text-halign': 'center',
          'background-color': t.nodeBg,
          'color': t.nodeText,
          'text-wrap': 'wrap',
          'text-max-width': '100px',
          'width': 'label',
          'height': 'label',
          'padding': '8px',
          'shape': 'round-rectangle',
        }}
      }},
      {{
        selector: 'node[type = "ACTOR"]',
        style: {{ 'background-color': t.actorBg, 'shape': 'ellipse' }}
      }},
      {{
        selector: 'node[id = "we"]',
        style: {{ 'background-color': t.weBg, 'font-weight': 'bold', 'shape': 'diamond' }}
      }},
      {{
        selector: 'edge',
        style: {{
          'label': 'data(label)',
          'font-size': '10px',
          'color': t.edgeText,
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.2,
          'line-color': t.edgeLine,
          'target-arrow-color': t.edgeLine,
          'text-rotation': 'autorotate',
          'text-background-color': t.edgeLabelBg,
          'text-background-opacity': 0.8,
          'text-background-padding': '2px',
        }}
      }},
      {{
        selector: 'edge[label = "SUBSUM"]',
        style: {{ 'line-style': 'dashed', 'line-color': t.subsum, 'target-arrow-color': t.subsum }}
      }},
      {{
        selector: 'edge[label = "SUBSUM_BY"]',
        style: {{ 'line-style': 'dashed', 'line-color': t.subsumBy, 'target-arrow-color': t.subsumBy }}
      }},
      {{
        selector: 'edge[label = "COREF"]',
        style: {{ 'line-style': 'dotted', 'line-color': t.coref, 'target-arrow-color': t.coref }}
      }},
    ];
  }}

  function applyTheme(dark) {{
    var t = dark ? THEMES.dark : THEMES.light;
    cy.style(buildStyle(t)).update();
    document.getElementById('dot-data').style.color  = t.dotData;
    document.getElementById('dot-actor').style.color = t.dotActor;
    document.getElementById('dot-we').style.color    = t.dotWe;
  }}

  var mq = window.matchMedia('(prefers-color-scheme: dark)');

  var cy = cytoscape({{
    container: document.getElementById('cy'),
    elements: {elements_json},
    style: buildStyle(mq.matches ? THEMES.dark : THEMES.light),
    layout: {{
      name: 'cose',
      animate: false,
      randomize: true,
      nodeRepulsion: 8000,
      idealEdgeLength: 100,
      edgeElasticity: 200,
    }},
  }});

  applyTheme(mq.matches);
  mq.addEventListener('change', function(e) {{ applyTheme(e.matches); }});
}})();
</script>
</body>
</html>"""

    srcdoc = html_lib.escape(inner, quote=True)
    return f'<iframe srcdoc="{srcdoc}" style="width:100%;height:580px;border:1px solid #ccc;border-radius:6px;" frameborder="0"></iframe>'


def score_policy(policy: PolicyDocumentInfo):
    policy.has_results = False
    if policy.has_graph() is False:
        logger.error("No graph was found to score document at %s", policy.output_dir)
        return None
    else:
        scorer = PrivacyScorer()
        results = scorer.score_policy(policy.get_document_text())
        policy.set_privacy_result(results)
        if results.get("success") is True:
            policy.score = results.get("total_score")
            policy.has_results = True
        else:
            policy.score = None
            policy.has_results = False
        return policy.score


def score_policy_with_gdpr(policy: PolicyDocumentInfo):
    policy.has_results = False
    if policy.has_graph() is False:
        logger.error("No graph was found to score document at %s", policy.output_dir)
        return None
    else:
        from poligrapher_app.analysis.gdpr_scorer import GDPRScorer

        artifacts = policy.load_graph_artifacts()
        scorer = GDPRScorer()
        results = scorer.score_policy(
            policy.get_document_text(),
            graphml_graph=artifacts.get("graphml_graph"),
            yaml_graph=artifacts.get("yaml_graph"),
        )
        policy.set_gdpr_result(results)
        if results.get("success") is True:
            policy.score = results.get("total_score")
            policy.has_results = True
        else:
            policy.score = None
            policy.has_results = False
        return policy.score


def format_gdpr_report_markdown(policy: PolicyDocumentInfo) -> str:
    """Render a concise Markdown report for the latest GDPR analysis."""

    result = policy.latest_gdpr_result
    if not result:
        return ""
    if not result.get("success"):
        return f"**GDPR analysis failed:** {', '.join(result.get('feedback', []))}"

    component_scores = result.get("component_scores", {})
    severity_counts = result.get("severity_counts", {})
    flags = result.get("flags", [])
    grouped = result.get("violations_by_rq", {})
    feature_summary = result.get("feature_summary", {})

    lines = [
        "**GDPR Compliance Report**",
        "",
        f"- Score: `{result.get('total_score', 0):.1f}` / 100 (`{result.get('normalized_score', 0):.3f}` normalized)",
        f"- Tier: `{result.get('tier', 'UNKNOWN')}`",
        f"- Summary: {result.get('summary', 'No summary available')}",
        f"- Severity counts: CRITICAL `{severity_counts.get('CRITICAL', 0)}`, HIGH `{severity_counts.get('HIGH', 0)}`, MEDIUM `{severity_counts.get('MEDIUM', 0)}`",
    ]

    if component_scores:
        lines.append("- Component scores:")
        for name, payload in component_scores.items():
            lines.append(
                f"  - {name.title()}: `{payload.get('score', 0):.3f}` (weight `{payload.get('weight', 0):.2f}`)"
            )

    if flags:
        lines.append(f"- Flags: {', '.join(flags)}")

    if feature_summary:
        lines.append(
            "- Text features: "
            f"`{feature_summary.get('n_words', 0)}` words, "
            f"`{feature_summary.get('n_sentences', 0)}` sentences, "
            f"passive ratio `{feature_summary.get('passive_ratio', 0):.3f}`, "
            f"CCPA coverage `{feature_summary.get('ccpa_coverage', 0):.3f}`"
        )
        lines.append(
            "- Readability: "
            f"FK `{feature_summary.get('flesch_kincaid', 0):.2f}`, "
            f"GF `{feature_summary.get('gunning_fog', 0):.2f}`, "
            f"FRE `{feature_summary.get('flesch_reading_ease', 0):.2f}`"
        )

    lines.append("")
    lines.append("**Top Violations**")
    any_violation = False
    for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6"):
        violations = grouped.get(rq, [])
        if not violations:
            continue
        any_violation = True
        lines.append(f"- {rq}:")
        for violation in violations[:3]:
            scope = violation.get("scope", "GDPR")
            lines.append(
                f"  - `{violation.get('code')}` [{violation.get('severity')}, {scope}] {violation.get('description')}: {violation.get('detail')}"
            )
    if not any_violation:
        lines.append("- No violations triggered.")

    return "\n".join(lines)


def test_document_url(url: str) -> bool:
    """Test if the document URL is reachable with a 200 response.

    Notes:
    - Returns False silently for local file paths or values without http/https scheme.
    - Avoids emitting noisy errors for non-URL inputs (e.g., absolute file paths).
    """
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        # Not an http(s) URL → treat as non-URL; return False without logging
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


def generate_graph_from_html(path, output_folder, capture_pdf: bool):
    logger.info(
        "Starting PoliGraph pipeline (capture_pdf=%s) for %s -> %s",
        capture_pdf,
        path,
        output_folder,
    )
    # Normalize file:// URIs to filesystem paths
    try:
        parsed = urllib.parse.urlparse(path)
        if parsed.scheme == "file":
            path = parsed.path
    except Exception:
        pass
    # Prefer local file check first to avoid URL probes on file paths
    if os.path.isfile(path):
        logger.info("Verified local file input: %s", path)
    else:
        if test_document_url(path) is False:
            raise FileNotFoundError(
                f"Document is not accessible or does not exist: {path}"
            )
        logger.info("Verified remote URL accessibility: %s", path)

    os.makedirs(output_folder, exist_ok=True)

    steps: list[tuple[str, Callable[[], None]]] = []

    if capture_pdf:
        ensure_source_pdf_copy(path, output_folder)
        html_path = os.path.join(output_folder, "output.html")

        def _pdf_parse():
            pdf_parser.main(path, output_folder)

        def _crawl_html_from_pdf():
            html_crawler.main(html_path, output_folder)

        if not os.path.exists(html_path):
            steps.append(("Extracting PDF to HTML via pdf_parser", _pdf_parse))
        else:
            logger.info(
                "Cached PDF conversion detected (%s); skipping pdf_parser",
                html_path,
            )

        steps.append(("Crawling parsed HTML via html_crawler", _crawl_html_from_pdf))
    else:

        def _crawl_source():
            html_crawler.main(path, output_folder)

        steps.append(("Crawling source via html_crawler", _crawl_source))

    steps.extend(
        [
            (
                "Initializing document (init_document)",
                lambda: init_document.main(workdirs=[output_folder]),
            ),
            (
                "Running annotators",
                lambda: run_annotators.main(workdirs=[output_folder]),
            ),
            (
                "Building standard graph",
                lambda: build_graph.main(workdirs=[output_folder]),
            ),
            (
                "Building pretty graph",
                lambda: build_graph.main(pretty=True, workdirs=[output_folder]),
            ),
        ]
    )

    total_steps = len(steps)
    for idx, (message, step_fn) in enumerate(steps, 1):
        logger.info("[%d/%d] %s", idx, total_steps, message)
        step_fn()

    logger.info("Completed PoliGraph pipeline for %s", output_folder)


def generate_graph(policy: PolicyDocumentInfo):
    """Run the full PoliGraph pipeline for a single policy."""
    match policy.source:
        case DocumentCaptureSource.WEBPAGE:
            capture_pdf = False
        case DocumentCaptureSource.PDF:
            capture_pdf = True
        case _:
            raise ValueError(f"Unknown document source: {policy.source}")

    try:
        logger.info(
            "Triggering pipeline for policy %s (source=%s)",
            policy.path,
            policy.source,
        )
        generate_graph_from_html(policy.path, policy.output_dir, capture_pdf)
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
    """Infer the graph kind (STANDARD, LLM, NONE) based on available files."""
    standard_yml = os.path.join(policy.output_dir, "graph-original.yml")
    # TODO: update this when LLM graph generation is added
    llm_yml = os.path.join(policy.output_dir, "graph-llm.yml")
    if os.path.exists(llm_yml):
        return GraphKind.LLM
    elif os.path.exists(standard_yml):
        return GraphKind.STANDARD
    else:
        return GraphKind.NONE


# def score_existing_policy(policy: PolicyDocumentInfo):
#     """Score an existing policy without regenerating the knowledge graph.

#     Assumes the graph/html artifacts already exist in the standard output folder.
#     """
#     try:
#         # output_folder_variants = [
#         #     os.path.join(
#         #         "../../PoliGraph-Setup/output", policy.company_name.replace(" ", "_")
#         #     ),
#         #     os.path.join("./output", policy.company_name.replace(" ", "_")),
#         # ]
#         output_folder = policy.output_dir
#         # for folder in output_folder_variants:
#         #     if os.path.isdir(folder):
#         #         output_folder = folder
#         #         break
#         # if output_folder is None:
#         #     return {"success": False, "message": "Existing output folder not found"}

#         # Collect text from any html files present
#         policy_text = ""
#         for fname in os.listdir(output_folder):
#             if fname.endswith(".html"):
#                 fpath = os.path.join(output_folder, fname)
#                 try:
#                     with open(fpath, "r", encoding="utf-8") as f:
#                         soup = BeautifulSoup(f.read(), "html.parser")
#                         for tag in soup.find_all(
#                             ["p", "li", "h1", "h2", "h3", "h4", "div"]
#                         ):
#                             policy_text += tag.get_text() + "\n"
#                 except Exception:
#                     continue

#         if not policy_text:
#             # Fallback: attempt using extract_policy_text helper (expects folder)
#             try:
#                 policy_text = extract_policy_text(output_folder)
#             except Exception:
#                 pass

#         if not policy_text:
#             return {"success": False, "message": "No existing HTML text found to score"}

#         scorer = PrivacyScorer()
#         results = scorer.score_policy(policy_text)

#         # Locate existing graphml if present
#         graphml_path = None
#         for candidate in [
#             os.path.join(output_folder, "graph-original.graphml"),
#             os.path.join(output_folder, "graph.graphml"),
#         ]:
#             if os.path.exists(candidate):
#                 graphml_path = candidate
#                 break

#         graph_json_path = graphml_to_json(graphml_path) if graphml_path else None

#         # Update policy flags
#         policy.has_results = policy.score is not None

#         return {
#             "success": True,
#             "message": "Scoring complete (existing graph reused)",
#             "result": {
#                 "total_score": results.get("total_score"),
#                 "grade": results.get("grade"),
#                 "category_scores": results.get("category_scores"),
#                 "feedback": results.get("feedback", []),
#                 "graph_json_path": graph_json_path,
#                 "structured": policy,
#             },
#         }
#     except Exception as e:
#         return {"success": False, "message": f"Error scoring existing policy: {str(e)}"}

def graphml_to_json(graphml_path):
    # Sanitize filename
    base_filename = os.path.splitext(os.path.basename(graphml_path))[0]
    graph_json_filename = f"{base_filename}.json"
    graph_json_path = os.path.join("./static/graphml/json", graph_json_filename)

    # Convert GraphML to JSON
    G = nx.read_graphml(graphml_path)
    nodes = [{"data": {"id": node, "label": node}} for node in G.nodes()]
    edges = [
        {
            "data": {
                "source": source,
                "target": target,
                "label": G.get_edge_data(source, target).get("label", "") or "",
            }
        }
        for source, target in G.edges()
    ]
    elements = nodes + edges

    # Save JSON
    os.makedirs(os.path.dirname(graph_json_path), exist_ok=True)
    with open(graph_json_path, "w", encoding="utf-8") as f:
        json.dump(elements, f)

    # Return web path
    web_path = f"/static/graphml/json/{graph_json_filename}"
    return web_path


# def search_policy_info(query):
#     # Simulated database query
#     policies = [
#         ("Privacy Policy A", 98, "https://example.com/privacy_policy_a"),
#         ("Privacy Policy B", 94, "https://example.com/privacy_policy_b"),
#         ("Privacy Policy M", 82, "https://example.com/privacy_policy_m"),
#         ("Privacy Policy X", 15, "https://example.com/privacy_policy_x"),
#     ]

#     return [policy for policy in policies if query.lower() in policy[0].lower()]


# def fetch_analysis_from_db(url):
#     print(f"Returning hardcoded mock analysis for URL: {url}")

#     total_score = 92.1
#     grade = "A"
#     category_scores = {
#         "data_collection": {
#             "raw_score": 220,
#             "weighted_score": 22.0,
#             "feedback": ["Clear data collection purpose", "Minimal data collected"],
#         },
#         "third_party_sharing": {
#             "raw_score": 250,
#             "weighted_score": 25.0,
#             "feedback": ["Transparent third-party disclosures"],
#         },
#         "user_rights": {
#             "raw_score": 230,
#             "weighted_score": 23.0,
#             "feedback": ["Users can delete data", "Clear opt-out mechanisms"],
#         },
#         "data_security": {
#             "raw_score": 220,
#             "weighted_score": 22.1,
#             "feedback": ["Encryption noted", "Breach policy documented"],
#         },
#     }

#     feedback = [
#         item for section in category_scores.values() for item in section["feedback"]
#     ]

#     return {
#         "total_score": total_score,
#         "grade": grade,
#         "category_scores": category_scores,
#         "feedback": feedback,
#         "graph_json_path": "/static/graphml/json/akili.json",  # Shows the PoliGraph
#     }


# def render_analysis_output(
#     *, url=None, pdf=None, total_score=None, grade=None, category_scores=None
# ):
#     try:
#         normalized_score = (total_score / 100.0) * 10.0

#         summary_html = f"""
#         <div class='summary-section'>
#             <h3>Total Score: {normalized_score:.1f}</h3>
#             <h3>Grade: {grade}</h3>
#             <p><strong>Feedback:</strong> {', '.join([f for cat in category_scores.values() for f in cat['feedback']]) or 'No feedback available'}</p>
#         </div>
#         """

#         accordion_html = ""
#         for category, scores in category_scores.items():
#             feedback = "<br>".join(scores["feedback"]) or "None"
#             accordion_html += f"""
#             <details>
#                 <summary><strong>{category.replace('_', ' ').title()}</strong></summary>
#                 <p>Raw Score: {scores['raw_score']}</p>
#                 <p>Weighted Score: {scores['weighted_score']}</p>
#                 <p>Feedback: {feedback}</p>
#             </details>
#             """

#         return summary_html, accordion_html

#     except Exception as e:
#         print(f"Error in render_analysis_output: {str(e)}")
#         return (
#             "<div>Error generating summary</div>",
#             "<div>Error generating details</div>",
#         )

# def fetch_policy_data():
#     try:
#         top_policies, low_policies, recent_policies = get_policy_info()
#         return {
#             "top_policies": top_policies,
#             "low_policies": low_policies,
#             "recent_policies": recent_policies,
#         }
#     except Exception as e:
#         return {"error": str(e)}
