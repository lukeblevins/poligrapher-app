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
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx
import tldextract
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

OTA_COLLECTIONS = ("contrib-declarations",)
OTA_RAW = "https://raw.githubusercontent.com/OpenTermsArchive/{col}/main/declarations/{name}.json"

# Present as a current desktop Chrome, not a bot. Corporate WAFs (Akamai,
# Cloudflare, Imperva) block obvious bot User-Agents on sight — the old
# "PoligrapherBot/1.0" was an instant reject — so we send a full, realistic
# browser header set for static fetches.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-CH-UA": '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# The Wayback Machine availability API. Fetching an archived snapshot sidesteps
# live-site bot-blocking entirely and, as a bonus for a policy-comparison
# research project, yields historical versions of the document.
WAYBACK_AVAILABLE = "https://archive.org/wayback/available?url={url}"
READER_PREFIX = "https://r.jina.ai/https://"
DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
YAHOO_SEARCH = "https://search.yahoo.com/search"


# ── optional Tier-2 anti-bot: proxy + unblocker API (env-gated, off by default) ─
#
# Datacenter-IP blocking is only reliably beaten by routing target requests
# through non-datacenter IPs. These hooks stay dormant (and free) unless the
# corresponding env vars are set, so nothing changes for the default deployment.
#
#   CRAWL_PROXY            e.g. http://user:pass@gw.provider.com:7777  (residential/ISP proxy)
#   CRAWL_PROXY_USERNAME   optional, if creds aren't embedded in CRAWL_PROXY
#   CRAWL_PROXY_PASSWORD   optional
#
#   SCRAPE_API_URL         unblocker/scraping-API template, e.g.
#                          https://api.zyte.com/v1/... or
#                          https://app.scrapingbee.com/api/v1/?api_key={key}&render_js=true&url={url}
#   SCRAPE_API_KEY         substituted into {key} in SCRAPE_API_URL

def _proxy_parts() -> tuple[str, str | None, str | None] | None:
    server = (os.getenv("CRAWL_PROXY") or "").strip()
    if not server:
        return None
    if "://" not in server:
        server = f"http://{server.lstrip('/')}"
    return server, os.getenv("CRAWL_PROXY_USERNAME"), os.getenv("CRAWL_PROXY_PASSWORD")


def crawl_proxy_mode() -> str:
    """Return ``fallback`` (default), ``always``, or ``off``."""
    mode = (os.getenv("CRAWL_PROXY_MODE") or "fallback").strip().lower()
    return mode if mode in {"fallback", "always", "off"} else "fallback"


def httpx_proxy() -> str | None:
    """Proxy URL for httpx, or None when unconfigured (creds folded into URL)."""
    parts = _proxy_parts()
    if not parts:
        return None
    server, user, pwd = parts
    if user and pwd and "@" not in server:
        p = urllib.parse.urlparse(server)
        creds = f"{urllib.parse.quote(user, safe='')}:{urllib.parse.quote(pwd, safe='')}"
        return urllib.parse.urlunparse(p._replace(netloc=f"{creds}@{p.netloc}"))
    return server


def playwright_proxy() -> dict | None:
    """Playwright ``proxy=`` config dict, or None when unconfigured."""
    parts = _proxy_parts()
    if not parts:
        return None
    server, user, pwd = parts
    cfg: dict[str, str] = {"server": server}
    if user:
        cfg["username"] = user
    if pwd:
        cfg["password"] = pwd
    return cfg


def open_client(timeout: float, proxy: str | None = None) -> httpx.Client:
    """Build an httpx.Client with browser headers, optionally proxied.

    Version-agnostic: httpx renamed the proxy kwarg (``proxies`` -> ``proxy``),
    and passing the wrong one raises TypeError. We only pass it when a proxy is
    configured, trying the modern name first and falling back to the old one, so
    the default (no-proxy) path works on every httpx version.
    """
    kwargs = dict(headers=BROWSER_HEADERS, follow_redirects=True, timeout=timeout)
    if proxy:
        try:
            return httpx.Client(proxy=proxy, **kwargs)
        except TypeError:
            return httpx.Client(proxies=proxy, **kwargs)
    return httpx.Client(**kwargs)


