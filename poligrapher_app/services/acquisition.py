"""Dynamic privacy-policy source acquisition.

A stored deep URL rots (pages move, 404, get renamed, hide behind consent walls,
or render client-side). This module resolves a *current* policy source for a
provider through a layered strategy chain, returning a candidate URL plus a
confidence score so callers can auto-run high-confidence resolutions and ask a
human to confirm weak ones. See docs/SCHEDULED_ACQUISITION.md for the rationale.

Strategies (best first):
  1. override   — a user-confirmed canonical URL stored on the provider
  2. ota        — an Open Terms Archive service declaration (curated URL + a
                  content selector that also improves extraction quality)
  3. discovery  — load the provider domain and find the privacy link, scored by
                  link text/href and constrained to the same registrable domain
  4. sitemap    — grep robots.txt / sitemap.xml for a privacy URL

Pure helpers (scoring, link discovery from HTML, extraction, hashing, name and
domain normalization) are import-light and unit-testable without a browser.
Network/headless fetching is isolated behind ``fetch_html``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.parse
from dataclasses import dataclass, field

import httpx
import tldextract
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

OTA_COLLECTIONS = ("contrib-declarations",)
OTA_RAW = "https://raw.githubusercontent.com/OpenTermsArchive/{col}/main/declarations/{name}.json"

_UA = {"User-Agent": "Mozilla/5.0 (compatible; PoligrapherBot/1.0; +privacy-policy-analyzer)"}

# Confidence a resolution must clear to run automatically; below this the source
# is surfaced to the user for confirmation.
AUTO_CONFIDENCE = 0.75

_PRIVACY_PATH = re.compile(r"privacy[-_/]?(policy|notice|statement|center|centre)?", re.I)
_COMPANY_SUFFIX = re.compile(
    r"[\s,]+(inc\.?|incorporated|corp\.?|corporation|co\.?|company|"
    r"plc|ltd\.?|llc|l\.?p\.?|holdings?|group|technologies|the)\b",
    re.I,
)


# ── candidates & results ──────────────────────────────────────────────────────

@dataclass
class SourceCandidate:
    url: str
    strategy: str
    confidence: float
    select: list[str] | str | None = None  # OTA content selector(s), if any
    notes: str = ""


@dataclass
class ResolvedSource:
    url: str
    text: str
    content_hash: str
    confidence: float
    strategy: str
    select: list[str] | str | None = None
    notes: str = ""

    @property
    def auto(self) -> bool:
        return self.confidence >= AUTO_CONFIDENCE


# ── pure helpers ──────────────────────────────────────────────────────────────

def registrable_domain(url_or_host: str) -> str:
    """Return the registrable domain (e.g. ``www.abbott.com`` -> ``abbott.com``)."""
    host = url_or_host
    if "//" in host or host.startswith("http"):
        host = urllib.parse.urlparse(url_or_host).netloc
    ext = tldextract.extract(host or url_or_host)
    return ".".join(p for p in (ext.domain, ext.suffix) if p)


def provider_domain_from_urls(urls: list[str]) -> str | None:
    """Derive the most common registrable domain from existing policy URLs."""
    from collections import Counter

    domains = Counter()
    for u in urls:
        if not u or not u.lower().startswith("http"):
            continue
        d = registrable_domain(u)
        if d:
            domains[d] += 1
    return domains.most_common(1)[0][0] if domains else None


def ota_name_candidates(provider_name: str) -> list[str]:
    """Candidate OTA service names for a provider (OTA uses bare brand names)."""
    name = provider_name.strip()
    out = [name]
    stripped = _COMPANY_SUFFIX.sub("", name).strip(" .,&")
    if stripped and stripped != name:
        out.append(stripped)
    first = name.split()[0].strip(" .,&") if name.split() else ""
    if first and first not in out:
        out.append(first)
    # de-dupe, keep order
    seen: set[str] = set()
    return [n for n in out if not (n in seen or seen.add(n))]


def score_link(text: str, href: str, domain: str) -> int:
    """Heuristic score that ``href`` is the provider's own privacy policy."""
    t = (text or "").strip().lower()
    h = (href or "").lower()
    s = 0
    if any(k in t for k in ("privacy policy", "privacy notice", "privacy statement")):
        s += 5
    elif "privacy" in t:
        s += 3
    if re.search(r"privacy[-_]?(policy|notice|statement)", h):
        s += 4
    elif "privacy" in h:
        s += 2
    if "cookie" in t or "cookie" in h:
        s -= 3  # cookie policy is a different document
    if any(k in t for k in ("ad choices", "do not sell", "ccpa")):
        s -= 1
    # same registrable domain is required: a privacy link on another domain is a
    # subsidiary/partner page, never the provider's own policy -> hard exclude.
    host = urllib.parse.urlparse(h).netloc
    if host and domain and registrable_domain(host) != domain:
        return -100
    return s


