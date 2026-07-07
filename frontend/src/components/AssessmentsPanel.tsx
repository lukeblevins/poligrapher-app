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

  if (isLoading) return <p className="text-sm text-zinc-400">Loading…</p>;
  if (isError || !data) return <p className="text-sm text-zinc-400">No assessments available.</p>;

  const { privacy, gdpr, readability } = data;
  if (!privacy && !gdpr) {
    return (
      <p className="text-sm text-zinc-400">
        No scores yet. Use the Score button on the policy row.
      </p>
    );
  }

  return (
    <div className="space-y-6 text-sm">
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
    <div className="mb-2 flex items-center gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <span className="font-mono text-sm">{score}</span>
      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${badgeClass}`}>{badge}</span>
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
        badgeClass="bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
      />
      <p className="mb-2 text-zinc-600 dark:text-zinc-400">{privacy.summary}</p>
      <div className="space-y-1.5">
        {Object.entries(privacy.category_scores).map(([name, cat]) => (
          <details key={name} className="rounded border border-zinc-200 dark:border-zinc-700">
            <summary className="cursor-pointer px-3 py-1.5 text-xs font-medium capitalize">
              {name.replace(/_/g, " ")} — {cat.weighted_score.toFixed(1)}
            </summary>
            <ul className="list-disc space-y-0.5 px-6 py-2 text-xs text-zinc-600 dark:text-zinc-400">
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
        badgeClass={TIER_STYLES[gdpr.tier ?? ""] ?? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800"}
      />
      <p className="mb-2 text-zinc-600 dark:text-zinc-400">{gdpr.summary}</p>

      {gdpr.component_scores && (
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Object.entries(gdpr.component_scores).map(([name, c]) => (
            <div
              key={name}
              className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1.5 dark:border-zinc-700 dark:bg-zinc-800/50"
            >
              <div className="text-xs capitalize text-zinc-500 dark:text-zinc-400">{name}</div>
              <div className="font-mono text-sm">{c.score.toFixed(2)}</div>
            </div>
          ))}
        </div>
      )}

      {gdpr.severity_counts && (
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          Severity — CRITICAL {gdpr.severity_counts.CRITICAL ?? 0}, HIGH{" "}
          {gdpr.severity_counts.HIGH ?? 0}, MEDIUM {gdpr.severity_counts.MEDIUM ?? 0}
        </p>
      )}

      {violationGroups.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-zinc-500 dark:text-zinc-400">
            Top violations
          </h4>
          <div className="space-y-2">
            {violationGroups.map(([rq, violations]) => (
              <div key={rq}>
                <div className="text-xs font-medium text-zinc-600 dark:text-zinc-300">{rq}</div>
                <ul className="space-y-0.5">
                  {violations.map((v) => (
                    <li key={v.code} className="text-xs text-zinc-600 dark:text-zinc-400">
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
      <h3 className="mb-2 text-sm font-semibold">Readability</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {metrics.map(([label, value]) => (
          <div
            key={label}
            className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1.5 dark:border-zinc-700 dark:bg-zinc-800/50"
          >
            <div className="text-xs text-zinc-500 dark:text-zinc-400">{label}</div>
            <div className="font-mono text-sm">
              {Number.isInteger(value) ? value : value.toFixed(2)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
