import { useEffect, useState } from "react";

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

export function CompanyLogo({
  name,
  domain,
  className = "h-8 w-8",
}: {
  name: string;
  domain?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const safeDomain = domain?.trim().toLowerCase();
  const canLoad = !!safeDomain && /^[a-z0-9.-]+$/.test(safeDomain) && !failed;

  useEffect(() => setFailed(false), [safeDomain]);

  return (
    <span
      className={`grid flex-shrink-0 place-items-center overflow-hidden rounded border border-slate-300 bg-white text-[10px] font-bold tracking-wide text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 ${className}`}
      aria-hidden="true"
    >
      {canLoad ? (
        <img
          src={`https://${safeDomain}/favicon.ico`}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          className="h-full w-full object-contain p-1"
          onError={() => setFailed(true)}
        />
      ) : (
        <span>{initials(name)}</span>
      )}
    </span>
  );
}
