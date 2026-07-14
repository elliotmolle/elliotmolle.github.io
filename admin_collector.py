#!/usr/bin/env python3
"""Energy-only feed collector for Nexus.

Default config shape:
{
  "defaults": {
    "topic": "Energy",
    "category": "General",
    "impact": "Low",
    "sentiment": "Neutral"
  },
  "sources": [
    {
      "name": "Example Energy Feed",
      "url": "https://example.com/feed.xml",
      "topic": "Energy",
      "category": "Market Updates",
      "enabled": true,
      "format": "rss"
    }
  ]
}

Supported source formats: RSS 2.0, RDF-style RSS, Atom, and JSON item lists.
JSON feeds may be either a top-level array of items or an object with an
``items``/``entries`` array. Item keys are normalized from common aliases.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import email.utils
import gzip
import hashlib
import html
import io
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = REPO_ROOT / "nexus" / "collector_sources.json"
DEFAULT_OUTPUT = REPO_ROOT / "nexus" / "news_data.json"
DEFAULT_CONTRACT = REPO_ROOT / "nexus" / "news_quality_contract.json"

DEFAULT_CONTRACT_DATA: dict[str, Any] = {
    "schema_version": "1.0.0",
    "required_fields": [
        "id",
        "title",
        "summary",
        "source",
        "url",
        "timestamp",
        "topic",
        "category",
        "impact",
        "sentiment",
    ],
    "optional_fields": [
        "source_tier",
        "primary_source",
        "claims",
        "citations",
        "tickers",
        "entities",
        "data_as_of",
        "editorial_notes",
    ],
    "allowed_values": {
        "impact": ["Low", "Medium", "High"],
        "sentiment": ["Negative", "Neutral", "Positive"],
        "topic": ["Energy", "Gaming", "Music Production", "Computer Science", "Mathematics"],
        "category_global": [
            "AI",
            "Audio Tech",
            "Company News",
            "Competitive",
            "Corporate",
            "Data Science",
            "General",
            "Grid Impacts",
            "Infrastructure",
            "Large Loads",
            "Market Updates",
            "Nuclear Policy",
            "Nuclear Technology",
            "Policy & Regulation",
            "Project Finance",
            "Releases",
            "Research",
            "Reviews",
            "RTOs / ISOs",
            "Safety",
            "Security",
            "Small Energy Companies",
            "Systems",
            "Utilities",
        ],
        "categories_by_topic": {
            "Energy": [
                "Company News",
                "Corporate",
                "General",
                "Grid Impacts",
                "Large Loads",
                "Market Updates",
                "Nuclear Policy",
                "Nuclear Technology",
                "Policy & Regulation",
                "Project Finance",
                "RTOs / ISOs",
                "Safety",
                "Small Energy Companies",
                "Utilities",
            ],
            "Gaming": ["Competitive", "General", "Infrastructure", "Releases", "Reviews"],
            "Music Production": ["Audio Tech", "General", "Releases", "Reviews"],
            "Computer Science": ["AI", "General", "Infrastructure", "Research", "Security", "Systems"],
            "Mathematics": ["Data Science", "General", "Research"],
        },
    },
    "freshness": {"stale_after_hours": 72, "future_grace_minutes": 15},
    "summary_rules": {
        "placeholder_phrases": [
            "this is a detailed summary regarding the latest updates from",
            "the impact on",
            "is currently being analyzed by experts",
        ]
    },
    "entity_disambiguation": {
        "ambiguous_terms": ["Terra", "Terra Energy"],
        "specific_entities": ["TerraPower", "Terrestrial Energy"],
    },
    "source_registry": [
        {
            "name": "U.S. Nuclear Regulatory Commission (NRC)",
            "tier": "primary",
            "primary_source": True,
            "canonical_url": "https://www.nrc.gov/",
            "coverage": "Regulatory notices, reactor oversight, licensing, and safety communications.",
        },
        {
            "name": "U.S. Department of Energy – Office of Nuclear Energy",
            "tier": "primary",
            "primary_source": True,
            "canonical_url": "https://www.energy.gov/ne",
            "coverage": "Federal nuclear energy policy, programs, funding, and technical updates.",
        },
        {
            "name": "DOE National Laboratories",
            "tier": "primary",
            "primary_source": True,
            "canonical_url": "https://www.energy.gov/lab-locator",
            "coverage": "Lab research from INL, ORNL, PNNL, SNL, ANL, and similar DOE labs.",
        },
        {
            "name": "SEC EDGAR",
            "tier": "primary",
            "primary_source": True,
            "canonical_url": "https://www.sec.gov/edgar",
            "coverage": "Public company filings, material disclosures, and issuer statements.",
        },
        {
            "name": "Company Investor Relations",
            "tier": "primary",
            "primary_source": True,
            "canonical_url": None,
            "coverage": "Issuer press releases, earnings materials, and investor presentations.",
            "note": "Company IR pages are issuer-specific; record the actual issuer domain in item metadata.",
        },
        {
            "name": "Reuters",
            "tier": "secondary",
            "primary_source": False,
            "canonical_url": "https://www.reuters.com/",
            "coverage": "General market coverage and independently reported energy / nuclear news.",
        },
        {
            "name": "World Nuclear News",
            "tier": "trade",
            "primary_source": False,
            "canonical_url": "https://world-nuclear-news.org/",
            "coverage": "Industry trade reporting focused on nuclear power and fuel cycle developments.",
        },
        {
            "name": "NucNet",
            "tier": "trade",
            "primary_source": False,
            "canonical_url": "https://www.nucnet.org/",
            "coverage": "European and global nuclear industry reporting.",
        },
        {
            "name": "Nuclear Engineering International",
            "tier": "trade",
            "primary_source": False,
            "canonical_url": "https://www.neimagazine.com/",
            "coverage": "Nuclear engineering trade reporting and analysis.",
        },
        {
            "name": "ANS Nuclear Newswire",
            "tier": "trade",
            "primary_source": False,
            "canonical_url": "https://www.ans.org/news/",
            "coverage": "American Nuclear Society news and industry updates.",
        },
    ],
}

ALLOWED_TOPICS = {"Energy", "Gaming", "Music Production", "Computer Science", "Mathematics", "Jiu-Jitsu", "UFC", "Rocket League"}
BLOCKED_TOPICS = {"Admin", "Personal"}
ALLOWED_FORMATS = {"rss", "rdf", "atom", "json"}
TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAM_NAMES = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "mkt_tok",
    "ref",
    "ref_src",
    "source",
    "src",
    "trk",
    "yclid",
}
HTTP_SCHEMES = {"http", "https"}
PLACEHOLDER_URLS = {"", "#", "/", "about:blank", "javascript:void(0)"}
DEFAULT_TITLE_LIMIT = 240
DEFAULT_SUMMARY_LIMIT = 1200
DEFAULT_SOURCE_LIMIT = 160
DEFAULT_EDITORIAL_LIMIT = 600
DEFAULT_CLAIMS_LIMIT = 10
DEFAULT_CITATIONS_LIMIT = 5
DEFAULT_ENTITIES_LIMIT = 20
DEFAULT_TICKERS_LIMIT = 20


class ConfigError(Exception):
    pass


class CollectionError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in {"br", "p", "div", "li", "tr", "td", "section", "article", "header", "footer", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag in {"p", "div", "li", "tr", "section", "article", "header", "footer"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data:
            self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        return

    def text(self) -> str:
        text = html.unescape("".join(self.parts))
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


@dataclass
class SourceConfig:
    index: int
    name: str
    feed_url: str
    topic: str
    category: str
    enabled: bool
    format: str | None = None
    source_tier: str | None = None
    primary_source: bool | None = None
    impact: str = "Low"
    sentiment: str = "Neutral"
    max_items: int | None = None
    max_age_hours: int | None = None
    entities: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    editorial_notes: str | None = None
    data_as_of: str | None = None


@dataclass
class SourceContext:
    name: str
    feed_url: str
    topic: str
    category: str
    source_tier: str | None
    primary_source: bool | None
    impact: str
    sentiment: str
    max_age_hours: int
    editorial_notes: str | None
    data_as_of: str | None
    entities: list[str]
    tickers: list[str]
    citations: list[str]
    claims: list[str]
    base_url: str
    format: str | None
    from_existing: bool = False


@dataclass
class FetchOutcome:
    source: SourceConfig
    context: SourceContext
    raw_count: int = 0
    parsed_count: int = 0
    kept_count: int = 0
    skipped_count: int = 0
    error: str | None = None
    parser_kind: str | None = None


@dataclass
class CollectionStats:
    total_sources: int = 0
    enabled_sources: int = 0
    skipped_sources: int = 0
    successful_sources: int = 0
    failed_sources: int = 0
    raw_items: int = 0
    normalized_items: int = 0
    merged_existing: int = 0
    deduped_items: int = 0
    final_items: int = 0


def repo_relative(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path)


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def deep_copy_contract() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONTRACT_DATA)


def load_contract(path: Path) -> dict[str, Any]:
    if not path.exists():
        return deep_copy_contract()
    try:
        raw = load_json_file(path)
    except Exception as exc:
        raise ConfigError(f"Failed to read contract {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Contract must be a JSON object: {path}")
    contract = deep_copy_contract()
    contract.update(raw)
    if "allowed_values" in raw and isinstance(raw["allowed_values"], dict):
        merged = copy.deepcopy(DEFAULT_CONTRACT_DATA["allowed_values"])
        merged.update(raw["allowed_values"])
        contract["allowed_values"] = merged
    for key in ("required_fields", "optional_fields", "allowed_values", "freshness"):
        if key not in contract:
            raise ConfigError(f"Contract is missing required field {key!r}: {path}")
    if not isinstance(contract["required_fields"], list) or not isinstance(contract["optional_fields"], list):
        raise ConfigError(f"Contract field lists must be arrays: {path}")
    if not isinstance(contract["allowed_values"], dict) or not isinstance(contract["freshness"], dict):
        raise ConfigError(f"Contract allowed_values and freshness must be objects: {path}")
    return contract


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip() + "…"


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_html(value: Any, limit: int | None = None) -> str:
    if not isinstance(value, str):
        return ""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(value)
        extractor.close()
        text = extractor.text()
    except Exception:
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = normalize_whitespace(text)
    text = re.sub(r"(?i)\b(read more|click here|subscribe|sign up|cookie policy|privacy policy)\b", " ", text)
    text = re.sub(r"\s+([,;:!?])", r"\1", text)
    text = re.sub(r"([.!?])\s+([.!?])", r"\1", text)
    text = normalize_whitespace(text)
    if limit is not None:
        text = shorten(text, limit)
    return text


def lower_key(value: str) -> str:
    return normalize_whitespace(html.unescape(value)).casefold()


def coerce_bool(value: Any, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in {"true", "yes", "1", "on"}:
            return True
        if token in {"false", "no", "0", "off"}:
            return False
    raise ConfigError(f"Expected boolean, got {value!r}")


def coerce_int(value: Any, field_name: str, minimum: int = 0) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except Exception as exc:
        raise ConfigError(f"Expected integer for {field_name}, got {value!r}") from exc
    if parsed < minimum:
        raise ConfigError(f"{field_name} must be >= {minimum}, got {parsed}")
    return parsed


def parse_text_list(value: Any, *, limit: int | None = None, max_item_len: int | None = None) -> list[str]:
    if value is None or value == "":
        return []
    items: list[str]
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = [str(part) for part in value if part is not None and str(part).strip()]
    else:
        raise ConfigError(f"Expected string or array, got {type(value).__name__}")
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = strip_html(item, max_item_len).strip()
        if not cleaned:
            continue
        key = lower_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if limit is not None and len(out) >= limit:
            break
    return out


def parse_url_list(value: Any, *, limit: int | None = None) -> list[str]:
    urls = parse_text_list(value, limit=limit, max_item_len=500)
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        canonical = canonicalize_url(url)
        if not canonical:
            continue
        key = canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(canonical)
    return out


def normalize_source_tier(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ConfigError(f"source_tier must be a string, got {type(value).__name__}")
    return normalize_whitespace(value).casefold()


def normalize_category(value: Any, topic: str, contract: dict[str, Any]) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ConfigError(f"category must be a string, got {type(value).__name__}")
    cleaned = normalize_whitespace(html.unescape(value))
    allowed_global = contract["allowed_values"]["category_global"]
    allowed_topic = contract["allowed_values"]["categories_by_topic"].get(topic, allowed_global)
    alias_map = {item.casefold(): item for item in allowed_global}
    alias_map.update({
        "market update": "Market Updates",
        "market updates": "Market Updates",
        "grid impact": "Grid Impacts",
        "grid impacts": "Grid Impacts",
        "large load": "Large Loads",
        "large loads": "Large Loads",
        "rto": "RTOs / ISOs",
        "isos": "RTOs / ISOs",
        "rto / iso": "RTOs / ISOs",
        "rto/iso": "RTOs / ISOs",
        "nuclear technology": "Nuclear Technology",
        "nuclear policy": "Nuclear Policy",
        "policy and regulation": "Policy & Regulation",
        "policy & regulation": "Policy & Regulation",
        "small energy company": "Small Energy Companies",
        "small energy companies": "Small Energy Companies",
        "company news": "Company News",
        "corporate": "Corporate",
        "general": "General",
        "utilities": "Utilities",
        "safety": "Safety",
        "security": "Security",
        "project finance": "Project Finance",
    })
    normalized = alias_map.get(cleaned.casefold(), cleaned)
    if normalized in allowed_topic or normalized in allowed_global:
        return normalized
    return None


def normalize_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str):
        raw = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        else:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                try:
                    dt = email.utils.parsedate_to_datetime(value)
                except Exception:
                    dt = None  # type: ignore[assignment]
            if dt is None and raw.isdigit():
                epoch = float(raw)
                if len(raw) >= 13:
                    epoch = epoch / 1000.0
                dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    else:
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonicalize_url(raw_url: Any, base_url: str | None = None) -> str | None:
    if not isinstance(raw_url, str):
        return None
    value = normalize_whitespace(html.unescape(raw_url))
    if not value:
        return None
    if value.casefold() in PLACEHOLDER_URLS:
        return None
    if base_url:
        value = urljoin(base_url, value)
    parts = urlsplit(value)
    if parts.scheme not in HTTP_SCHEMES or not parts.netloc:
        return None
    if parts.scheme == "http" or parts.scheme == "https":
        scheme = parts.scheme.lower()
    else:
        return None
    hostname = parts.hostname.lower() if parts.hostname else ""
    if not hostname:
        return None
    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        netloc = hostname
    elif port:
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname
    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        key_key = key.casefold()
        if key_key.startswith(TRACKING_PARAM_PREFIXES) or key_key in TRACKING_PARAM_NAMES:
            continue
        query_items.append((key, value))
    query_items.sort(key=lambda kv: (kv[0].casefold(), kv[1]))
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def extract_hostname(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    return parts.hostname.lower() if parts.hostname else ""


def stable_id(source: str, title: str, url: str) -> str:
    payload = "\n".join([lower_key(source), lower_key(title), url.casefold()])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"energy-{digest[:16]}"


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return value
        elif value not in (None, "", [], (), {}):
            return value
    return None


def source_name_from_registry(contract: dict[str, Any], name: str, url: str) -> tuple[str | None, bool | None]:
    hostname = extract_hostname(url)
    for entry in contract.get("source_registry", []):
        if not isinstance(entry, dict):
            continue
        entry_name = entry.get("name")
        canonical = entry.get("canonical_url")
        if isinstance(entry_name, str) and entry_name.casefold() == name.casefold():
            return (str(entry.get("tier")) if entry.get("tier") is not None else None, entry.get("primary_source"))
        if isinstance(canonical, str) and extract_hostname(canonical) and hostname == extract_hostname(canonical):
            return (str(entry.get("tier")) if entry.get("tier") is not None else None, entry.get("primary_source"))
    return None, None


def source_hints_by_name(contract: dict[str, Any], name: str, url: str) -> dict[str, Any]:
    hostname = extract_hostname(url)
    for entry in contract.get("source_registry", []):
        if not isinstance(entry, dict):
            continue
        entry_name = entry.get("name")
        canonical = entry.get("canonical_url")
        match_name = isinstance(entry_name, str) and entry_name.casefold() == name.casefold()
        match_host = isinstance(canonical, str) and hostname and extract_hostname(canonical) == hostname
        if match_name or match_host:
            return {
                "source_tier": normalize_source_tier(entry.get("tier")),
                "primary_source": entry.get("primary_source") if isinstance(entry.get("primary_source"), bool) else None,
            }
    return {}


def parse_config(path: Path, contract: dict[str, Any]) -> list[SourceConfig]:
    if not path.exists():
        raise ConfigError(
            f"Configuration file not found: {path}\n"
            "Create a JSON config with a top-level 'sources' array (or 'feeds'/'items' alias), "
            "or pass --config to a populated file."
        )
    try:
        raw = load_json_file(path)
    except Exception as exc:
        raise ConfigError(f"Failed to read config {path}: {exc}") from exc

    defaults: dict[str, Any] = {}
    source_entries: list[Any]
    if isinstance(raw, list):
        source_entries = raw
    elif isinstance(raw, dict):
        for key in ("defaults", "settings"):
            if isinstance(raw.get(key), dict):
                defaults.update(raw[key])
        for key in ("sources", "feeds", "items"):
            if isinstance(raw.get(key), list):
                source_entries = raw[key]
                break
        else:
            raise ConfigError(
                f"Config must provide a top-level 'sources' array (or 'feeds'/'items' alias): {path}"
            )
    else:
        raise ConfigError(f"Config must be a JSON object or array of sources: {path}")

    sources: list[SourceConfig] = []
    for index, raw_source in enumerate(source_entries):
        if not isinstance(raw_source, dict):
            raise ConfigError(f"Source entry #{index} must be an object, got {type(raw_source).__name__}")

        merged = copy.deepcopy(defaults)
        merged.update(raw_source)
        url = first_nonempty(
            merged.get("url"),
            merged.get("feed_url"),
            merged.get("feedUrl"),
            merged.get("href"),
        )
        if not isinstance(url, str) or not url.strip():
            raise ConfigError(f"Source entry #{index} is missing a feed URL ('url').")
        feed_url = canonicalize_url(url.strip())
        if not feed_url:
            raise ConfigError(f"Source entry #{index} must use an http(s) feed URL: {url!r}")

        enabled = coerce_bool(merged.get("enabled", merged.get("active", True)), default=True)
        if enabled is None:
            enabled = True

        topic_raw = first_nonempty(merged.get("topic"), defaults.get("topic"))
        if not isinstance(topic_raw, str) or not topic_raw.strip():
            raise ConfigError(f"Source entry #{index} is missing required field 'topic'.")
        topic = normalize_whitespace(html.unescape(topic_raw))
        if topic.casefold() in {value.casefold() for value in BLOCKED_TOPICS}:
            sources.append(
                SourceConfig(
                    index=index,
                    name=normalize_whitespace(str(first_nonempty(merged.get("name"), merged.get("title"), feed_url))),
                    feed_url=feed_url,
                    topic=topic,
                    category=normalize_whitespace(str(first_nonempty(merged.get("category"), defaults.get("category"), "General"))),
                    enabled=False,
                )
            )
            continue
        if topic not in ALLOWED_TOPICS:
            sources.append(
                SourceConfig(
                    index=index,
                    name=normalize_whitespace(str(first_nonempty(merged.get("name"), merged.get("title"), feed_url))),
                    feed_url=feed_url,
                    topic=topic,
                    category=normalize_whitespace(str(first_nonempty(merged.get("category"), defaults.get("category"), "General"))),
                    enabled=False,
                )
            )
            continue

        source_name = normalize_whitespace(str(first_nonempty(merged.get("name"), merged.get("title"), feed_url)))
        category_value = first_nonempty(merged.get("category"), defaults.get("category"), "General")
        category = normalize_category(category_value, topic, contract)
        if category is None:
            raise ConfigError(f"Source entry #{index} has invalid category {category_value!r}")
        source_tier = normalize_source_tier(first_nonempty(merged.get("source_tier"), merged.get("sourceTier"), merged.get("tier"), defaults.get("source_tier")))
        primary_source = merged.get("primary_source")
        if primary_source is None:
            primary_source = merged.get("primarySource")
        if primary_source is None:
            primary_source = merged.get("isPrimarySource")
        if isinstance(primary_source, bool):
            parsed_primary = primary_source
        elif primary_source is None:
            parsed_primary = None
        else:
            parsed_primary = coerce_bool(primary_source)
        impact = normalize_whitespace(str(first_nonempty(merged.get("impact"), defaults.get("impact"), "Low")))
        if impact not in contract["allowed_values"]["impact"]:
            raise ConfigError(
                f"Source entry #{index} has invalid impact {impact!r}; allowed: {contract['allowed_values']['impact']}"
            )
        sentiment = normalize_whitespace(str(first_nonempty(merged.get("sentiment"), defaults.get("sentiment"), "Neutral")))
        if sentiment not in contract["allowed_values"]["sentiment"]:
            raise ConfigError(
                f"Source entry #{index} has invalid sentiment {sentiment!r}; allowed: {contract['allowed_values']['sentiment']}"
            )

        raw_format = first_nonempty(merged.get("format"), merged.get("feed_type"), merged.get("feedType"), merged.get("type"))
        if raw_format is None:
            parsed_format = None
        else:
            if not isinstance(raw_format, str):
                raise ConfigError(f"Source entry #{index} has invalid format: {raw_format!r}")
            parsed_format = normalize_whitespace(raw_format).casefold()
            if parsed_format not in ALLOWED_FORMATS:
                raise ConfigError(
                    f"Source entry #{index} has invalid format {parsed_format!r}; expected one of {sorted(ALLOWED_FORMATS)}"
                )

        max_items = coerce_int(first_nonempty(merged.get("max_items"), merged.get("maxItems")), f"source[{index}].max_items", minimum=0)
        max_age_hours = coerce_int(first_nonempty(merged.get("max_age_hours"), merged.get("maxAgeHours")), f"source[{index}].max_age_hours", minimum=0)

        entities = parse_text_list(
            first_nonempty(merged.get("entities"), merged.get("entity_hints"), merged.get("entityHints")),
            limit=DEFAULT_ENTITIES_LIMIT,
            max_item_len=80,
        )
        tickers = [
            item.upper().lstrip("$")
            for item in parse_text_list(
                first_nonempty(merged.get("tickers"), merged.get("ticker_hints"), merged.get("symbols")),
                limit=DEFAULT_TICKERS_LIMIT,
                max_item_len=20,
            )
        ]
        citations = parse_url_list(merged.get("citations"), limit=DEFAULT_CITATIONS_LIMIT)
        claims = parse_text_list(merged.get("claims"), limit=DEFAULT_CLAIMS_LIMIT, max_item_len=500)
        editorial_notes = strip_html(first_nonempty(merged.get("editorial_notes"), merged.get("editorialNotes")), DEFAULT_EDITORIAL_LIMIT) or None
        data_as_of = first_nonempty(merged.get("data_as_of"), merged.get("dataAsOf"))
        if data_as_of is not None and normalize_timestamp(data_as_of) is None:
            raise ConfigError(f"Source entry #{index} has invalid data_as_of value: {data_as_of!r}")

        hints = source_hints_by_name(contract, source_name, feed_url)
        if source_tier is None:
            source_tier = hints.get("source_tier")
        if parsed_primary is None:
            parsed_primary = hints.get("primary_source")
        if parsed_primary is None and source_tier == "primary":
            parsed_primary = True

        sources.append(
            SourceConfig(
                index=index,
                name=source_name,
                feed_url=feed_url,
                topic=topic,
                category=category,
                enabled=enabled,
                format=parsed_format,
                source_tier=source_tier,
                primary_source=parsed_primary,
                impact=impact,
                sentiment=sentiment,
                max_items=max_items,
                max_age_hours=max_age_hours,
                entities=entities,
                tickers=tickers,
                citations=citations,
                claims=claims,
                editorial_notes=editorial_notes,
                data_as_of=iso_z(normalize_timestamp(data_as_of)) if data_as_of is not None else None,
            )
        )

    return sources


class _HttpsOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme not in HTTP_SCHEMES:
            raise URLError(f"Blocked redirect to non-http(s) URL: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_http_opener() -> Any:
    return build_opener(HTTPHandler(), HTTPSHandler(context=ssl.create_default_context()), _HttpsOnlyRedirectHandler())


def fetch_http(url: str, *, timeout: float, max_bytes: int, retries: int, backoff_seconds: float, user_agent: str, verbose: bool) -> tuple[bytes, str, str]:
    opener = build_http_opener()
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, application/json, text/json, */*",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with opener.open(request, timeout=timeout) as response:
                final_url = response.geturl()
                final_scheme = urlsplit(final_url).scheme
                if final_scheme not in HTTP_SCHEMES:
                    raise CollectionError(f"Redirected to unsupported URL scheme: {final_url}")
                content_type = response.headers.get_content_type() if response.headers else ""
                content_encoding = (response.headers.get("Content-Encoding") or "").casefold()
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared = int(content_length)
                    except ValueError:
                        declared = None
                    else:
                        if declared > max_bytes:
                            raise CollectionError(f"Response too large ({declared} bytes > limit {max_bytes} bytes)")

                buffer = io.BytesIO()
                total = 0
                while True:
                    chunk = response.read(min(65536, max_bytes - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise CollectionError(f"Response too large (> {max_bytes} bytes)")
                    buffer.write(chunk)
                body = buffer.getvalue()
                if content_encoding == "gzip":
                    body = gzip.decompress(body)
                return body, final_url, content_type
        except HTTPError as exc:
            last_error = exc
            retryable = exc.code in {429, 500, 502, 503, 504}
            if not retryable or attempt >= retries:
                raise CollectionError(f"HTTP {exc.code} fetching {url}: {exc.reason}") from exc
        except (URLError, TimeoutError, OSError, CollectionError) as exc:
            last_error = exc
            if attempt >= retries:
                raise CollectionError(f"Failed to fetch {url}: {exc}") from exc
        if attempt < retries:
            delay = backoff_seconds * (2**attempt)
            if verbose:
                print(f"Retrying {url} in {delay:.1f}s (attempt {attempt + 1}/{retries})", file=sys.stderr)
            time.sleep(delay)
    assert last_error is not None
    raise CollectionError(f"Failed to fetch {url}: {last_error}")


def sniff_feed_kind(content_type: str, body: bytes, explicit_format: str | None) -> str:
    if explicit_format in ALLOWED_FORMATS:
        return explicit_format
    ct = (content_type or "").casefold()
    if "json" in ct:
        return "json"
    if "atom" in ct:
        return "atom"
    if "rss" in ct:
        return "rss"
    if "xml" in ct or ct.endswith("+xml"):
        text = body.lstrip()[:200].lstrip()
        if text.startswith(b"{") or text.startswith(b"["):
            return "json"
        if b"<feed" in body[:1000].lower():
            return "atom"
        return "rss"
    text = body.lstrip()[:200]
    if text.startswith(b"{") or text.startswith(b"["):
        return "json"
    if text.startswith(b"<"):
        if b"<feed" in body[:1000].lower():
            return "atom"
        return "rss"
    raise CollectionError(f"Unable to determine feed format from content type {content_type!r}")


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    if local_name(node.tag) == "content" and node.attrib.get("type", "").casefold() == "xhtml":
        return ET.tostring(node, encoding="unicode", method="xml")
    return "".join(node.itertext())


def find_first_child(parent: ET.Element, names: set[str]) -> ET.Element | None:
    for child in parent.iter():
        if local_name(child.tag) in names:
            return child
    return None


def find_text(parent: ET.Element | None, names: set[str]) -> str:
    if parent is None:
        return ""
    for child in parent.iter():
        if local_name(child.tag) in names:
            text = xml_text(child)
            if text.strip():
                return text
    return ""


def parse_rss_like_xml(body: bytes, final_url: str, kind: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        root = ET.fromstring(body)
    except Exception as exc:
        raise CollectionError(f"Invalid XML feed at {final_url}: {exc}") from exc

    feed_title = find_text(root, {"title"}) or None
    items: list[dict[str, Any]] = []

    if kind == "atom" or local_name(root.tag) == "feed":
        entry_nodes = [node for node in root.iter() if local_name(node.tag) == "entry"]
        for entry in entry_nodes:
            item_title = find_text(entry, {"title"})
            item_summary = find_text(entry, {"summary", "subtitle", "content"})
            item_url = ""
            for child in entry:
                if local_name(child.tag) == "link":
                    rel = child.attrib.get("rel", "alternate")
                    href = child.attrib.get("href")
                    if href and rel in {"alternate", "self", ""}:
                        item_url = href
                        if rel == "alternate" or not item_url:
                            break
            if not item_url:
                item_url = find_text(entry, {"id", "link"})
            published = find_text(entry, {"published", "updated", "modified", "date"})
            categories = [child.attrib.get("term") or xml_text(child) for child in entry if local_name(child.tag) == "category"]
            items.append(
                {
                    "title": item_title,
                    "summary": item_summary,
                    "url": item_url,
                    "timestamp": published,
                    "categories": categories,
                    "source": feed_title,
                    "raw_xml": True,
                }
            )
        return items, feed_title

    item_nodes = [node for node in root.iter() if local_name(node.tag) == "item"]
    if not item_nodes and local_name(root.tag) == "RDF":
        item_nodes = [node for node in root.iter() if local_name(node.tag) == "item"]
    for item in item_nodes:
        title_text = find_text(item, {"title"})
        link_text = find_text(item, {"link"})
        summary_text = find_text(item, {"description", "encoded", "content"})
        if not summary_text:
            summary_text = find_text(item, {"summary"})
        date_text = find_text(item, {"pubDate", "date", "updated", "published"})
        guid_text = find_text(item, {"guid", "id"})
        categories = [xml_text(child) for child in item if local_name(child.tag) == "category"]
        items.append(
            {
                "title": title_text,
                "summary": summary_text,
                "url": first_nonempty(link_text, guid_text),
                "timestamp": date_text,
                "categories": categories,
                "source": feed_title,
                "raw_xml": True,
            }
        )
    return items, feed_title


def parse_json_feed(body: bytes, final_url: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        try:
            parsed = json.loads(body.decode("utf-8"))
        except UnicodeDecodeError:
            parsed = json.loads(body.decode("utf-8-sig"))
    except Exception as exc:
        raise CollectionError(f"Invalid JSON feed at {final_url}: {exc}") from exc
    feed_title: str | None = None
    if isinstance(parsed, list):
        entries = parsed
    elif isinstance(parsed, dict):
        feed_title = first_nonempty(parsed.get("title"), parsed.get("name"), parsed.get("source"))
        for key in ("items", "entries", "articles", "data", "results"):
            value = parsed.get(key)
            if isinstance(value, list):
                entries = value
                break
        else:
            raise CollectionError(
                f"JSON feed at {final_url} must be a top-level list or an object with an 'items' array."
            )
    else:
        raise CollectionError(f"JSON feed at {final_url} must be an array or object.")

    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized.append(
            {
                "title": first_nonempty(entry.get("title"), entry.get("name")),
                "summary": first_nonempty(entry.get("summary"), entry.get("description"), entry.get("content"), entry.get("body")),
                "url": first_nonempty(entry.get("url"), entry.get("link"), entry.get("canonical_url"), entry.get("canonicalUrl"), entry.get("id")),
                "timestamp": first_nonempty(entry.get("timestamp"), entry.get("published"), entry.get("pubDate"), entry.get("updated"), entry.get("date")),
                "topic": first_nonempty(entry.get("topic")),
                "category": first_nonempty(entry.get("category"), entry.get("categories")),
                "impact": first_nonempty(entry.get("impact")),
                "sentiment": first_nonempty(entry.get("sentiment")),
                "source": first_nonempty(entry.get("source")),
                "source_tier": first_nonempty(entry.get("source_tier"), entry.get("sourceTier")),
                "primary_source": first_nonempty(entry.get("primary_source"), entry.get("primarySource"), entry.get("isPrimarySource")),
                "claims": entry.get("claims"),
                "citations": entry.get("citations"),
                "tickers": entry.get("tickers"),
                "entities": entry.get("entities"),
                "data_as_of": first_nonempty(entry.get("data_as_of"), entry.get("dataAsOf")),
                "editorial_notes": first_nonempty(entry.get("editorial_notes"), entry.get("editorialNotes")),
            }
        )
    return normalized, feed_title


def parse_feed(body: bytes, final_url: str, content_type: str, explicit_format: str | None) -> tuple[list[dict[str, Any]], str | None, str]:
    kind = sniff_feed_kind(content_type, body, explicit_format)
    if kind == "json":
        items, feed_title = parse_json_feed(body, final_url)
        return items, feed_title, kind
    items, feed_title = parse_rss_like_xml(body, final_url, kind)
    return items, feed_title, kind


def normalize_output_value(value: Any, limit: int) -> str:
    return shorten(strip_html(value, limit), limit)


def normalize_optional_value(value: Any, limit: int) -> str | None:
    text = strip_html(value, limit).strip()
    return text or None


def normalize_string_list(value: Any, *, limit: int, item_limit: int) -> list[str]:
    return parse_text_list(value, limit=item_limit, max_item_len=limit)


def validate_category(topic: str, category: str, contract: dict[str, Any]) -> bool:
    allowed_global = set(contract["allowed_values"]["category_global"])
    allowed_topic = set(contract["allowed_values"]["categories_by_topic"].get(topic, []))
    return category in allowed_global or category in allowed_topic


def validate_output_item(item: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required = contract["required_fields"]
    missing = [field for field in required if field not in item or item.get(field) in (None, "")]
    if missing:
        issues.append(f"missing required fields: {', '.join(missing)}")

    if item.get("impact") not in contract["allowed_values"]["impact"]:
        issues.append(f"invalid impact: {item.get('impact')!r}")
    if item.get("sentiment") not in contract["allowed_values"]["sentiment"]:
        issues.append(f"invalid sentiment: {item.get('sentiment')!r}")
    if item.get("topic") not in contract["allowed_values"]["topic"]:
        issues.append(f"invalid topic: {item.get('topic')!r}")
    if item.get("category") and not validate_category(item["topic"], item["category"], contract):
        issues.append(f"invalid category for topic {item['topic']!r}: {item['category']!r}")
    if not isinstance(item.get("primary_source"), (bool, type(None))):
        issues.append("primary_source must be boolean or null")
    if not isinstance(item.get("source_tier"), (str, type(None))):
        issues.append("source_tier must be string or null")
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        issues.append("title must be non-empty text")
    if not isinstance(item.get("summary"), str) or not item["summary"].strip():
        issues.append("summary must be non-empty text")
    if not isinstance(item.get("source"), str) or not item["source"].strip():
        issues.append("source must be non-empty text")
    if not isinstance(item.get("url"), str) or canonicalize_url(item["url"]) is None:
        issues.append("url must be a valid http(s) URL")
    if normalize_timestamp(item.get("timestamp")) is None:
        issues.append("timestamp must be an ISO/RFC date with timezone")
    for field_name in ("claims", "citations", "entities", "tickers"):
        if field_name in item and not isinstance(item[field_name], list):
            issues.append(f"{field_name} must be an array")
    if "citations" in item:
        for citation in item["citations"]:
            if not isinstance(citation, str) or canonicalize_url(citation) is None:
                issues.append("citations must contain http(s) URLs")
                break
    if "data_as_of" in item and item["data_as_of"] not in (None, "") and normalize_timestamp(item["data_as_of"]) is None:
        issues.append("data_as_of must be a timezone-aware timestamp")
    return issues


def build_source_context(source: SourceConfig, default_max_age_hours: int) -> SourceContext:
    data_as_of = source.data_as_of
    if data_as_of is None and source.max_age_hours is not None and source.max_age_hours >= 0:
        data_as_of = None
    return SourceContext(
        name=source.name,
        feed_url=source.feed_url,
        topic=source.topic,
        category=source.category,
        source_tier=source.source_tier,
        primary_source=source.primary_source,
        impact=source.impact,
        sentiment=source.sentiment,
        max_age_hours=source.max_age_hours if source.max_age_hours is not None else default_max_age_hours,
        editorial_notes=source.editorial_notes,
        data_as_of=data_as_of,
        entities=source.entities,
        tickers=source.tickers,
        citations=source.citations,
        claims=source.claims,
        base_url=source.feed_url,
        format=source.format,
    )


def build_existing_context(item: dict[str, Any], contract: dict[str, Any]) -> SourceContext:
    name = normalize_optional_value(first_nonempty(item.get("source"), item.get("feed_source")), DEFAULT_SOURCE_LIMIT) or "Existing Feed"
    url = canonicalize_url(first_nonempty(item.get("url"), item.get("canonical_url"), item.get("canonicalUrl"))) or ""
    source_tier = normalize_source_tier(item.get("source_tier"))
    primary_source = item.get("primary_source")
    if not isinstance(primary_source, bool):
        primary_source = None
    topic = normalize_whitespace(str(first_nonempty(item.get("topic"), "Energy")))
    category = normalize_whitespace(str(first_nonempty(item.get("category"), "General")))
    if not validate_category(topic, category, contract):
        category = "General"
    impact = normalize_whitespace(str(first_nonempty(item.get("impact"), "Low")))
    if impact not in contract["allowed_values"]["impact"]:
        impact = "Low"
    sentiment = normalize_whitespace(str(first_nonempty(item.get("sentiment"), "Neutral")))
    if sentiment not in contract["allowed_values"]["sentiment"]:
        sentiment = "Neutral"
    return SourceContext(
        name=name,
        feed_url=url,
        topic="Energy" if topic.casefold() == "energy" else topic,
        category=category,
        source_tier=source_tier,
        primary_source=primary_source,
        impact=impact,
        sentiment=sentiment,
        max_age_hours=72,
        editorial_notes=normalize_optional_value(item.get("editorial_notes"), DEFAULT_EDITORIAL_LIMIT),
        data_as_of=first_nonempty(item.get("data_as_of")),
        entities=parse_text_list(item.get("entities"), limit=DEFAULT_ENTITIES_LIMIT, max_item_len=80),
        tickers=[ticker.upper().lstrip("$") for ticker in parse_text_list(item.get("tickers"), limit=DEFAULT_TICKERS_LIMIT, max_item_len=20)],
        citations=parse_url_list(item.get("citations"), limit=DEFAULT_CITATIONS_LIMIT),
        claims=parse_text_list(item.get("claims"), limit=DEFAULT_CLAIMS_LIMIT, max_item_len=500),
        base_url=url,
        format=None,
        from_existing=True,
    )


def normalize_raw_item(
    raw: dict[str, Any],
    context: SourceContext,
    contract: dict[str, Any],
    *,
    base_url: str,
    now: datetime | None = None,
    future_grace_minutes: int | None = None,
    max_age_hours: int | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    now = now or datetime.now(timezone.utc)
    title = normalize_output_value(first_nonempty(raw.get("title"), raw.get("name")), DEFAULT_TITLE_LIMIT)
    if not title:
        return None, "missing title"
    summary = normalize_output_value(first_nonempty(raw.get("summary"), raw.get("description"), raw.get("content"), raw.get("body")), DEFAULT_SUMMARY_LIMIT)
    if not summary:
        return None, "missing summary"

    url = canonicalize_url(first_nonempty(raw.get("url"), raw.get("link"), raw.get("canonical_url"), raw.get("canonicalUrl"), raw.get("id")), base_url=base_url)
    if not url:
        return None, "missing or invalid url"

    topic = normalize_whitespace(str(first_nonempty(raw.get("topic"), context.topic, "Energy")))
    if topic not in contract["allowed_values"]["topic"]:
        return None, f"skipped unknown topic {topic!r}"

    ts = normalize_timestamp(first_nonempty(raw.get("timestamp"), raw.get("published"), raw.get("pubDate"), raw.get("updated"), raw.get("date")))
    if ts is None:
        return None, "missing or invalid timestamp"

    if future_grace_minutes is None:
        future_grace_minutes = int(contract["freshness"]["future_grace_minutes"])
    future_grace = timedelta(minutes=int(future_grace_minutes))
    if ts - now > future_grace:
        return None, "timestamp is too far in the future"

    if max_age_hours is None:
        max_age_hours = context.max_age_hours if context.max_age_hours is not None else int(contract["freshness"]["stale_after_hours"])
    if max_age_hours >= 0 and now - ts > timedelta(hours=max_age_hours):
        return None, "item is older than recency cutoff"

    category_value = first_nonempty(raw.get("category"), raw.get("categories"), context.category, "General")
    if isinstance(category_value, list):
        category_value = category_value[0] if category_value else "General"
    category = normalize_category(category_value, topic, contract) or "General"
    if not validate_category(topic, category, contract):
        category = "General"

    impact = normalize_whitespace(str(first_nonempty(raw.get("impact"), context.impact, "Low")))
    if impact not in contract["allowed_values"]["impact"]:
        impact = context.impact if context.impact in contract["allowed_values"]["impact"] else "Low"

    sentiment = normalize_whitespace(str(first_nonempty(raw.get("sentiment"), context.sentiment, "Neutral")))
    if sentiment not in contract["allowed_values"]["sentiment"]:
        sentiment = context.sentiment if context.sentiment in contract["allowed_values"]["sentiment"] else "Neutral"

    source_name = normalize_output_value(first_nonempty(raw.get("source"), context.name, topic), DEFAULT_SOURCE_LIMIT)
    if not source_name:
        source_name = topic

    source_tier = normalize_source_tier(first_nonempty(raw.get("source_tier"), raw.get("sourceTier"), context.source_tier))
    primary_source_raw = first_nonempty(raw.get("primary_source"), raw.get("primarySource"), raw.get("isPrimarySource"), context.primary_source)
    primary_source = None
    if primary_source_raw is not None:
        try:
            primary_source = coerce_bool(primary_source_raw)
        except ConfigError:
            primary_source = context.primary_source

    entities = parse_text_list(first_nonempty(raw.get("entities"), context.entities), limit=DEFAULT_ENTITIES_LIMIT, max_item_len=80)
    tickers = [ticker.upper().lstrip("$") for ticker in parse_text_list(first_nonempty(raw.get("tickers"), context.tickers), limit=DEFAULT_TICKERS_LIMIT, max_item_len=20)]
    claims = parse_text_list(first_nonempty(raw.get("claims"), context.claims), limit=DEFAULT_CLAIMS_LIMIT, max_item_len=500)
    citations = parse_url_list(first_nonempty(raw.get("citations"), context.citations), limit=DEFAULT_CITATIONS_LIMIT)
    if not citations:
        citations = [url]
    elif url not in citations:
        citations = [url, *[citation for citation in citations if citation != url]][:DEFAULT_CITATIONS_LIMIT]
    editorial_notes = normalize_optional_value(first_nonempty(raw.get("editorial_notes"), raw.get("editorialNotes"), context.editorial_notes), DEFAULT_EDITORIAL_LIMIT)
    data_as_of_raw = first_nonempty(raw.get("data_as_of"), raw.get("dataAsOf"), context.data_as_of, iso_z(ts))
    data_as_of_dt = normalize_timestamp(data_as_of_raw)
    data_as_of = iso_z(data_as_of_dt) if data_as_of_dt else None
    if data_as_of is None:
        data_as_of = iso_z(ts)

    output = {
        "title": title,
        "summary": summary,
        "source": source_name,
        "url": url,
        "timestamp": iso_z(ts),
        "topic": topic,
        "category": category,
        "impact": impact,
        "sentiment": sentiment,
        "citations": citations,
    }
    if source_tier:
        output["source_tier"] = source_tier
    if primary_source is not None:
        output["primary_source"] = primary_source
    if claims:
        output["claims"] = claims
    if entities:
        output["entities"] = entities
    if tickers:
        output["tickers"] = tickers
    if data_as_of:
        output["data_as_of"] = data_as_of
    if editorial_notes:
        output["editorial_notes"] = editorial_notes

    output["id"] = stable_id(source_name, title, url)
    return output, None


def collect_source(source: SourceConfig, contract: dict[str, Any], args: argparse.Namespace) -> tuple[FetchOutcome, list[dict[str, Any]]]:
    context = build_source_context(source, args.max_age_hours)
    outcome = FetchOutcome(source=source, context=context)
    if not source.enabled:
        outcome.error = "disabled"
        return outcome, []
    if source.topic not in contract["allowed_values"]["topic"]:
        outcome.error = f"skipped unknown topic {source.topic!r}"
        return outcome, []

    try:
        body, final_url, content_type = fetch_http(
            source.feed_url,
            timeout=args.timeout_seconds,
            max_bytes=args.max_bytes,
            retries=args.retries,
            backoff_seconds=args.backoff_seconds,
            user_agent=args.user_agent,
            verbose=args.verbose,
        )
        raw_items, feed_title, parser_kind = parse_feed(body, final_url, content_type, source.format)
        outcome.parser_kind = parser_kind
        outcome.raw_count = len(raw_items)
        if feed_title and not source.name:
            context.name = feed_title
        normalized: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                outcome.skipped_count += 1
                continue
            item, reason = normalize_raw_item(
                raw,
                context,
                contract,
                base_url=final_url,
                now=datetime.now(timezone.utc),
                future_grace_minutes=args.future_grace_minutes,
                max_age_hours=None,
            )
            if item is None:
                outcome.skipped_count += 1
                if args.verbose:
                    print(f"Skip item from {source.name}: {reason}", file=sys.stderr)
                continue
            normalized.append(item)
        if source.max_items is not None:
            normalized = normalized[: source.max_items]
        outcome.parsed_count = len(raw_items)
        outcome.kept_count = len(normalized)
        return outcome, normalized
    except Exception as exc:
        outcome.error = str(exc)
        return outcome, []


def normalize_existing_feed(path: Path, contract: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = load_json_file(path)
    except Exception as exc:
        if args.verbose:
            print(f"Existing feed not merged (failed to read {path}): {exc}", file=sys.stderr)
        return []
    if not isinstance(raw, list):
        if args.verbose:
            print(f"Existing feed not merged (expected list): {path}", file=sys.stderr)
        return []

    merged: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw):
        if not isinstance(raw_item, dict):
            continue
        context = build_existing_context(raw_item, contract)
        normalized, reason = normalize_raw_item(
            raw_item,
            context,
            contract,
            base_url=context.base_url or "",
            now=datetime.now(timezone.utc),
            future_grace_minutes=int(contract["freshness"]["future_grace_minutes"]),
            max_age_hours=args.max_age_hours,
        )
        if normalized is None:
            if args.verbose:
                print(f"Skipping existing item #{index}: {reason}", file=sys.stderr)
            continue
        merged.append(normalized)
    return merged


def dedupe_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    url_keys: dict[str, tuple[str, str]] = {}
    title_keys: dict[str, tuple[str, str]] = {}
    dropped = 0

    def score(item: dict[str, Any]) -> tuple[datetime, int, str, str, str]:
        ts = normalize_timestamp(item.get("timestamp")) or datetime.fromtimestamp(0, tz=timezone.utc)
        completeness = sum(1 for key in ("source_tier", "primary_source", "claims", "citations", "tickers", "entities", "data_as_of", "editorial_notes") if item.get(key) not in (None, [], ""))
        return (ts, completeness, lower_key(str(item.get("source", ""))), lower_key(str(item.get("title", ""))), str(item.get("id", "")))

    sorted_items = sorted(items, key=score, reverse=True)
    for item in sorted_items:
        canonical_url = canonicalize_url(item["url"])
        title_key = lower_key(item["title"])
        if canonical_url is None:
            dropped += 1
            continue
        url_key = canonical_url.casefold()
        url_hit = url_keys.get(url_key)
        title_hit = title_keys.get(title_key)
        if url_hit or title_hit:
            dropped += 1
            continue
        key = (url_key, title_key)
        best_by_key[key] = item
        url_keys[url_key] = key
        title_keys[title_key] = key
    result = sorted(
        best_by_key.values(),
        key=lambda item: (
            normalize_timestamp(item["timestamp"]) or datetime.fromtimestamp(0, tz=timezone.utc),
            lower_key(str(item["source"])),
            lower_key(str(item["title"])),
            lower_key(str(item["id"])),
        ),
        reverse=True,
    )
    return result, dropped


def apply_diversity_limits(items: list[dict[str, Any]], per_source_limit: int, per_host_limit: int) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    host_counts: Counter[str] = Counter()
    for item in items:
        source_key = lower_key(str(item.get("source", "")))
        host_key = extract_hostname(item.get("url"))
        if per_source_limit > 0 and source_counts[source_key] >= per_source_limit:
            continue
        if per_host_limit > 0 and host_counts[host_key] >= per_host_limit:
            continue
        kept.append(item)
        source_counts[source_key] += 1
        host_counts[host_key] += 1
    return kept


def write_json_atomic(path: Path, data: Any, *, backup_existing: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if backup_existing and path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = path.with_name(f"{path.stem}.{stamp}.bak{path.suffix}")
        shutil.copy2(path, backup_path)
    temp_handle = None
    temp_path = None
    try:
        temp_handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=str(path.parent),
            prefix=f".{path.stem}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_handle.name)
        with temp_handle:
            json.dump(data, temp_handle, ensure_ascii=False, indent=2)
            temp_handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and normalize public Energy items into nexus/news_data.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python collector.py --dry-run\n"
            "  python collector.py --write --verbose\n"
            "  python collector.py --config nexus\\collector_sources.json --output nexus\\news_data.json --write\n\n"
            "Config shape:\n"
            "  {\"sources\": [{\"name\": \"...\", \"url\": \"https://...\", \"topic\": \"Energy\", \"enabled\": true}]}\n"
            "Non-Energy, Admin, and Personal topics are skipped so they can live in a separate collector."
        ),
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Collector source config JSON (default: nexus\\collector_sources.json).")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output feed JSON (default: nexus\\news_data.json).")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT), help="Quality contract JSON (default: nexus\\news_quality_contract.json).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Write the collected feed atomically.")
    mode.add_argument("--dry-run", action="store_true", help="Collect and validate without writing.")
    parser.add_argument("--merge-existing", action="store_true", default=True, help="Merge valid existing feed records into the output (default: on).")
    parser.add_argument("--no-merge-existing", action="store_false", dest="merge_existing", help="Disable merge of existing feed records.")
    parser.add_argument("--source-limit", type=int, default=0, help="Maximum number of enabled Energy sources to process (0 = no limit).")
    parser.add_argument("--item-limit", type=int, default=0, help="Maximum number of final items to keep (0 = no limit).")
    parser.add_argument("--per-source-limit", type=int, default=3, help="Maximum items to keep per source (default: 3).")
    parser.add_argument("--per-host-limit", type=int, default=3, help="Maximum items to keep per host (default: 3).")
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per source after transient failures.")
    parser.add_argument("--backoff-seconds", type=float, default=1.0, help="Initial retry backoff in seconds.")
    parser.add_argument("--max-bytes", type=int, default=2_000_000, help="Maximum response size in bytes.")
    parser.add_argument("--max-age-hours", type=int, default=72, help="Default recency cutoff for new items.")
    parser.add_argument("--future-grace-minutes", type=int, default=15, help="Allow timestamps up to this many minutes in the future.")
    parser.add_argument("--min-success-sources", type=int, default=1, help="Minimum successful source fetches required before writing.")
    parser.add_argument("--min-items", type=int, default=1, help="Minimum final item count required before writing.")
    parser.add_argument("--user-agent", default="NexusCollector/1.0 (+https://github.com/)", help="Descriptive HTTP User-Agent.")
    parser.add_argument("--backup-existing", action="store_true", help="Create a timestamped backup of the output before writing.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed diagnostics.")
    return parser


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path)


def filter_enabled_sources(sources: list[SourceConfig], limit: int) -> list[SourceConfig]:
    enabled = [source for source in sources if source.enabled]
    if limit and limit > 0:
        return enabled[:limit]
    return enabled


def collect_items(args: argparse.Namespace, contract: dict[str, Any], config_path: Path, output_path: Path) -> tuple[list[dict[str, Any]], CollectionStats, list[FetchOutcome]]:
    sources = parse_config(config_path, contract)
    stats = CollectionStats(total_sources=len(sources))

    enabled = filter_enabled_sources(sources, args.source_limit)
    stats.enabled_sources = len(enabled)
    stats.skipped_sources = stats.total_sources - stats.enabled_sources

    collected: list[dict[str, Any]] = []
    outcomes: list[FetchOutcome] = []
    for source in enabled:
        outcome, items = collect_source(source, contract, args)
        outcomes.append(outcome)
        if outcome.error:
            stats.failed_sources += 1
            print(f"Source failed: {source.name} ({source.feed_url}) -> {outcome.error}", file=sys.stderr)
            continue
        stats.successful_sources += 1
        stats.raw_items += outcome.raw_count
        stats.normalized_items += outcome.kept_count
        collected.extend(items)

    if args.merge_existing:
        existing = normalize_existing_feed(output_path, contract, args)
        stats.merged_existing = len(existing)
        collected.extend(existing)

    deduped, dropped = dedupe_items(collected)
    stats.deduped_items = len(collected) - len(deduped)

    deduped = sorted(
        deduped,
        key=lambda item: (
            normalize_timestamp(item["timestamp"]) or datetime.fromtimestamp(0, tz=timezone.utc),
            lower_key(str(item["source"])),
            lower_key(str(item["title"])),
            lower_key(str(item["id"])),
        ),
        reverse=True,
    )
    deduped = apply_diversity_limits(deduped, args.per_source_limit, args.per_host_limit)
    if args.item_limit and args.item_limit > 0:
        deduped = deduped[: args.item_limit]
    stats.final_items = len(deduped)
    return deduped, stats, outcomes


def run_validation(items: list[dict[str, Any]], contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for index, item in enumerate(items):
        item_issues = validate_output_item(item, contract)
        if item_issues:
            issues.append(f"item[{index}] {item.get('id', '?')}: " + "; ".join(item_issues))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.write and not args.dry_run:
        args.dry_run = True
    if args.write and args.dry_run:
        args.dry_run = False

    try:
        config_path = resolve_path(args.config)
        output_path = resolve_path(args.output)
        contract_path = resolve_path(args.contract)
        contract = load_contract(contract_path)
        args.max_age_hours = max(0, int(args.max_age_hours))
        args.future_grace_minutes = max(0, int(args.future_grace_minutes))
        args.retries = max(0, int(args.retries))
        args.per_source_limit = max(0, int(args.per_source_limit))
        args.per_host_limit = max(0, int(args.per_host_limit))
        args.source_limit = max(0, int(args.source_limit))
        args.item_limit = max(0, int(args.item_limit))
        args.min_success_sources = max(0, int(args.min_success_sources))
        args.min_items = max(0, int(args.min_items))
        items, stats, outcomes = collect_items(args, contract, config_path, output_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except CollectionError as exc:
        print(f"Collection error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    validation_issues = run_validation(items, contract)
    if validation_issues:
        print("Validation errors:", file=sys.stderr)
        for issue in validation_issues:
            print(f"  - {issue}", file=sys.stderr)

    for outcome in outcomes:
        if args.verbose:
            if outcome.error:
                print(f"Source {outcome.source.name} failed: {outcome.error}", file=sys.stderr)
            else:
                print(
                    f"Source {outcome.source.name}: parser={outcome.parser_kind} raw={outcome.raw_count} kept={outcome.kept_count}",
                    file=sys.stderr,
                )

    print(
        f"sources={stats.total_sources} enabled={stats.enabled_sources} success={stats.successful_sources} "
        f"failed={stats.failed_sources} raw_items={stats.raw_items} final_items={stats.final_items}",
        file=sys.stderr,
    )

    if stats.successful_sources < args.min_success_sources:
        print("No write: insufficient successful sources.", file=sys.stderr)
        return 4
    if stats.final_items < args.min_items:
        print("No write: insufficient final items.", file=sys.stderr)
        return 4
    if not items:
        print("No write: collection produced no valid items.", file=sys.stderr)
        return 4
    if validation_issues:
        print("No write: output failed contract validation.", file=sys.stderr)
        return 5

    if args.dry_run:
        print("Dry run: no file written.", file=sys.stderr)
        return 0

    try:
        write_json_atomic(output_path, items, backup_existing=args.backup_existing)
    except Exception as exc:
        print(f"Write failed: {exc}", file=sys.stderr)
        return 6

    print(f"Wrote {len(items)} items to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
