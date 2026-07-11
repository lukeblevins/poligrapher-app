import type { GdprAssessment, PrivacyAssessment, Readability } from "../api/types";
import { useAssessments } from "../hooks/queries";

const TIER_STYLES: Record<string, string> = {
  COMPLIANT: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  WARNING: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  "NON-COMPLIANT": "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
};

const SEVERITY_STYLES: Record<string, string> = {
  CRITICAL: "text-red-600 dark:text-red-400",
  HIGH: "text-orange-600 dark:text-orange-400",
  MEDIUM: "text-amber-600 dark:text-amber-400",
};

export function AssessmentsPanel({ policyId }: { policyId: string }) {
  const { data, isLoading, isError } = useAssessments(policyId);

  if (isLoading) return <p className="quiet-state">Loading assessments…</p>;
  if (isError || !data) return <p className="quiet-state">No assessments are available for this analysis.</p>;

  const { privacy, gdpr, readability } = data;
  if (!privacy && !gdpr) {
    return (
      <p className="quiet-state">
        No scores yet. Run scoring to generate privacy and GDPR assessments.
      </p>
    );
  }

  return (
    <div className="space-y-8 text-sm leading-6">
      {privacy && <PrivacySection privacy={privacy} />}
      {gdpr && <GdprSection gdpr={gdpr} />}
      {readability && <ReadabilitySection readability={readability} />}
    </div>
  );
}

function ScoreHeader({ title, score, badge, badgeClass }: {
  title: string;
  score: string;
  badge: string;
  badgeClass: string;
}) {
  return (
    <div className="mb-3 flex items-center gap-2.5 border-b border-slate-100 pb-3 dark:border-slate-800">
      <h3 className="font-display text-base font-bold tracking-tight">{title}</h3>
      <span className="data-value ml-auto text-sm font-semibold">{score}</span>
      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold tracking-wide ${badgeClass}`}>{badge}</span>
    </div>
  );
}

function PrivacySection({ privacy }: { privacy: PrivacyAssessment }) {
  return (
    <section>
      <ScoreHeader
        title="Privacy"
        score={`${privacy.total_score.toFixed(1)} / 100`}
        badge={privacy.grade}
        badgeClass="bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300"
      />
      <p className="mb-3 text-slate-600 dark:text-slate-400">{privacy.summary}</p>
      <div className="space-y-2">
        {Object.entries(privacy.category_scores).map(([name, cat]) => (
          <details key={name} className="rounded-lg border border-slate-200 dark:border-slate-700">
            <summary className="cursor-pointer px-3 py-2 text-xs font-semibold capitalize">
              {name.replace(/_/g, " ")} — {cat.weighted_score.toFixed(1)}
            </summary>
            <ul className="list-disc space-y-1 px-6 pb-3 pt-1 text-xs leading-5 text-slate-600 dark:text-slate-400">
              {cat.feedback.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}

function GdprSection({ gdpr }: { gdpr: GdprAssessment }) {
  if (!gdpr.success) {
    return (
      <section>
        <h3 className="mb-1 text-sm font-semibold">GDPR</h3>
        <p className="text-xs text-red-600 dark:text-red-400">
          {gdpr.feedback?.join(", ") || "Analysis failed."}
        </p>
      </section>
    );
  }

  const violationGroups = Object.entries(gdpr.top_violations ?? {});
  return (
    <section>
      <ScoreHeader
        title="GDPR"
        score={`${(gdpr.total_score ?? 0).toFixed(1)} / 100`}
        badge={gdpr.tier ?? "UNKNOWN"}
        badgeClass={TIER_STYLES[gdpr.tier ?? ""] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800"}
      />
      <p className="mb-3 text-slate-600 dark:text-slate-400">{gdpr.summary}</p>

      {gdpr.component_scores && (
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Object.entries(gdpr.component_scores).map(([name, c]) => (
            <div
              key={name}
              className="rounded-md border border-slate-300 bg-slate-50/70 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/50"
            >
              <div className="text-[11px] font-medium capitalize text-slate-500 dark:text-slate-400">{name}</div>
              <div className="data-value mt-1 text-sm font-semibold">{c.score.toFixed(2)}</div>
            </div>
          ))}
        </div>
      )}

      {gdpr.severity_counts && (
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
          Severity — CRITICAL {gdpr.severity_counts.CRITICAL ?? 0}, HIGH{" "}
          {gdpr.severity_counts.HIGH ?? 0}, MEDIUM {gdpr.severity_counts.MEDIUM ?? 0}
        </p>
      )}

      {violationGroups.length > 0 && (
        <div>
          <h4 className="section-kicker mb-2">
            Top violations
          </h4>
          <div className="space-y-2">
            {violationGroups.map(([rq, violations]) => (
              <div key={rq}>
                <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">{rq}</div>
                <ul className="space-y-0.5">
                  {violations.map((v) => (
                    <li key={v.code} className="text-xs leading-5 text-slate-600 dark:text-slate-400">
                      <span className="font-mono">{v.code}</span>{" "}
                      <span className={SEVERITY_STYLES[v.severity] ?? ""}>[{v.severity}]</span>{" "}
                      {v.description}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ReadabilitySection({ readability }: { readability: Readability }) {
  const metrics: [string, number][] = [
    ["Flesch-Kincaid", readability.flesch_kincaid],
    ["Gunning Fog", readability.gunning_fog],
    ["Reading ease", readability.flesch_reading_ease],
    ["Words", readability.n_words],
    ["Sentences", readability.n_sentences],
    ["Passive ratio", readability.passive_ratio],
  ];
  return (
    <section>
      <h3 className="mb-3 border-b border-slate-100 pb-3 font-display text-base font-bold tracking-tight dark:border-slate-800">Readability</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {metrics.map(([label, value]) => (
          <div
            key={label}
            className="rounded-md border border-slate-300 bg-slate-50/70 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/50"
          >
            <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{label}</div>
            <div className="data-value mt-1 text-sm font-semibold">
              {Number.isInteger(value) ? value : value.toFixed(2)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