def fetch_via_unblocker(url: str, timeout: float = 60.0) -> str:
    """Fetch HTML through a configured unblocker/scraping API, or '' if unset.

    The service handles IP rotation, JS rendering, and CAPTCHA solving and
    returns the page HTML. Enabled only when SCRAPE_API_URL is set.
    """
    template = (os.getenv("SCRAPE_API_URL") or "").strip()
    if not template:
        return ""
    endpoint = template.replace("{key}", os.getenv("SCRAPE_API_KEY", "")).replace(
        "{url}", urllib.parse.quote(url, safe="")
    )
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            r = client.get(endpoint)
        if r.status_code == 200 and len(r.text) >= 2000:
            logger.info("fetched via unblocker API: %s", url)
            return r.text
        logger.info("unblocker API returned %s / %d bytes for %s", r.status_code, len(r.text), url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("unblocker API failed for %s: %s", url, exc)
    return ""

# Confidence a resolution must clear to run automatically; below this the source
# is surfaced to the user for confirmation.
AUTO_CONFIDENCE = 0.75

_PRIVACY_PATH = re.compile(r"privacy[-_/]?(policy|notice|statement|center|centre)?", re.I)
_NARROW_POLICY_RESULT = re.compile(
    r"(?:^|[\s/_-])(?:applicant|candidate|recruit|employee|workday|pension|retiree|"
    r"hipaa|health[-_ ]fund|benchmark|study|canadian[-_ ]residents?|"
    r"investors?|annual[-_ ]reports?|careers?|jobs?|manuals?|prospects?|"
    r"connected[-_ ]apps?|human[-_ ]resources?|hr[-_ ]information|"
    r"newsletters?|subscriptions?)(?:$|[\s/?#&._=-])",
    re.I,
)
_PIPELINE_POLICY_PATTERN = re.compile(
    r"(data|privacy)\s*(?:policy|notice|statement)", re.I
)
_PIPELINE_HTML_REMOVE_SELECTORS = (
    "script, noscript, link, style, header, footer, nav, iframe, "
    "img, picture, video, audio, source, object, embed"
)
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
    if _NARROW_POLICY_RESULT.search(f"{t} {h}"):
        return -100
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


def search_result_links(html: str) -> list[tuple[str, str]]:
    """Extract de-redirected result links from supported HTML search pages."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc:
            href = urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
        elif "r.search.yahoo.com" in parsed.netloc:
            match = re.search(r"/RU=([^/]+?)/RK=", parsed.path)
            if not match:
                continue
            href = urllib.parse.unquote(match.group(1))
        elif "result__a" not in (anchor.get("class") or []):
            continue
        href = urllib.parse.unquote(href)
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        results.append((anchor.get_text(" ", strip=True), href))
    return results


def _company_tokens(name: str) -> set[str]:
    stripped = _COMPANY_SUFFIX.sub("", name).casefold()
    return {
        token for token in re.findall(r"[a-z0-9]+", stripped)
        if len(token) >= 3 and token not in {"class", "global"}
    }


def privacy_document_text(data: bytes, content_type: str, url: str) -> str:
    """Extract enough text to validate an HTML or PDF privacy document."""
    if data.startswith(b"%PDF") or "pdf" in content_type.casefold() or url.lower().endswith(".pdf"):
        try:
            from io import BytesIO
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data))
            return _normalize_ws(" ".join((page.extract_text() or "") for page in reader.pages[:12]))
        except Exception:  # noqa: BLE001
            return ""
    return extract_text(data.decode("utf-8", "ignore"))


def is_privacy_document(text: str, provider_name: str, *, same_domain: bool) -> bool:
    """Reject search noise while permitting branded or parent-company policies."""
    normalized = text.casefold()
    if len(normalized) < 500 or "privacy" not in normalized:
        return False
    if same_domain:
        return True
    tokens = _company_tokens(provider_name)
    return bool(tokens and any(token in normalized for token in tokens))


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


def validate_policy_html(html: str) -> str:
    """Sanitize HTML and return it only when it satisfies the crawler contract."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select(_PIPELINE_HTML_REMOVE_SELECTORS):
        element.decompose()
    for element in soup.select('[aria-hidden="true"]'):
        element["aria-hidden"] = "false"

    text = soup.body.get_text(" ", strip=True) if soup.body else ""
    try:
        import langdetect

        language = langdetect.detect(text)
    except Exception:  # noqa: BLE001
        language = "UNKNOWN"
    if not language.casefold().startswith("en"):
        return ""
    if _PIPELINE_POLICY_PATTERN.search(text) is None:
        return ""
    return str(soup)


def fetch_validated_policy_html(
    url: str,
    timeout: float = 30.0,
    *,
    attempts: int = 2,
) -> str:
    """Fetch pipeline-valid HTML through the application's shared client.

    The upstream crawler performs its own request with ``requests`` after
    Chromium navigation fails; some corporate sites accept this application's
    ``httpx`` request and reject the crawler's second request. Materializing the
    already validated bytes lets the crawler process that content locally.
    """

    status, html = fetch_static(url, timeout=timeout, attempts=attempts)
    return validate_policy_html(html) if status == 200 and html else ""


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def content_hash(text: str) -> str:
    """Stable hash of the *extracted* text (ignores markup/nonce churn)."""
    return hashlib.sha256(_normalize_ws(text).encode("utf-8", "ignore")).hexdigest()


# ── network / headless fetching ───────────────────────────────────────────────

def fetch_static(
    url: str,
    timeout: float = 20.0,
    attempts: int = 3,
    use_proxy: bool = True,
    force_proxy: bool = False,
) -> tuple[int, str]:
    """GET a URL with realistic headers, retrying transient failures with backoff.

    Corporate CDNs are slow and rate-limit bursts, so we retry on connection
    errors/timeouts and on 429/503 with a short exponential backoff. In the
    default ``fallback`` mode this function tries direct access; ``fetch_html``
    explicitly retries through the proxy only after a block. ``always`` routes
    every eligible request through the proxy, while archive/OTA callers pass
    ``use_proxy=False`` to avoid spending proxy bandwidth.
    """
    mode = crawl_proxy_mode()
    proxy = httpx_proxy() if use_proxy and mode != "off" and (force_proxy or mode == "always") else None
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            with open_client(timeout, proxy) as client:
                r = client.get(url)
            if r.status_code in (429, 503) and i < attempts - 1:
                time.sleep(1.5 * (i + 1))
                continue
            return r.status_code, r.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i < attempts - 1:
                time.sleep(1.0 * (i + 1))
    logger.info("static fetch failed for %s: %s", url, last_exc)
    return 0, ""


def fetch_rendered(url: str, timeout_ms: int = 35000, *, use_proxy: bool = False) -> str:
    """Load a page in a headless browser (recovers SPA / bot-blocked sites).

    Uses light stealth so a default headless fingerprint doesn't get flagged:
    a real UA + Accept-Language, a desktop viewport/locale/timezone, and a
    masked ``navigator.webdriver``.
    """
    from playwright.sync_api import sync_playwright

    launch_kwargs: dict = {
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    }
    proxy = playwright_proxy() if use_proxy and crawl_proxy_mode() != "off" else None
    if proxy:
        launch_kwargs["proxy"] = proxy

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(
                user_agent=BROWSER_HEADERS["User-Agent"],
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={"Accept-Language": BROWSER_HEADERS["Accept-Language"]},
            )
            # Hide the automation flag most bot-detectors check first.
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)  # let lazy footers/consent scripts settle
            return page.content()
        finally:
            browser.close()


