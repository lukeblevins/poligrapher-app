import { useEffect, useState } from "react";

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

function avatarTone(name: string): number {
  return [...name].reduce((total, character) => total + character.charCodeAt(0), 0) % 3;
}

export function CompanyLogo({
  name,
  domain,
  className = "h-10 w-10",
}: {
  name: string;
  domain?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const safeDomain = domain?.trim().toLowerCase();
  const canLoad = !!safeDomain && /^[a-z0-9.-]+$/.test(safeDomain) && !failed;

  useEffect(() => {
    setFailed(false);
    setLoaded(false);
  }, [safeDomain]);

  return (
    <span
      className={`m3-avatar m3-avatar-tone-${avatarTone(name)} relative grid flex-shrink-0 place-items-center overflow-hidden ${className}`}
      aria-hidden="true"
    >
      {!loaded && <span>{initials(name)}</span>}
      {canLoad && (
        <img
          src={`https://${safeDomain}/favicon.ico`}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          className={`m3-avatar-image absolute inset-0 h-full w-full object-contain ${loaded ? "opacity-100" : "opacity-0"}`}
          onLoad={(event) => setLoaded(event.currentTarget.naturalWidth > 0 && event.currentTarget.naturalHeight > 0)}
          onError={() => {
            setLoaded(false);
            setFailed(true);
          }}
        />
      )}
    </span>
  );
}
