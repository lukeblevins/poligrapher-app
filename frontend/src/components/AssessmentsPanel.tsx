import type { GdprAssessment, PrivacyAssessment, Readability } from "../api/types";
import { useAssessments } from "../hooks/queries";

export function AssessmentsPanel({ policyId }: { policyId: string }) {
  const { data, isLoading, isError, error } = useAssessments(policyId);
  if (isLoading) return <p role="status" className="quiet-state">Loading assessment results…</p>;
  if (isError) return <p role="alert" className="status-error">Could not load assessment results. {error instanceof Error ? error.message : "Try again."}</p>;
  if (!data) return <p className="quiet-state">Assessment results are not available for this analysis.</p>;
  const { privacy, gdpr, readability } = data;
  if (!privacy && !gdpr) return <p className="quiet-state">No assessment scores yet. Score this analysis to generate privacy and GDPR results.</p>;

  return <div className="m3-results-panel"><header className="m3-results-heading"><h2>Assessment results</h2><p>Privacy, GDPR, and readability results for this policy snapshot.</p></header>{privacy && <PrivacySection privacy={privacy} />}{gdpr && <GdprSection gdpr={gdpr} />}{readability && <ReadabilitySection readability={readability} />}</div>;
}

function ScoreHeader({ title, score, badge, tone }: { title: string; score: string; badge: string; tone: "primary" | "success" | "warning" | "error" | "neutral" }) {
  return <header className="m3-score-header"><div><h3>{title}</h3><p>Score out of 100</p></div><strong className={`m3-assessment-score m3-assessment-score-${tone} data-value`}><span>{score}</span><small>/100</small></strong><span className={`m3-score-badge m3-score-badge-${tone}`}>{badge}</span></header>;
}

function PrivacySection({ privacy }: { privacy: PrivacyAssessment }) {
  return <section className="m3-result-section"><ScoreHeader title="Privacy assessment" score={privacy.total_score.toFixed(1)} badge={privacy.grade} tone="primary" /><p className="m3-supporting-copy">{privacy.summary}</p><div className="m3-feedback-list">{Object.entries(privacy.category_scores).map(([name, category]) => <details key={name}><summary><span>{name.replace(/_/g, " ")}</span><strong className="data-value">{category.weighted_score.toFixed(1)}</strong></summary><ul>{category.feedback.map((feedback, index) => <li key={index}>{feedback}</li>)}</ul></details>)}</div></section>;
}

function GdprSection({ gdpr }: { gdpr: GdprAssessment }) {
  if (!gdpr.success) return <section className="m3-result-section"><ScoreHeader title="GDPR assessment" score="—" badge="Unavailable" tone="error" /><p role="alert" className="m3-supporting-copy text-[var(--md-sys-color-error)]">{gdpr.feedback?.join(", ") || "The GDPR assessment could not be completed."}</p></section>;
  const tier = gdpr.tier ?? "UNKNOWN";
  const tone = tier === "COMPLIANT" ? "success" : tier === "WARNING" ? "warning" : tier === "NON-COMPLIANT" ? "error" : "neutral";
  return <section className="m3-result-section"><ScoreHeader title="GDPR assessment" score={(gdpr.total_score ?? 0).toFixed(1)} badge={tier} tone={tone} /><p className="m3-supporting-copy">{gdpr.summary}</p>{gdpr.component_scores && <div className="m3-metric-grid m3-metric-grid-compact">{Object.entries(gdpr.component_scores).map(([name, component]) => <Metric key={name} label={name} value={component.score.toFixed(2)} />)}</div>}{gdpr.severity_counts && <div className="m3-severity-summary"><span>Critical <b>{gdpr.severity_counts.CRITICAL ?? 0}</b></span><span>High <b>{gdpr.severity_counts.HIGH ?? 0}</b></span><span>Medium <b>{gdpr.severity_counts.MEDIUM ?? 0}</b></span></div>}<Violations groups={gdpr.top_violations ?? {}} /></section>;
}

function Violations({ groups }: { groups: NonNullable<GdprAssessment["top_violations"]> }) {
  const entries = Object.entries(groups); if (!entries.length) return null;
  return <div className="m3-violation-list"><h4>Top findings</h4>{entries.map(([requirement, violations]) => <div key={requirement}><p>{requirement}</p><ul>{violations.map((violation) => <li key={violation.code}><span className={`m3-severity m3-severity-${violation.severity.toLowerCase()}`}>{violation.severity}</span><b className="data-value">{violation.code}</b><span>{violation.description}</span></li>)}</ul></div>)}</div>;
}

function ReadabilitySection({ readability }: { readability: Readability }) {
  const metrics: [string, number][] = [["Flesch-Kincaid", readability.flesch_kincaid], ["Gunning Fog", readability.gunning_fog], ["Reading ease", readability.flesch_reading_ease], ["Words", readability.n_words], ["Sentences", readability.n_sentences], ["Passive voice", readability.passive_ratio]];
  return <section className="m3-result-section"><h3>Readability</h3><p className="m3-supporting-copy">Writing complexity and document length indicators.</p><div className="m3-metric-grid m3-metric-grid-compact">{metrics.map(([label, value]) => <Metric key={label} label={label} value={Number.isInteger(value) ? value : value.toFixed(2)} />)}</div></section>;
}

function Metric({ label, value }: { label: string; value: number | string }) { return <article className="m3-metric-card"><p>{label}</p><strong className="data-value">{value}</strong></article>; }
