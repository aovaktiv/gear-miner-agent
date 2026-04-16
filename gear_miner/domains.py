from __future__ import annotations

from typing import Iterable, Sequence, Tuple
from urllib.parse import urlparse


def normalize_domain(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1].split(":")[0]
    return host.lstrip(".")


def parse_domain_list(raw: str | Iterable[str] | None) -> Tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = list(raw)

    normalized = []
    seen = set()
    for part in parts:
        domain = normalize_domain(str(part))
        if not domain or domain in seen:
            continue
        seen.add(domain)
        normalized.append(domain)
    return tuple(normalized)


def host_matches_domain(host: str, domain: str) -> bool:
    normalized_host = normalize_domain(host)
    normalized_domain = normalize_domain(domain)
    if not normalized_host or not normalized_domain:
        return False
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def url_host(url: str) -> str:
    return normalize_domain(urlparse(url).netloc)


def is_url_allowed(
    url: str,
    allow_domains: Sequence[str] = (),
    block_domains: Sequence[str] = (),
    default_host: str | None = None,
) -> bool:
    host = url_host(url)
    if not host:
        return False

    if any(host_matches_domain(host, domain) for domain in block_domains):
        return False

    if allow_domains:
        return any(host_matches_domain(host, domain) for domain in allow_domains)

    if default_host:
        return host_matches_domain(host, default_host)

    return True
