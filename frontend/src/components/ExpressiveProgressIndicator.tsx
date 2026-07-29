import { useId } from "react";

type ExpressiveProgressIndicatorProps = {
  label: string;
  value?: number;
};

const WAVE_PATH = "M0 8 Q6 0 12 8 T24 8 T36 8 T48 8 T60 8 T72 8 T84 8 T96 8 T108 8 T120 8 T132 8 T144 8 T156 8 T168 8 T180 8 T192 8 T204 8 T216 8 T228 8 T240 8 T252 8 T264 8 T276 8 T288 8 T300 8 T312 8 T324 8 T336 8 T348 8 T360 8 T372 8 T384 8 T396 8 T408 8 T420 8 T432 8 T444 8 T456 8 T468 8 T480 8 T492 8 T504 8 T516 8 T528 8 T540 8 T552 8 T564 8 T576 8 T588 8 T600 8 T612 8 T624 8";

export function ExpressiveProgressIndicator({ label, value }: ExpressiveProgressIndicatorProps) {
  const clipId = useId().replace(/:/g, "");
  const normalizedValue = value === undefined || !Number.isFinite(value) ? undefined : Math.max(0, Math.min(1, value));
  const progressX = (normalizedValue ?? 0) * 600;
  const trackStart = Math.min(594, progressX + 12);

  return (
    <div
      className={`m3-expressive-progress ${normalizedValue === undefined ? "m3-expressive-progress-indeterminate" : "m3-expressive-progress-determinate"}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={normalizedValue === undefined ? undefined : Math.round(normalizedValue * 100)}
      aria-valuetext={normalizedValue === undefined ? "In progress" : `${Math.round(normalizedValue * 100)}%`}
    >
      <svg viewBox="0 0 600 16" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <clipPath id={clipId}>
            <rect className="m3-expressive-progress-clip" x="0" y="0" width={normalizedValue === undefined ? 600 : normalizedValue * 600} height="16" />
          </clipPath>
        </defs>
        <line
          className="m3-expressive-progress-track"
          x1={normalizedValue === undefined ? 6 : trackStart}
          y1="8"
          x2="594"
          y2="8"
        />
        {normalizedValue === undefined ? null : <circle className="m3-expressive-progress-stop" cx="594" cy="8" r="3" />}
        <g clipPath={`url(#${clipId})`}>
          <path className="m3-expressive-progress-wave" d={WAVE_PATH} pathLength="600" />
        </g>
      </svg>
    </div>
  );
}