def wayback_snapshot_url(url: str, timeout: float = 15.0, raw: bool = True) -> str | None:
    """Return the archived URL of the closest Wayback snapshot, or None.

    ``raw=True`` uses the ``id_`` modifier to return the original archived
    resource (no toolbar/rewriting) — best for an httpx text fetch. ``raw=False``
    returns the standard https replay URL, which is what to navigate a browser to
    (the raw ``id_`` endpoint refuses browser navigation from some networks).
    """
    try:
        api = WAYBACK_AVAILABLE.format(url=urllib.parse.quote(url, safe=""))
        r = httpx.get(api, headers=BROWSER_HEADERS, follow_redirects=True, timeout=timeout)
        snap = ((r.json().get("archived_snapshots") or {}).get("closest") or {})
        if not snap.get("available") or not snap.get("url"):
            return None
        snap_url = snap["url"].replace("http://", "https://", 1)  # avoid http refusals
        if raw:
            # https://web.archive.org/web/<ts>/<orig> -> .../web/<ts>id_/<orig>
            return re.sub(r"/web/(\d+)/", r"/web/\1id_/", snap_url, count=1)
        return snap_url
    except Exception as exc:  # noqa: BLE001
        logger.info("wayback lookup failed for %s: %s", url, exc)
        return None


