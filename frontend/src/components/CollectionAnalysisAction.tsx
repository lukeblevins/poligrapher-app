import analyzeIcon from "@material-symbols/svg-400/rounded/analytics.svg?url";
import type { CSSProperties } from "react";

import type { BulkActionPreview } from "../api/types";

type CollectionAnalysisActionProps = {
  preview: BulkActionPreview | undefined;
  isLoading: boolean;
  isError: boolean;
  confirming: boolean;
  isPending: boolean;
  error: Error | null;
  onReview: () => void;
  onCancel: () => void;
  onConfirm: () => void;
  onRetry: () => void;
};

export function CollectionAnalysisAction({
  preview,
  isLoading,
  isError,
  confirming,
  isPending,
  error,
  onReview,
  onCancel,
  onConfirm,
  onRetry,
}: CollectionAnalysisActionProps) {
  const eligibleCount = preview?.eligible_count ?? 0;
  const skippedCount = preview?.skipped_count ?? 0;

  return (
    <section id="collection-analysis-action" className="m3-collection-analysis-action" aria-labelledby="collection-analysis-heading">
      <div className="m3-collection-analysis-summary">
        <span className="m3-collection-analysis-icon" aria-hidden="true">
          <span className="m3-material-symbol" style={{ "--m3-symbol-url": `url("${analyzeIcon}")` } as CSSProperties} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="collection-analysis-heading" className="font-display text-lg font-semibold">
            {isLoading
              ? "Checking analysis readiness…"
              : isError
                ? "Analysis readiness is unavailable"
                : eligibleCount
                  ? `${eligibleCount} ${eligibleCount === 1 ? "company is" : "companies are"} ready to analyze`
                  : "Collection analysis is up to date"}
          </h2>
          {!isLoading && !isError && preview ? (
            <p>
              {eligibleCount
                ? `${skippedCount} ${skippedCount === 1 ? "company stays" : "companies stay"} untouched because analysis is complete or a policy source is unavailable.`
                : "No source-backed companies without completed graph output are waiting for analysis."}
            </p>
          ) : null}
          {isError ? <p>Refresh the eligibility preview before queueing collection work.</p> : null}
        </div>
      </div>

      <div className="m3-collection-analysis-controls">
        {isError ? <button type="button" className="m3-collection-analysis-button secondary" onClick={onRetry}>Try again</button> : null}
        {!isLoading && !isError && eligibleCount > 0 && !confirming ? (
          <button type="button" className="m3-collection-analysis-button primary" onClick={onReview}>Review &amp; queue</button>
        ) : null}
      </div>

      {confirming && preview ? (
        <div className="m3-collection-analysis-confirmation" role="group" aria-label="Confirm collection analysis">
          <p>
            Queue analysis for <strong>{eligibleCount}</strong> {eligibleCount === 1 ? "company" : "companies"}. Existing graph output will not be regenerated.
          </p>
          {error ? <p role="alert" className="status-error">{error.message}</p> : null}
          <div className="m3-collection-analysis-confirmation-actions">
            <button type="button" className="m3-collection-analysis-button secondary" disabled={isPending} onClick={onCancel}>Cancel</button>
            <button type="button" className="m3-collection-analysis-button primary" disabled={isPending} onClick={onConfirm}>{isPending ? "Queueing…" : "Confirm and queue"}</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