def discover_links(html: str, base_url: str, domain: str, top: int = 3) -> list[tuple[int, str]]:
    """Return scored (score, absolute_url) privacy-link candidates from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    cands: list[tuple[int, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        sc = score_link(a.get_text(), a["href"], domain)
        if sc <= 0:
            continue
        url = urllib.parse.urljoin(base_url, a["href"]).split("#")[0]
        if url in seen:
            continue
        seen.add(url)
        cands.append((sc, url))
    cands.sort(reverse=True)
    return cands[:top]


def extract_text(html: str, select: list[str] | str | None = None) -> str:
    """Extract policy text: OTA selector(s) when given, else de-boilerplated body."""
    soup = BeautifulSoup(html, "html.parser")
    if select:
        selectors = [select] if isinstance(select, str) else list(select)
        parts: list[str] = []
        for sel in selectors:
            for el in soup.select(sel):
                parts.append(el.get_text(" ", strip=True))
        if parts:
            return _normalize_ws("\n".join(parts))
    # fallback: strip obvious non-content, take the body text
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    return _normalize_ws(root.get_text(" ", strip=True))


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def content_hash(text: str) -> str:
    """Stable hash of the *extracted* text (ignores markup/nonce churn)."""
    return hashlib.sha256(_normalize_ws(text).encode("utf-8", "ignore")).hexdigest()


# ── network / headless fetching ───────────────────────────────────────────────

def fetch_static(url: str, timeout: float = 15.0) -> tuple[int, str]:
    try:
        r = httpx.get(url, headers=_UA, follow_redirects=True, timeout=timeout)
        return r.status_code, r.text
    except Exception as exc:  # noqa: BLE001
        logger.info("static fetch failed for %s: %s", url, exc)
        return 0, ""


def fetch_rendered(url: str, timeout_ms: int = 25000) -> str:
    """Load a page in a headless browser (recovers SPA / bot-blocked sites)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=_UA["User-Agent"])
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)  # let lazy footers/consent scripts settle
            return page.content()
        finally:
            browser.close()


def fetch_html(url: str, allow_headless: bool = True) -> str:
    """Fetch HTML, escalating to a headless browser when static fetch is blocked."""
    status, html = fetch_static(url)
    blocked = status in (0, 403, 429, 503) or len(html) < 2000
    if blocked and allow_headless:
        logger.info("escalating to headless browser for %s (static status=%s)", url, status)
        try:
            return fetch_rendered(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("headless fetch failed for %s: %s", url, exc)
    return html


# ── OTA lookup ────────────────────────────────────────────────────────────────

def ota_declaration(provider_name: str) -> dict | None:
    """Fetch an OTA Privacy Policy declaration for a provider, if one exists."""
    for name in ota_name_candidates(provider_name):
        quoted = urllib.parse.quote(name)
        for col in OTA_COLLECTIONS:
            url = OTA_RAW.format(col=col, name=quoted)
            status, body = fetch_static(url, timeout=10.0)
            if status != 200 or not body:
                continue
            try:
                import json

                data = json.loads(body)
            except Exception:
                continue
            pp = (data.get("terms") or {}).get("Privacy Policy")
            if pp and pp.get("fetch"):
                logger.info("OTA declaration matched %r (collection %s)", name, col)
                return pp
    return None


# ── resolver ──────────────────────────────────────────────────────────────────

class PolicySourceResolver:
    def __init__(self, allow_headless: bool = True):
        self.allow_headless = allow_headless

    def resolve_candidate(
        self, provider_name: str, domain: str | None, override_url: str | None = None
    ) -> SourceCandidate | None:
        """Pick the best source URL for a provider without fetching its text."""
        if override_url:
            return SourceCandidate(override_url, "override", 1.0, notes="user-confirmed")

        pp = ota_declaration(provider_name)
        if pp:
            conf = 0.9 if not pp.get("executeClientScripts") else 0.88
            return SourceCandidate(pp["fetch"], "ota", conf, select=pp.get("select"),
                                   notes="Open Terms Archive declaration")

        if domain:
            html = fetch_html(f"https://www.{domain}", self.allow_headless)
            if html:
                cands = discover_links(html, f"https://www.{domain}", domain)
                if cands:
                    score, url = cands[0]
                    # strong path match on same domain -> high confidence
                    conf = 0.8 if score >= 8 and _PRIVACY_PATH.search(url) else min(0.5 + 0.05 * score, 0.7)
                    return SourceCandidate(url, "discovery", round(conf, 2),
                                           notes=f"footer/link match (score {score})")

            sm = self._sitemap_candidate(domain)
            if sm:
                return sm
        return None

    def _sitemap_candidate(self, domain: str) -> SourceCandidate | None:
        status, robots = fetch_static(f"https://www.{domain}/robots.txt", timeout=8.0)
        sitemaps = re.findall(r"(?i)sitemap:\s*(\S+)", robots) if status == 200 else []
        sitemaps = sitemaps or [f"https://www.{domain}/sitemap.xml"]
        for sm in sitemaps[:3]:
            s, body = fetch_static(sm, timeout=10.0)
            if s != 200:
                continue
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body):
                if _PRIVACY_PATH.search(loc) and registrable_domain(loc) == domain:
                    return SourceCandidate(loc, "sitemap", 0.6, notes="sitemap entry")
        return None

    def resolve(
        self, provider_name: str, domain: str | None, override_url: str | None = None
    ) -> ResolvedSource | None:
        """Resolve and fetch the current policy source for a provider."""
        cand = self.resolve_candidate(provider_name, domain, override_url)
        if not cand:
            return None
        html = fetch_html(cand.url, self.allow_headless)
        if not html:
            return None
        text = extract_text(html, cand.select)
        return ResolvedSource(
            url=cand.url,
            text=text,
            content_hash=content_hash(text),
            confidence=cand.confidence,
            strategy=cand.strategy,
            select=cand.select,
            notes=cand.notes,
        )
