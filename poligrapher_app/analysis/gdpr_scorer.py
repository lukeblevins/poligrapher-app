from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
import re
from typing import Any

import networkx as nx
import toml

try:
    import textstat
except ImportError:  # pragma: no cover - covered by runtime fallback tests
    textstat = None


class GDPRScorer:
    """Graph-aware GDPR compliance scorer derived from the research PDF.

    The implementation uses PoliGrapher's primary exported artifact:
    - GraphML: used for the rendered graph structure and node typing
    and also uses the following secondary artifacts for richer extraction of the features:
    - YAML: for richer edge metadata
    - Policy text: Used for disclosures not preserved explicitly in
      the output graph schema (for example lawful basis or DPO contact language).
    """

    def __init__(self, scoring_rules: dict | None = None, scoring_criteria: dict | None = None):
        self.rules = scoring_rules or self.load_default_rules()
        self.criteria = scoring_criteria or self.load_scoring_criteria()
        self.codes: dict[str, dict[str, Any]] = self.criteria.get("codes", {})
        self.research_questions: dict[str, str] = self.criteria.get(
            "research_questions",
            {},
        )

    def load_default_rules(self) -> dict[str, Any]:
        rules_path = Path("poligrapher/analysis/config/gdpr_scoring_rules.toml")
        if not rules_path.exists():
            raise FileNotFoundError(f"GDPR scoring rules not found at: {rules_path}")
        return toml.load(rules_path)

    def load_scoring_criteria(self) -> dict[str, Any]:
        criteria_path = Path("poligrapher/analysis/criteria/gdpr_scoring_criteria.toml")
        if not criteria_path.exists():
            raise FileNotFoundError(
                f"GDPR scoring criteria not found at: {criteria_path}"
            )
        return toml.load(criteria_path)

    def score_policy(
        self,
        policy_text: str,
        graphml_graph: nx.DiGraph | None = None,
        yaml_graph: nx.MultiDiGraph | None = None,
    ) -> dict[str, Any]:
        if graphml_graph is None and yaml_graph is None:
            return self._create_error_result("Missing graph artifacts for GDPR scoring")

        try:
            if graphml_graph is None and yaml_graph is not None:
                graphml_graph = self._graph_from_yaml(yaml_graph)
            if yaml_graph is None and graphml_graph is not None:
                yaml_graph = self._graphml_to_multidigraph(graphml_graph)

            text = self._normalize_text(policy_text or self._graph_text(yaml_graph))
            features = self.extract_features(text, graphml_graph, yaml_graph)
            preliminary_score = self._compute_composite_score(features)
            features["preliminary_score"] = preliminary_score

            violations: list[dict[str, Any]] = []
            for detector in (
                self._detect_rq1_disclosure,
                self._detect_rq2_structural,
                self._detect_rq3_compliance,
                self._detect_rq4_third_party,
                self._detect_rq5_contradictions,
            ):
                violations.extend(detector(features))

            violations.extend(
                self._detect_rq6_risk(
                    features,
                    violations,
                    preliminary_score,
                )
            )

            violations.sort(
                key=lambda item: (
                    self._severity_rank(item["severity"]),
                    item["code"],
                )
            )

            severity_counts = Counter(v["severity"] for v in violations)
            normalized_score = self._compute_composite_score(features)
            total_score = round(normalized_score * 100.0, 1)
            tier = self._classify_tier(normalized_score)
            flags = self._build_risk_flags(features, severity_counts)
            grouped = self._group_violations_by_rq(violations)

            result = {
                "success": True,
                "total_score": total_score,
                "normalized_score": round(normalized_score, 3),
                "tier": tier,
                "grade": tier,
                "component_scores": self._component_scores(features),
                "severity_counts": {
                    "CRITICAL": severity_counts.get("CRITICAL", 0),
                    "HIGH": severity_counts.get("HIGH", 0),
                    "MEDIUM": severity_counts.get("MEDIUM", 0),
                },
                "flags": flags,
                "violations": violations,
                "violations_by_rq": grouped,
                "summary": self._generate_summary(tier, normalized_score, severity_counts),
                "feedback": self._generate_feedback(violations, flags, features),
                "feature_summary": self._feature_summary(features),
                "scope_counts": Counter(v["scope"] for v in violations),
            }
            return result
        except Exception as exc:
            return self._create_error_result(f"Error scoring policy: {exc}")

    def extract_features(
        self,
        policy_text: str,
        graphml_graph: nx.DiGraph,
        yaml_graph: nx.MultiDiGraph,
    ) -> dict[str, Any]:
        simple_graph = self._simple_graph(graphml_graph)
        text = self._normalize_text(policy_text)
        text_features = self._extract_text_features(text)
        collect_edges = self._collect_edges(yaml_graph)
        subsum_edges = self._subsum_edges(yaml_graph)
        data_nodes = [
            node
            for node, data in graphml_graph.nodes(data=True)
            if data.get("type") == "DATA"
        ]
        actor_nodes = [
            node
            for node, data in graphml_graph.nodes(data=True)
            if data.get("type") == "ACTOR"
        ]

        first_party_actors = self._first_party_actors(yaml_graph, actor_nodes)
        third_party_actors = [
            actor
            for actor in actor_nodes
            if actor not in first_party_actors and actor != "UNSPECIFIED_ACTOR"
        ]
        specific_third_parties = [
            actor for actor in third_party_actors if not self._is_generic_actor(actor)
        ]
        generic_third_parties = [
            actor for actor in third_party_actors if self._is_generic_actor(actor)
        ]

        node_count = simple_graph.number_of_nodes()
        edge_count = simple_graph.number_of_edges()
        density = nx.density(simple_graph) if node_count > 1 else 0.0
        components = list(nx.connected_components(simple_graph)) if node_count else []
        component_count = len(components)
        largest_component_ratio = (
            max((len(component) for component in components), default=0) / node_count
            if node_count
            else 0.0
        )
        clustering = (
            nx.average_clustering(simple_graph)
            if node_count > 1 and edge_count > 0
            else 0.0
        )
        betweenness = (
            nx.betweenness_centrality(simple_graph)
            if node_count > 2 and edge_count > 0
            else {}
        )
        max_centrality = max(betweenness.values(), default=0.0)
        degrees = [degree for _, degree in simple_graph.degree()]
        degree_variance = self._variance(degrees)

        collect_edge_count = len(collect_edges)
        subsum_edge_count = len(subsum_edges)
        purposeful_collect_edges = sum(
            1 for _, _, _, data in collect_edges if data.get("purposes")
        )
        purpose_labels = sorted(
            {
                purpose
                for _, _, _, data in collect_edges
                for purpose in (data.get("purposes") or {})
            }
        )

        modal_terms = self._terms("lists", "modal_terms")
        vague_terms = self._terms("lists", "vague_terms")
        modal_count = sum(text.count(term) for term in modal_terms)
        vague_count = sum(text.count(term) for term in vague_terms)
        token_count = max(text_features["n_words"], 1)
        vagueness_ratio = vague_count / token_count
        purpose_attribution_ratio = (
            purposeful_collect_edges / collect_edge_count if collect_edge_count else 0.0
        )
        edge_node_ratio = edge_count / node_count if node_count else 0.0
        data_entity_ratio = len(data_nodes) / max(len(actor_nodes), 1)
        collection_intensity = collect_edge_count / edge_count if edge_count else 0.0
        orphan_data_nodes = sum(
            1
            for node in data_nodes
            if simple_graph.degree(node) == 0 or node == "UNSPECIFIED_DATA"
        )
        ambiguous_entity_ratio = (
            len(generic_third_parties) / len(third_party_actors)
            if third_party_actors
            else 0.0
        )

        coverage = self._category_coverage(
            text,
            yaml_graph,
            actor_nodes,
            data_nodes,
            third_party_actors,
            specific_third_parties,
            purposeful_collect_edges,
        )
        coverage_ratio = sum(1 for present in coverage.values() if present) / max(
            len(coverage), 1
        )

        special_category_nodes = [
            node
            for node in data_nodes
            if any(term in node.lower() for term in self._terms("lists", "special_category_terms"))
        ]
        processor_like_actors = [
            actor
            for actor in actor_nodes
            if any(term in actor.lower() for term in self._terms("lists", "processor_terms"))
        ]
        transfer_jurisdiction_mentions = self._count_keyword_hits(
            text,
            self._terms("lists", "jurisdiction_terms"),
        )
        tracking_present = self._has_tracking_indicator(text, data_nodes, purpose_labels)
        advertising_present = self._has_advertising_indicator(text, purpose_labels)
        consent_present = self._contains_any(text, self._terms("keywords", "consent"))
        opt_out_present = self._contains_any(text, self._terms("keywords", "opt_out"))
        withdrawal_present = self._contains_any(
            text,
            self._terms("keywords", "withdrawal"),
        )
        deletion_present = self._contains_any(text, self._terms("keywords", "deletion"))
        minimization_claim = self._contains_any(
            text,
            self._terms("keywords", "minimization_claim"),
        )
        collection_denial_claim = self._contains_any(
            text,
            self._terms("keywords", "collection_denial"),
        )
        claims_no_share = self._matches_regex_group(text, "claims_no_share")
        mentions_sharing = self._matches_regex_group(text, "mentions_sharing")
        claims_no_sell = self._matches_regex_group(text, "claims_no_sell")
        sharing_denial_claim = claims_no_share or self._contains_any(
            text,
            self._terms("keywords", "sharing_denial"),
        )
        sale_disclosure_present = self._contains_any(
            text,
            self._terms("keywords", "sale"),
        )
        legitimate_interest_present = self._contains_any(
            text,
            self._terms("keywords", "legitimate_interest"),
        )
        balancing_test_present = self._contains_any(
            text,
            self._terms("keywords", "balancing_test"),
        )
        contract_basis_present = self._contains_any(
            text,
            self._terms("keywords", "contract_basis"),
        )
        explicit_consent_present = self._contains_any(
            text,
            self._terms("keywords", "explicit_consent"),
        )
        article_9_exception_present = self._contains_any(
            text,
            self._terms("keywords", "article_9_exception"),
        )
        dpia_present = self._contains_any(text, self._terms("keywords", "dpia"))
        joint_controller_present = self._contains_any(
            text,
            self._terms("keywords", "joint_controller"),
        )
        human_oversight_present = self._contains_any(
            text,
            self._terms("keywords", "human_oversight"),
        )
        response_timeframe_present = bool(
            re.search(self.rules.get("regex", {}).get("response_timeframe", ""), text)
        )
        bunded_consent_present = self._contains_any(
            text,
            self._terms("keywords", "bundled_consent"),
        )
        privacy_by_design_present = self._contains_any(
            text,
            self._terms("keywords", "privacy_by_design"),
        )
        privacy_by_default_present = self._contains_any(
            text,
            self._terms("keywords", "privacy_by_default"),
        )
        transfer_mechanism_present = self._contains_any(
            text,
            self._terms("keywords", "transfer_mechanism"),
        )
        data_broker_present = self._contains_any(
            text,
            self._terms("keywords", "data_broker"),
        )
        subprocessor_present = self._contains_any(
            text,
            self._terms("keywords", "subprocessor"),
        )
        ccpa_categories = (
            "right_to_know",
            "opt_out",
            "right_to_delete",
            "do_not_sell_link",
            "ccpa_categories",
        )
        ccpa_found = {
            category: self._matches_regex_group(text, category)
            for category in ccpa_categories
        }
        ccpa_coverage = sum(1 for found in ccpa_found.values() if found) / max(
            len(ccpa_found),
            1,
        )

        return {
            "policy_text": text,
            "simple_graph": simple_graph,
            "graphml_graph": graphml_graph,
            "yaml_graph": yaml_graph,
            "data_nodes": data_nodes,
            "actor_nodes": actor_nodes,
            "first_party_actors": first_party_actors,
            "third_party_actors": third_party_actors,
            "specific_third_parties": specific_third_parties,
            "generic_third_parties": generic_third_parties,
            "processor_like_actors": processor_like_actors,
            "special_category_nodes": special_category_nodes,
            "purpose_labels": purpose_labels,
            "node_count": node_count,
            "edge_count": edge_count,
            "density": density,
            "component_count": component_count,
            "largest_component_ratio": largest_component_ratio,
            "clustering": clustering,
            "max_centrality": max_centrality,
            "degree_variance": degree_variance,
            "collect_edge_count": collect_edge_count,
            "subsum_edge_count": subsum_edge_count,
            "purposeful_collect_edges": purposeful_collect_edges,
            "purpose_attribution_ratio": purpose_attribution_ratio,
            "n_words": text_features["n_words"],
            "n_sentences": text_features["n_sentences"],
            "avg_sentence_length": text_features["avg_sentence_length"],
            "flesch_kincaid": text_features["flesch_kincaid"],
            "gunning_fog": text_features["gunning_fog"],
            "flesch_reading_ease": text_features["flesch_reading_ease"],
            "passive_count": text_features["passive_count"],
            "passive_ratio": text_features["passive_ratio"],
            "vagueness_ratio": vagueness_ratio,
            "modal_term_count": modal_count,
            "edge_node_ratio": edge_node_ratio,
            "data_entity_ratio": data_entity_ratio,
            "collection_intensity": collection_intensity,
            "orphan_data_nodes": orphan_data_nodes,
            "ambiguous_entity_ratio": ambiguous_entity_ratio,
            "specificity_ratio": (
                len(specific_third_parties) / len(third_party_actors)
                if third_party_actors
                else 0.0
            ),
            "coverage": coverage,
            "coverage_ratio": coverage_ratio,
            "tracking_present": tracking_present,
            "advertising_present": advertising_present,
            "consent_present": consent_present,
            "opt_out_present": opt_out_present,
            "withdrawal_present": withdrawal_present,
            "deletion_present": deletion_present,
            "minimization_claim": minimization_claim,
            "collection_denial_claim": collection_denial_claim,
            "claims_no_share": claims_no_share,
            "mentions_sharing": mentions_sharing,
            "claims_no_sell": claims_no_sell,
            "sharing_denial_claim": sharing_denial_claim,
            "sale_disclosure_present": sale_disclosure_present,
            "legitimate_interest_present": legitimate_interest_present,
            "balancing_test_present": balancing_test_present,
            "contract_basis_present": contract_basis_present,
            "explicit_consent_present": explicit_consent_present,
            "article_9_exception_present": article_9_exception_present,
            "dpia_present": dpia_present,
            "joint_controller_present": joint_controller_present,
            "human_oversight_present": human_oversight_present,
            "response_timeframe_present": response_timeframe_present,
            "bundled_consent_present": bunded_consent_present,
            "privacy_by_design_present": privacy_by_design_present,
            "privacy_by_default_present": privacy_by_default_present,
            "transfer_mechanism_present": transfer_mechanism_present,
            "data_broker_present": data_broker_present,
            "subprocessor_present": subprocessor_present,
            "transfer_jurisdiction_mentions": transfer_jurisdiction_mentions,
            "ccpa_found": ccpa_found,
            "ccpa_coverage": ccpa_coverage,
        }

    def _detect_rq1_disclosure(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        coverage = features["coverage"]
        violations: list[dict[str, Any]] = []
        self._maybe_add(
            violations,
            not coverage["controller"],
            "V01",
            "No controller identity disclosure detected",
        )
        self._maybe_add(
            violations,
            not coverage["dpo"],
            "V02",
            "No DPO or privacy contact disclosure detected",
        )
        self._maybe_add(
            violations,
            not coverage["purposes"],
            "V03",
            "Processing purposes are not clearly disclosed",
        )
        self._maybe_add(
            violations,
            not coverage["basis"],
            "V04",
            "No lawful basis language detected",
        )
        self._maybe_add(
            violations,
            (not coverage["recipients"]) or features["specificity_ratio"] < 0.5,
            "V05",
            f"Recipient disclosure is missing or vague (specificity={features['specificity_ratio']:.2f})",
        )
        self._maybe_add(
            violations,
            not coverage["transfers"],
            "V06",
            "No international transfer disclosure detected",
        )
        self._maybe_add(
            violations,
            not coverage["retention"],
            "V07",
            "No retention period language detected",
        )
        self._maybe_add(
            violations,
            not coverage["rights"],
            "V08",
            "Data subject rights are not clearly disclosed",
        )
        self._maybe_add(
            violations,
            not coverage["adm"],
            "V09",
            "Automated decision-making or profiling disclosure is missing",
        )
        self._maybe_add(
            violations,
            not coverage["data_categories"],
            "V10",
            "Data categories are not clearly enumerated",
        )
        self._maybe_add(
            violations,
            features["vagueness_ratio"] > self._threshold("vagueness_warning"),
            "V11",
            f"Vagueness ratio is high at {features['vagueness_ratio']:.2%}",
        )
        self._maybe_add(
            violations,
            features["purpose_attribution_ratio"]
            < self._threshold("purpose_attribution_warning"),
            "V12",
            f"Purpose attribution ratio is low at {features['purpose_attribution_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            bool(features["special_category_nodes"])
            and not (
                features["explicit_consent_present"]
                or features["article_9_exception_present"]
            ),
            "V13",
            "Special category data appears without explicit safeguards or Art. 9 exceptions",
        )
        return violations

    def _detect_rq2_structural(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        density = features["density"]
        self._maybe_add(
            violations,
            density < self._threshold("density_critical"),
            "S01",
            f"Graph density is critically low at {density:.3f}",
        )
        self._maybe_add(
            violations,
            self._threshold("density_critical") <= density < self._threshold("density_warning"),
            "S02",
            f"Graph density is below the warning threshold at {density:.3f}",
        )
        self._maybe_add(
            violations,
            features["component_count"] > self._threshold("components_high"),
            "S03",
            f"Graph has {features['component_count']} connected components",
        )
        self._maybe_add(
            violations,
            features["largest_component_ratio"] < self._threshold("largest_component_warning"),
            "S04",
            f"Largest component coverage is only {features['largest_component_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            features["collection_intensity"] > self._threshold("collection_intensity_high"),
            "S05",
            f"Collection intensity is high at {features['collection_intensity']:.2f}",
        )
        self._maybe_add(
            violations,
            features["data_entity_ratio"] > self._threshold("data_entity_ratio_high"),
            "S06",
            f"Data-to-entity ratio is high at {features['data_entity_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            features["clustering"] < self._threshold("clustering_low"),
            "S07",
            f"Average clustering is low at {features['clustering']:.2f}",
        )
        self._maybe_add(
            violations,
            features["max_centrality"] > self._threshold("centrality_high"),
            "S08",
            f"Max betweenness centrality is high at {features['max_centrality']:.2f}",
        )
        self._maybe_add(
            violations,
            features["collect_edge_count"] == 0,
            "S09",
            "No COLLECT edges were found in the graph",
        )
        self._maybe_add(
            violations,
            len(features["data_nodes"]) > self._threshold("data_nodes_high"),
            "S10",
            f"Graph contains {len(features['data_nodes'])} data nodes",
        )
        self._maybe_add(
            violations,
            features["node_count"] < self._threshold("node_count_min"),
            "S11",
            f"Graph contains only {features['node_count']} nodes",
        )
        self._maybe_add(
            violations,
            features["degree_variance"] < self._threshold("degree_variance_low"),
            "S12",
            f"Degree variance is low at {features['degree_variance']:.2f}",
        )
        self._maybe_add(
            violations,
            features["subsum_edge_count"] == 0,
            "S13",
            "No SUBSUM hierarchy edges were found in the graph",
        )
        self._maybe_add(
            violations,
            features["edge_node_ratio"] > self._threshold("edge_node_ratio_high"),
            "S14",
            f"Edge-to-node ratio is high at {features['edge_node_ratio']:.2f}",
        )
        return violations

    def _detect_rq3_compliance(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        coverage = features["coverage"]
        self._maybe_add(
            violations,
            not coverage["basis"],
            "C01",
            "No lawful basis disclosure detected",
        )
        self._maybe_add(
            violations,
            features["collect_edge_count"] > 0 and not features["consent_present"],
            "C02",
            "Collection is disclosed without a clear consent mechanism",
        )
        self._maybe_add(
            violations,
            features["advertising_present"]
            and features["contract_basis_present"]
            and not features["consent_present"],
            "C03",
            "Advertising-related processing appears to rely on contract basis without consent",
        )
        self._maybe_add(
            violations,
            features["advertising_present"]
            and features["legitimate_interest_present"]
            and not features["balancing_test_present"],
            "C04",
            "Legitimate-interest language appears without balancing-test disclosure",
        )
        self._maybe_add(
            violations,
            bool(features["special_category_nodes"])
            and not features["explicit_consent_present"],
            "C05",
            "Special category data appears without explicit consent language",
        )
        self._maybe_add(
            violations,
            bool(features["special_category_nodes"])
            and not features["article_9_exception_present"],
            "C06",
            "Special category processing lacks an Art. 9 exception reference",
        )
        self._maybe_add(
            violations,
            not features["withdrawal_present"],
            "C07",
            "No consent withdrawal mechanism was detected",
        )
        self._maybe_add(
            violations,
            features["bundled_consent_present"],
            "C08",
            "Consent appears bundled with service access or continued use",
        )
        self._maybe_add(
            violations,
            len(features["data_nodes"]) > self._threshold("data_nodes_excessive")
            and features["purpose_attribution_ratio"]
            < self._threshold("purpose_attribution_warning"),
            "C09",
            "High data volume appears without proportional purpose disclosure",
        )
        self._maybe_add(
            violations,
            not coverage["retention"],
            "C10",
            "Retention or storage limitation language is missing",
        )
        self._maybe_add(
            violations,
            features["preliminary_score"] < self._threshold("component_floor"),
            "C11",
            f"Composite accountability score is low at {features['preliminary_score']:.2f}",
        )
        self._maybe_add(
            violations,
            bool(features["special_category_nodes"])
            and features["coverage_ratio"] < self._threshold("coverage_critical"),
            "C12",
            "Sensitive processing appears with weak overall coverage",
        )
        self._maybe_add(
            violations,
            bool(features["special_category_nodes"]) and not features["dpia_present"],
            "C13",
            "Sensitive processing appears without a DPIA or equivalent disclosure",
        )
        self._maybe_add(
            violations,
            bool(features["third_party_actors"]) and not features["transfer_mechanism_present"],
            "C14",
            "Third-party or cross-border sharing appears without a transfer mechanism",
        )
        self._maybe_add(
            violations,
            not coverage["data_categories"],
            "C15",
            "Data categories at collection are not clearly disclosed",
        )
        self._maybe_add(
            violations,
            features["advertising_present"] and not features["opt_out_present"],
            "C16",
            "Advertising-related processing appears without an opt-out mechanism",
        )
        self._maybe_add(
            violations,
            coverage["adm"] and not features["human_oversight_present"],
            "C17",
            "Automated decision-making is mentioned without human oversight language",
        )
        self._maybe_add(
            violations,
            not features["response_timeframe_present"],
            "C18",
            "No response timeframe for rights requests was detected",
        )
        return violations

    def _detect_rq4_third_party(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        tp_count = len(features["third_party_actors"])
        specific_count = len(features["specific_third_parties"])
        specificity = features["specificity_ratio"]
        self._maybe_add(
            violations,
            specific_count == 0,
            "T01",
            "No specific third parties were identified in the graph",
        )
        self._maybe_add(
            violations,
            tp_count > 0 and specificity < self._threshold("specificity_warning"),
            "T02",
            f"Third-party specificity ratio is low at {specificity:.2f}",
        )
        self._maybe_add(
            violations,
            tp_count > 0 and specific_count == 0 and len(features["generic_third_parties"]) > 0,
            "T03",
            "Only generic third-party labels were identified",
        )
        self._maybe_add(
            violations,
            len(features["generic_third_parties"]) > self._threshold("generic_reference_count_high"),
            "T04",
            f"Found {len(features['generic_third_parties'])} generic third-party references",
        )
        self._maybe_add(
            violations,
            features["advertising_present"]
            and not any(
                "advert" in actor.lower() or "market" in actor.lower()
                for actor in features["specific_third_parties"]
            ),
            "T05",
            "Advertising-related sharing appears without named advertising recipients",
        )
        self._maybe_add(
            violations,
            features["tracking_present"] and not features["specific_third_parties"],
            "T06",
            "Tracking or analytics is present without clear recipient disclosure",
        )
        self._maybe_add(
            violations,
            not features["processor_like_actors"],
            "T07",
            "No processor, service-provider, or cloud-provider actor was identified",
        )
        self._maybe_add(
            violations,
            tp_count > 0 and not features["coverage"]["transfers"],
            "T08",
            "Third-party sharing appears without transfer disclosure",
        )
        self._maybe_add(
            violations,
            tp_count > self._threshold("joint_controller_actor_count")
            and not features["joint_controller_present"],
            "T09",
            "Multiple recipient actors appear without joint-controller language",
        )
        self._maybe_add(
            violations,
            tp_count == 0,
            "T10",
            "No categories of third parties were identified",
        )
        self._maybe_add(
            violations,
            tp_count > 0 and not features["processor_like_actors"],
            "T11",
            "Service-provider or processor distinctions are unclear",
        )
        self._maybe_add(
            violations,
            tp_count > 0
            and features["purpose_attribution_ratio"]
            < self._threshold("purpose_attribution_warning"),
            "T12",
            "Third-party sharing appears without sufficient purpose linkage",
        )
        self._maybe_add(
            violations,
            tp_count > self._threshold("third_party_entity_count_high")
            and specificity < self._threshold("specificity_warning"),
            "T13",
            "Many recipient entities are disclosed with low specificity",
        )
        self._maybe_add(
            violations,
            features["data_broker_present"] and specific_count == 0,
            "T14",
            "Data-broker indicators appear without named broker disclosure",
        )
        self._maybe_add(
            violations,
            len(features["processor_like_actors"]) > 1 and not features["subprocessor_present"],
            "T15",
            "Multiple processor-like actors appear without sub-processor language",
        )
        self._maybe_add(
            violations,
            features["coverage"]["transfers"]
            and features["transfer_jurisdiction_mentions"] == 0,
            "T16",
            "Transfer recipients or jurisdictions are unclear",
        )
        return violations

    def _detect_rq5_contradictions(self, features: dict[str, Any]) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        self._maybe_add(
            violations,
            features["vagueness_ratio"] > self._threshold("vagueness_warning"),
            "X01",
            f"Vagueness ratio exceeds warning threshold at {features['vagueness_ratio']:.2%}",
        )
        self._maybe_add(
            violations,
            features["vagueness_ratio"] > self._threshold("vagueness_critical"),
            "X02",
            f"Vagueness ratio exceeds critical threshold at {features['vagueness_ratio']:.2%}",
        )
        self._maybe_add(
            violations,
            features["modal_term_count"] > self._threshold("modal_term_count_high"),
            "X03",
            f"Detected {features['modal_term_count']} modal uncertainty terms",
        )
        self._maybe_add(
            violations,
            features["collection_denial_claim"] and features["collect_edge_count"] > 0,
            "X04",
            "Policy claims not to collect while the graph still shows collection edges",
        )
        self._maybe_add(
            violations,
            features["sharing_denial_claim"] and len(features["third_party_actors"]) > 0,
            "X05",
            "Policy claims not to share while third-party collection paths are present",
        )
        self._maybe_add(
            violations,
            features["collect_edge_count"] > 0 and not features["coverage"]["purposes"],
            "X06",
            "Data collection is disclosed without corresponding purpose statements",
        )
        self._maybe_add(
            violations,
            features["purpose_attribution_ratio"]
            < self._threshold("purpose_attribution_warning"),
            "X07",
            f"Purpose attribution ratio is low at {features['purpose_attribution_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            features["purpose_attribution_ratio"]
            < self._threshold("purpose_attribution_critical"),
            "X08",
            f"Purpose attribution ratio is critically low at {features['purpose_attribution_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            len(features["third_party_actors"]) > self._threshold("recipient_count_mismatch")
            and not features["coverage"]["recipients"],
            "X09",
            "The graph contains many recipient actors without recipient disclosure text",
        )
        self._maybe_add(
            violations,
            features["minimization_claim"]
            and len(features["data_nodes"]) > self._threshold("data_nodes_excessive"),
            "X10",
            "Policy claims data minimization while the graph shows broad data collection",
        )
        self._maybe_add(
            violations,
            features["collect_edge_count"] > 0 and not features["consent_present"],
            "X11",
            "Collection appears without a corresponding consent mechanism",
        )
        self._maybe_add(
            violations,
            features["deletion_present"] and not features["coverage"]["retention"],
            "X12",
            "Deletion rights are disclosed without a retention policy",
        )
        self._maybe_add(
            violations,
            bool(features["special_category_nodes"])
            and features["coverage_ratio"] < self._threshold("coverage_critical"),
            "X13",
            "Sensitive data appears alongside weak coverage and safeguards",
        )
        self._maybe_add(
            violations,
            features["advertising_present"] and not features["sale_disclosure_present"],
            "X14",
            "Advertising indicators appear without sale or sharing disclosure",
        )
        self._maybe_add(
            violations,
            features["orphan_data_nodes"] > 0,
            "X15",
            f"Found {features['orphan_data_nodes']} orphan data nodes",
        )
        self._maybe_add(
            violations,
            features["component_count"] > 3
            and features["largest_component_ratio"] < self._threshold("coverage_warning"),
            "X16",
            "Graph fragmentation suggests circular or disconnected definitions",
        )
        self._maybe_add(
            violations,
            features["ambiguous_entity_ratio"] > self._threshold("ambiguous_entity_ratio_high"),
            "X17",
            f"Ambiguous entity ratio is high at {features['ambiguous_entity_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            features["tracking_present"] and not features["coverage"]["adm"],
            "X18",
            "Tracking indicators appear without profiling or ADM disclosure",
        )
        return violations

    def _detect_rq6_risk(
        self,
        features: dict[str, Any],
        prior_violations: list[dict[str, Any]],
        normalized_score: float,
    ) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []
        severity_counts = Counter(v["severity"] for v in prior_violations)
        rq_presence = {v["rq"] for v in prior_violations}
        component_scores = self._component_scores(features)

        self._maybe_add(
            violations,
            normalized_score < self._threshold("score_critical"),
            "R01",
            f"Composite score is critically low at {normalized_score:.2f}",
        )
        self._maybe_add(
            violations,
            self._threshold("score_critical")
            <= normalized_score
            < self._threshold("score_warning"),
            "R02",
            f"Composite score is in the warning band at {normalized_score:.2f}",
        )
        self._maybe_add(
            violations,
            features["coverage_ratio"] < self._threshold("coverage_critical"),
            "R03",
            f"Coverage ratio is below 50% at {features['coverage_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            self._threshold("coverage_critical")
            <= features["coverage_ratio"]
            < self._threshold("coverage_warning"),
            "R04",
            f"Coverage ratio remains in the warning band at {features['coverage_ratio']:.2f}",
        )
        self._maybe_add(
            violations,
            features["density"] < self._threshold("density_critical"),
            "R05",
            f"Density is critically low at {features['density']:.3f}",
        )
        self._maybe_add(
            violations,
            self._threshold("density_critical")
            <= features["density"]
            < self._threshold("density_warning"),
            "R06",
            f"Density remains in the warning band at {features['density']:.3f}",
        )
        self._maybe_add(
            violations,
            component_scores["transparency"]["score"] < self._threshold("score_critical"),
            "R07",
            f"Transparency score is low at {component_scores['transparency']['score']:.2f}",
        )
        self._maybe_add(
            violations,
            component_scores["clarity"]["score"] < self._threshold("clarity_warning"),
            "R08",
            f"Clarity score is low at {component_scores['clarity']['score']:.2f}",
        )

        component_failures = sum(
            1
            for key, score in (
                ("coverage", component_scores["coverage"]["score"]),
                ("density", component_scores["density"]["score"]),
                ("transparency", component_scores["transparency"]["score"]),
                ("clarity", component_scores["clarity"]["score"]),
            )
            if score < self._threshold("component_floor")
        )
        self._maybe_add(
            violations,
            component_failures >= self._threshold("compound_flag_count"),
            "R09",
            f"{component_failures} component-level risk flags were triggered",
        )
        self._maybe_add(
            violations,
            severity_counts.get("CRITICAL", 0) >= self._threshold("critical_violation_count"),
            "R10",
            f"{severity_counts.get('CRITICAL', 0)} critical violations were triggered",
        )
        self._maybe_add(
            violations,
            severity_counts.get("HIGH", 0) >= self._threshold("high_violation_count"),
            "R11",
            f"{severity_counts.get('HIGH', 0)} high-severity violations were triggered",
        )
        self._maybe_add(
            violations,
            features["max_centrality"] > self._threshold("centrality_high")
            and features["coverage_ratio"] < self._threshold("coverage_critical"),
            "R12",
            "A dominant central node appears together with low disclosure coverage",
        )
        self._maybe_add(
            violations,
            features["component_count"] > 1
            and features["largest_component_ratio"] < self._threshold("largest_component_warning"),
            "R13",
            "Multiple disconnected components appear with weak largest-component coverage",
        )
        self._maybe_add(
            violations,
            len(features["data_nodes"]) > self._threshold("data_nodes_excessive")
            and features["edge_node_ratio"] < self._threshold("edge_node_ratio_low"),
            "R14",
            "Data-node volume appears high relative to the graph's edge disclosure",
        )
        self._maybe_add(
            violations,
            all(
                component_scores[name]["score"] < self._threshold("component_floor")
                for name in ("coverage", "density", "transparency", "clarity")
            ),
            "R15",
            "All composite score components fall below the accountability floor",
        )
        self._maybe_add(
            violations,
            all(rq in rq_presence for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5")),
            "R16",
            "Violations span all five primary research-question groups",
        )
        return violations

    def _component_scores(self, features: dict[str, Any]) -> dict[str, dict[str, float]]:
        coverage_score = features["coverage_ratio"]
        density_score = min(
            features["density"] / max(self._threshold("density_target"), 1e-9),
            1.0,
        )
        transparency_score = features["specificity_ratio"]
        clarity_score = max(0.0, 1.0 - features["vagueness_ratio"])

        weights = self.rules.get("weights", {})
        return {
            "coverage": {
                "score": round(coverage_score, 3),
                "weight": float(weights.get("coverage", 0.30)),
            },
            "density": {
                "score": round(density_score, 3),
                "weight": float(weights.get("density", 0.20)),
            },
            "transparency": {
                "score": round(transparency_score, 3),
                "weight": float(weights.get("transparency", 0.25)),
            },
            "clarity": {
                "score": round(clarity_score, 3),
                "weight": float(weights.get("clarity", 0.25)),
            },
        }

    def _compute_composite_score(self, features: dict[str, Any]) -> float:
        components = self._component_scores(features)
        score = sum(component["score"] * component["weight"] for component in components.values())
        return min(max(score, 0.0), 1.0)

    def _classify_tier(self, normalized_score: float) -> str:
        tiers = self.rules.get("tiers", {})
        if normalized_score >= float(tiers.get("compliant", 0.70)):
            return "COMPLIANT"
        if normalized_score >= float(tiers.get("warning", 0.50)):
            return "WARNING"
        return "NON-COMPLIANT"

    def _group_violations_by_rq(self, violations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for violation in violations:
            grouped[violation["rq"]].append(violation)
        return {
            rq: grouped.get(rq, [])
            for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6")
        }

    def _build_risk_flags(
        self,
        features: dict[str, Any],
        severity_counts: Counter,
    ) -> list[str]:
        flags: list[str] = []
        if features["coverage_ratio"] < self._threshold("coverage_warning"):
            flags.append("LOW COVERAGE")
        if features["density"] < self._threshold("density_warning"):
            flags.append("SPARSE GRAPH")
        if features["specificity_ratio"] < self._threshold("specificity_warning"):
            flags.append("VAGUE RECIPIENTS")
        if features["vagueness_ratio"] > self._threshold("vagueness_warning"):
            flags.append("LOW CLARITY")
        if features["purpose_attribution_ratio"] < self._threshold("purpose_attribution_warning"):
            flags.append("LOW PURPOSE ATTRIBUTION")
        if severity_counts.get("CRITICAL", 0) >= self._threshold("critical_violation_count"):
            flags.append("CRITICAL VIOLATION LOAD")
        return flags

    def _feature_summary(self, features: dict[str, Any]) -> dict[str, Any]:
        return {
            "node_count": features["node_count"],
            "edge_count": features["edge_count"],
            "n_words": features["n_words"],
            "n_sentences": features["n_sentences"],
            "avg_sentence_length": round(features["avg_sentence_length"], 2),
            "density": round(features["density"], 3),
            "coverage_ratio": round(features["coverage_ratio"], 3),
            "ccpa_coverage": round(features["ccpa_coverage"], 3),
            "specificity_ratio": round(features["specificity_ratio"], 3),
            "vagueness_ratio": round(features["vagueness_ratio"], 3),
            "passive_ratio": round(features["passive_ratio"], 3),
            "flesch_kincaid": round(features["flesch_kincaid"], 2),
            "gunning_fog": round(features["gunning_fog"], 2),
            "flesch_reading_ease": round(features["flesch_reading_ease"], 2),
            "purpose_attribution_ratio": round(features["purpose_attribution_ratio"], 3),
            "component_count": features["component_count"],
            "largest_component_ratio": round(features["largest_component_ratio"], 3),
            "third_party_actor_count": len(features["third_party_actors"]),
            "special_category_count": len(features["special_category_nodes"]),
        }

    def _generate_summary(
        self,
        tier: str,
        normalized_score: float,
        severity_counts: Counter,
    ) -> str:
        critical = severity_counts.get("CRITICAL", 0)
        high = severity_counts.get("HIGH", 0)
        if tier == "COMPLIANT":
            return (
                f"Composite GDPR score is {normalized_score:.2f}. "
                f"The policy is classified as COMPLIANT with {critical} critical and {high} high-severity findings."
            )
        if tier == "WARNING":
            return (
                f"Composite GDPR score is {normalized_score:.2f}. "
                f"The policy is classified as WARNING due to elevated disclosure or structural risk."
            )
        return (
            f"Composite GDPR score is {normalized_score:.2f}. "
            f"The policy is classified as NON-COMPLIANT with material enforcement-risk indicators."
        )

    def _generate_feedback(
        self,
        violations: list[dict[str, Any]],
        flags: list[str],
        features: dict[str, Any],
    ) -> list[str]:
        feedback = [f"Flag: {flag}" for flag in flags]
        for violation in violations[:10]:
            feedback.append(f"{violation['code']}: {violation['detail']}")
        if not feedback:
            feedback.append(
                f"No material GDPR violations were detected. Coverage ratio: {features['coverage_ratio']:.2f}."
            )
        return feedback

    def _create_error_result(self, error_message: str) -> dict[str, Any]:
        return {
            "success": False,
            "total_score": 0.0,
            "normalized_score": 0.0,
            "tier": "NON-COMPLIANT",
            "grade": "NON-COMPLIANT",
            "component_scores": {},
            "severity_counts": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0},
            "flags": [],
            "violations": [],
            "violations_by_rq": {rq: [] for rq in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6")},
            "summary": "Unable to evaluate GDPR compliance",
            "feedback": [error_message],
            "feature_summary": {},
            "scope_counts": {},
        }

    def _category_coverage(
        self,
        text: str,
        yaml_graph: nx.MultiDiGraph,
        actor_nodes: list[str],
        data_nodes: list[str],
        third_party_actors: list[str],
        specific_third_parties: list[str],
        purposeful_collect_edges: int,
    ) -> dict[str, bool]:
        return {
            "controller": bool(actor_nodes) and self._contains_any(text, self._terms("keywords", "controller")),
            "dpo": self._contains_any(text, self._terms("keywords", "dpo")),
            "purposes": purposeful_collect_edges > 0
            or self._contains_any(text, self._terms("keywords", "purposes")),
            "basis": self._contains_any(text, self._terms("keywords", "lawful_basis")),
            "recipients": bool(third_party_actors)
            or self._contains_any(text, self._terms("keywords", "recipients")),
            "transfers": self._contains_any(text, self._terms("keywords", "transfers")),
            "retention": self._contains_any(text, self._terms("keywords", "retention")),
            "rights": self._contains_any(text, self._terms("keywords", "rights")),
            "adm": self._contains_any(text, self._terms("keywords", "adm")),
            "data_categories": bool(data_nodes)
            and (
                len(data_nodes) >= self._threshold("data_category_min")
                or self._contains_any(text, self._terms("keywords", "data_categories"))
            ),
        }

    def _first_party_actors(
        self,
        yaml_graph: nx.MultiDiGraph,
        actor_nodes: list[str],
    ) -> set[str]:
        if "we" not in yaml_graph:
            return {"we"} if "we" in actor_nodes else set(actor_nodes[:1])

        first_party = {"we"}
        queue: deque[str] = deque(["we"])
        while queue:
            node = queue.popleft()
            for _, dst, key in yaml_graph.out_edges(node, keys=True):
                if key == "SUBSUM" and yaml_graph.nodes[dst].get("type") == "ACTOR" and dst not in first_party:
                    first_party.add(dst)
                    queue.append(dst)
        return first_party

    def _simple_graph(self, graphml_graph: nx.DiGraph) -> nx.Graph:
        graph = nx.Graph()
        for node, data in graphml_graph.nodes(data=True):
            graph.add_node(node, **data)
        for u, v in graphml_graph.edges():
            if u != v:
                graph.add_edge(u, v)
        return graph

    def _collect_edges(self, yaml_graph: nx.MultiDiGraph) -> list[tuple[str, str, str, dict[str, Any]]]:
        return list(yaml_graph.edges(keys=True, data=True))

    def _subsum_edges(self, yaml_graph: nx.MultiDiGraph) -> list[tuple[str, str, str, dict[str, Any]]]:
        return [
            (u, v, key, data)
            for u, v, key, data in yaml_graph.edges(keys=True, data=True)
            if key == "SUBSUM"
        ]

    def _graph_text(self, yaml_graph: nx.MultiDiGraph | None) -> str:
        if yaml_graph is None:
            return ""
        snippets: list[str] = []
        for _, _, _, data in yaml_graph.edges(keys=True, data=True):
            snippets.extend(data.get("text", []))
        return "\n".join(snippets)

    def _graph_from_yaml(self, yaml_graph: nx.MultiDiGraph) -> nx.DiGraph:
        graph = nx.DiGraph()
        for node, data in yaml_graph.nodes(data=True):
            graph.add_node(node, label=node, type=data.get("type"))
        for u, v, _, data in yaml_graph.edges(keys=True, data=True):
            if not graph.has_edge(u, v):
                graph.add_edge(u, v, relationship=data.get("relationship"))
        return graph

    def _graphml_to_multidigraph(self, graphml_graph: nx.DiGraph) -> nx.MultiDiGraph:
        graph = nx.MultiDiGraph()
        for node, data in graphml_graph.nodes(data=True):
            graph.add_node(node, **data)
        for u, v, data in graphml_graph.edges(data=True):
            relationship = data.get("relationship", "COLLECT")
            graph.add_edge(
                u,
                v,
                key=relationship,
                text=[data.get("text", "")] if data.get("text") else [],
                purposes={},
            )
        return graph

    def _contains_any(self, text: str, phrases: list[str]) -> bool:
        return any(phrase in text for phrase in phrases)

    def _extract_text_features(self, text: str) -> dict[str, Any]:
        tokens = re.findall(r"[a-z0-9']+", text)
        sentences = [
            sentence.strip()
            for sentence in re.split(r"[.!?]+", text)
            if len(sentence.strip()) > 10
        ]
        n_words = len(tokens)
        n_sentences = len(sentences)
        avg_sentence_length = n_words / max(n_sentences, 1)
        passive_count = len(
            re.findall(
                r"\b(?:is|are|was|were|been|be|being)\s+\w+ed\b",
                text,
            )
        )
        passive_ratio = passive_count / max(n_sentences, 1)
        return {
            "tokens": tokens,
            "n_words": n_words,
            "n_sentences": n_sentences,
            "avg_sentence_length": avg_sentence_length,
            "passive_count": passive_count,
            "passive_ratio": passive_ratio,
            **self._readability_metrics(text),
        }

    def _readability_metrics(self, text: str) -> dict[str, float]:
        if textstat is None:
            return {
                "flesch_kincaid": 0.0,
                "gunning_fog": 0.0,
                "flesch_reading_ease": 0.0,
            }
        try:
            return {
                "flesch_kincaid": float(textstat.flesch_kincaid_grade(text)),
                "gunning_fog": float(textstat.gunning_fog(text)),
                "flesch_reading_ease": float(textstat.flesch_reading_ease(text)),
            }
        except Exception:
            return {
                "flesch_kincaid": 0.0,
                "gunning_fog": 0.0,
                "flesch_reading_ease": 0.0,
            }

    def _count_keyword_hits(self, text: str, keywords: list[str]) -> int:
        return sum(1 for keyword in keywords if keyword in text)

    def _matches_regex_group(self, text: str, key: str) -> bool:
        patterns = self.rules.get("regex", {}).get(key, [])
        if isinstance(patterns, str):
            patterns = [patterns]
        return any(re.search(pattern, text) for pattern in patterns)

    def _has_tracking_indicator(
        self,
        text: str,
        data_nodes: list[str],
        purpose_labels: list[str],
    ) -> bool:
        tracking_terms = self._terms("lists", "tracking_terms")
        return (
            any(term in text for term in tracking_terms)
            or any(term in " ".join(data_nodes).lower() for term in tracking_terms)
            or "analytics" in purpose_labels
        )

    def _has_advertising_indicator(self, text: str, purpose_labels: list[str]) -> bool:
        advertising_terms = self._terms("lists", "advertising_terms")
        return any(term in text for term in advertising_terms) or "advertising" in purpose_labels

    def _maybe_add(
        self,
        violations: list[dict[str, Any]],
        condition: bool,
        code: str,
        detail: str,
    ):
        if not condition:
            return
        metadata = dict(self.codes.get(code, {}))
        violation = {
            "code": code,
            "rq": metadata.get("rq", "UNKNOWN"),
            "rq_label": self.research_questions.get(metadata.get("rq", ""), ""),
            "article": metadata.get("article", ""),
            "severity": metadata.get("severity", "MEDIUM"),
            "scope": metadata.get("scope", "GDPR"),
            "description": metadata.get("description", ""),
            "detail": detail,
        }
        violations.append(violation)

    def _severity_rank(self, severity: str) -> int:
        return {
            "CRITICAL": 0,
            "HIGH": 1,
            "MEDIUM": 2,
        }.get(severity, 3)

    def _normalize_text(self, text: str) -> str:
        return " ".join((text or "").lower().split())

    def _terms(self, section: str, key: str) -> list[str]:
        return [term.lower() for term in self.rules.get(section, {}).get(key, [])]

    def _threshold(self, key: str) -> float:
        return float(self.rules.get("thresholds", {}).get(key, 0.0))

    def _is_generic_actor(self, label: str) -> bool:
        normalized = label.lower().strip()
        if normalized == "unspecified_actor":
            return True
        return any(term in normalized for term in self._terms("lists", "generic_actor_terms"))

    @staticmethod
    def _variance(values: list[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values) / len(values)