def reader_snapshot_url(
    url: str, provider_name: str, timeout: float = 20.0
) -> str | None:
    """Return a readable text mirror when an origin and Wayback both refuse access."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    reader_url = f"{READER_PREFIX}{parsed.netloc}{parsed.path}"
    if parsed.query:
        reader_url = f"{reader_url}?{parsed.query}"
    status, body = fetch_static(reader_url, timeout=timeout, use_proxy=False)
    if status != 200 or not is_privacy_document(body, provider_name, same_domain=True):
        return None
    return reader_url


def fetch_wayback(url: str, timeout: float = 20.0) -> str:
    """Return archived HTML from the closest Wayback Machine snapshot, or ''."""
    snap_url = wayback_snapshot_url(url, timeout=timeout)
    if not snap_url:
        return ""
    status, html = fetch_static(snap_url, timeout=timeout, use_proxy=False)
    if status == 200 and html:
        logger.info("using Wayback snapshot for %s -> %s", url, snap_url)
        return html
    return ""


def fetch_html(url: str, allow_headless: bool = True) -> str:
    """Fetch HTML, escalating static -> headless browser -> Wayback snapshot."""
    status, html = fetch_static(url)
    blocked = status in (0, 403, 429, 503) or len(html) < 2000
    proxy_available = bool(httpx_proxy()) and crawl_proxy_mode() == "fallback"
    if blocked and proxy_available:
        proxy_status, proxy_html = fetch_static(url, force_proxy=True)
        if proxy_status and proxy_html:
            status, html = proxy_status, proxy_html
            blocked = status in (0, 403, 429, 503) or len(html) < 2000
    if blocked and allow_headless:
        logger.info("escalating to headless browser for %s (static status=%s)", url, status)
        try:
            rendered = fetch_rendered(url, use_proxy=crawl_proxy_mode() == "always")
            if len(rendered) >= 2000:
                return rendered
            html = rendered or html
        except Exception as exc:  # noqa: BLE001
            logger.warning("headless fetch failed for %s: %s", url, exc)
        if proxy_available:
            try:
                rendered = fetch_rendered(url, use_proxy=True)
                if len(rendered) >= 2000:
                    return rendered
                html = rendered or html
            except Exception as exc:  # noqa: BLE001
                logger.warning("proxied headless fetch failed for %s: %s", url, exc)
    # Tier-2 unblocker API, if configured (handles rotation + rendering + CAPTCHA).
    if not html or len(html) < 2000:
        via_api = fetch_via_unblocker(url)
        if via_api:
            return via_api
    # Last resort: an archived copy sidesteps live bot-blocking entirely.
    if not html or len(html) < 2000:
        archived = fetch_wayback(url)
        if archived:
            return archived
    return html


# ── OTA lookup ────────────────────────────────────────────────────────────────

def ota_declaration(provider_name: str) -> dict | None:
    """Fetch an OTA Privacy Policy declaration for a provider, if one exists."""
    for name in ota_name_candidates(provider_name):
        quoted = urllib.parse.quote(name)
        for col in OTA_COLLECTIONS:
            url = OTA_RAW.format(col=col, name=quoted)
            status, body = fetch_static(url, timeout=10.0, use_proxy=False)
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
        self,
        provider_name: str,
        domain: str | None,
        override_url: str | None = None,
        *,
        exclude_urls: set[str] | None = None,
        prefer_pdf: bool = False,
        require_validation: bool = False,
        search_timeout: float = 20.0,
        max_validation_candidates: int = 5,
        allow_site_discovery: bool = True,
    ) -> SourceCandidate | None:
        """Pick the best source URL for a provider without fetching its text."""
        if override_url:
            return SourceCandidate(override_url, "override", 1.0, notes="user-confirmed")

        pp = ota_declaration(provider_name) if not exclude_urls else None
        if pp:
            conf = 0.9 if not pp.get("executeClientScripts") else 0.88
            return SourceCandidate(pp["fetch"], "ota", conf, select=pp.get("select"),
                                   notes="Open Terms Archive declaration")

        searched = self._search_candidate(
            provider_name,
            domain,
            exclude_urls=exclude_urls,
            prefer_pdf=prefer_pdf,
            require_validation=require_validation,
            search_timeout=search_timeout,
            max_validation_candidates=max_validation_candidates,
        )
        if searched:
            return searched
        if prefer_pdf or not allow_site_discovery:
            return None

        if domain:
            excluded = {value.rstrip("/") for value in (exclude_urls or set())}
            html = fetch_html(f"https://www.{domain}", self.allow_headless)
            if html:
                cands = [
                    candidate
                    for candidate in discover_links(html, f"https://www.{domain}", domain)
                    if candidate[1].rstrip("/") not in excluded
                ]
                if cands:
                    score, url = cands[0]
                    # strong path match on same domain -> high confidence
                    conf = 0.8 if score >= 8 and _PRIVACY_PATH.search(url) else min(0.5 + 0.05 * score, 0.7)
                    return SourceCandidate(url, "discovery", round(conf, 2),
                                           notes=f"footer/link match (score {score})")

            sm = self._sitemap_candidate(domain)
            if sm and sm.url.rstrip("/") not in excluded:
                return sm
        return None

    def _search_candidate(
        self,
        provider_name: str,
        domain: str | None,
        *,
        exclude_urls: set[str] | None = None,
        prefer_pdf: bool = False,
        require_validation: bool = False,
        search_timeout: float = 20.0,
        max_validation_candidates: int = 5,
    ) -> SourceCandidate | None:
        """Find and validate an official privacy page when site discovery fails."""
        expected_domain = registrable_domain(domain or "")
        excluded = {value.rstrip("/") for value in (exclude_urls or set())}
        ranked: list[tuple[int, str]] = []
        queries = [
            f"site:{domain} privacy" if domain else "",
            f'"{provider_name}" "privacy policy"',
            f'"{provider_name}" "privacy notice" filetype:pdf',
        ]
        seen: set[str] = set()
        for query in filter(None, queries):
            try:
                with httpx.Client(
                    headers=BROWSER_HEADERS,
                    follow_redirects=True,
                    timeout=search_timeout,
                ) as client:
                    response = client.get(YAHOO_SEARCH, params={"p": query})
                if response.status_code != 200:
                    continue
            except httpx.HTTPError:
                continue
            for title, url in search_result_links(response.text):
                if url in seen or url.rstrip("/") in excluded:
                    continue
                seen.add(url)
                candidate_domain = registrable_domain(url)
                same_domain = bool(expected_domain and candidate_domain == expected_domain)
                combined = f"{title} {url}".casefold()
                if "privacy" not in combined:
                    continue
                if _NARROW_POLICY_RESULT.search(combined):
                    continue
                brand_match = any(token in combined for token in _company_tokens(provider_name))
                if not same_domain and not brand_match:
                    continue
                score = (8 if same_domain else 0) + (3 if "privacy policy" in combined else 1)
                is_pdf = url.lower().split("?", 1)[0].endswith(".pdf")
                if prefer_pdf and not is_pdf:
                    continue
                if prefer_pdf and not same_domain:
                    continue
                if is_pdf:
                    score += 6 if prefer_pdf else 1
                ranked.append((score, url))

        ordered = sorted(ranked, reverse=True)
        for score, url in ordered:
            is_pdf = url.lower().split("?", 1)[0].endswith(".pdf")
            if (
                expected_domain
                and registrable_domain(url) == expected_domain
                and score >= 9
                and _PRIVACY_PATH.search(url)
                and not is_pdf
                and not require_validation
            ):
                return SourceCandidate(
                    url,
                    "search",
                    0.8,
                    notes="official-domain indexed privacy document",
                )
        if ordered and not prefer_pdf and not require_validation:
            score, url = ordered[0]
            if score >= 3 and _PRIVACY_PATH.search(url):
                return SourceCandidate(
                    url,
                    "search",
                    0.75,
                    notes="brand-matched indexed privacy document",
                )

        for score, url in ordered[:max_validation_candidates]:
            try:
                with open_client(search_timeout) as client:
                    with client.stream("GET", url) as response:
                        content_length = int(response.headers.get("content-length") or 0)
                        if content_length > 10 * 1024 * 1024:
                            continue
                        body = bytearray()
                        for chunk in response.iter_bytes(256 * 1024):
                            body.extend(chunk)
                            if len(body) > 10 * 1024 * 1024:
                                break
                        content = bytes(body)
            except httpx.HTTPError:
                continue
            same_domain = bool(expected_domain and registrable_domain(url) == expected_domain)
            if (
                not require_validation
                and response.status_code in (401, 403, 429, 451)
                and same_domain
                and _PRIVACY_PATH.search(url)
            ):
                return SourceCandidate(
                    url,
                    "search",
                    0.8,
                    notes=f"official-domain privacy result; live access restricted (HTTP {response.status_code})",
                )
            if response.status_code >= 400 or len(content) < 500 or len(content) > 10 * 1024 * 1024:
                continue
            content_type = response.headers.get("content-type", "")
            response_url = str(response.url)
            document_is_pdf = (
                content.startswith(b"%PDF")
                or "pdf" in content_type.casefold()
                or response_url.lower().split("?", 1)[0].endswith(".pdf")
            )
            if require_validation and not document_is_pdf:
                validated_html = validate_policy_html(
                    content.decode(response.encoding or "utf-8", "ignore")
                )
                if not validated_html:
                    continue
                text = extract_text(validated_html)
            else:
                text = privacy_document_text(content, content_type, response_url)
            if not is_privacy_document(text, provider_name, same_domain=same_domain):
                continue
            confidence = 0.84 if same_domain else 0.76
            return SourceCandidate(
                str(response.url),
                "search",
                confidence,
                notes=f"validated public search result (score {score})",
            )
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
                if (
                    _PRIVACY_PATH.search(loc)
                    and not _NARROW_POLICY_RESULT.search(loc)
                    and registrable_domain(loc) == domain
                ):
                    return SourceCandidate(loc, "sitemap", 0.6, notes="sitemap entry")
        return None

    def resolve(
        self, provider_name: str, domain: str | None, override_url: str | None = None
    ) -> ResolvedSource | None:
        """Resolve and fetch the current policy source for a provider."""
        cand = self.resolve_candidate(provider_name, domain, override_url)
        if not cand:
            return None
        try:
            with open_client(30.0) as client:
                response = client.get(cand.url)
        except httpx.HTTPError:
            response = None
        if response is not None and response.status_code < 400:
            text = privacy_document_text(
                response.content, response.headers.get("content-type", ""), str(response.url)
            )
            resolved_url = str(response.url)
        else:
            html = fetch_html(cand.url, self.allow_headless)
            text = extract_text(html, cand.select) if html else ""
            resolved_url = cand.url
        same_domain = bool(domain and registrable_domain(resolved_url) == registrable_domain(domain))
        if not is_privacy_document(text, provider_name, same_domain=same_domain):
            return None
        return ResolvedSource(
            url=resolved_url,
            text=text,
            content_hash=content_hash(text),
            confidence=cand.confidence,
            strategy=cand.strategy,
            select=cand.select,
            notes=cand.notes,
        )
