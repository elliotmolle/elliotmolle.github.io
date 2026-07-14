from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_CONTRACT = {
    "schema_version": "1.0.0",
    "required_fields": ["id", "title", "summary", "source", "url", "timestamp", "topic", "category", "impact", "sentiment"],
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
    "freshness": {
        "stale_after_hours": 72,
        "future_grace_minutes": 15,
    },
    "summary_rules": {
        "placeholder_phrases": [
            "this is a detailed summary regarding the latest updates from",
            "the impact on",
            "is currently being analyzed by experts",
        ],
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


class HtmlStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.tags_seen = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags_seen += 1

    def handle_endtag(self, tag: str) -> None:
        self.tags_seen += 1

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", html_lib.unescape("".join(self.parts))).strip()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract(path: Path) -> dict[str, Any]:
    if path.exists():
        contract = load_json(path)
        merged = DEFAULT_CONTRACT.copy()
        merged.update(contract)
        if "allowed_values" in contract:
            merged["allowed_values"] = {**DEFAULT_CONTRACT["allowed_values"], **contract["allowed_values"]}
        return merged
    return DEFAULT_CONTRACT


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonical_key(value: str) -> str:
    return normalize_whitespace(html_lib.unescape(value)).casefold()


def canonical_url(value: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip()
    path = parsed.path.rstrip("/")
    if not path:
        path = "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, parsed.fragment))


def parse_timestamp(value: Any, assume_tz: timezone) -> tuple[datetime | None, list[str], str | None]:
    issues: list[str] = []
    if not isinstance(value, str):
        return None, ["timestamp_not_string"], None

    parsed: datetime | None = None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except Exception:
            parsed = None

    if parsed is None:
        return None, ["timestamp_unparseable"], None

    if parsed.tzinfo is None:
        issues.append("timestamp_timezone_inferred")
        parsed = parsed.replace(tzinfo=assume_tz)

    normalized = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return parsed, issues, normalized


def strip_html_summary(value: Any) -> tuple[str, bool, int]:
    if not isinstance(value, str):
        return "", False, 0
    parser = HtmlStripper()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return normalize_whitespace(html_lib.unescape(value)), False, 0
    return parser.text(), parser.tags_seen > 0, parser.tags_seen


def placeholder_summary(text: str, phrases: list[str]) -> bool:
    lower = text.casefold()
    return any(phrase in lower for phrase in phrases)


def sensational_flags(text: str) -> list[str]:
    lower = text.casefold()
    flags: list[str] = []
    if re.search(r"\b(explosive|shocking|bizarre|outrageous|scandal|graphic|brutal|horrifying|sensational)\b", lower):
        flags.append("sensational_language")
    if re.search(r"\b(diarrhea|feces|vomit|vomiting|gore)\b", lower):
        flags.append("graphic_or_crude_language")
    if re.search(r"\breportedly tied to\b", lower) and ("sensational_language" in flags or "graphic_or_crude_language" in flags):
        flags.append("sensational_attribution")
    return flags


def terra_ambiguity(text: str, disambiguation: dict[str, list[str]]) -> list[str]:
    lower = text.casefold()
    specific = [term.casefold() for term in disambiguation.get("specific_entities", [])]
    generic_terms = [term.casefold() for term in disambiguation.get("ambiguous_terms", [])]
    if re.search(r"\bterrapower\b", lower) and re.search(r"\bterrestrial energy\b", lower):
        return ["terra_entity_collision"]
    if re.search(r"\bterra energy\b", lower):
        return ["terra_generic_ambiguity"]
    if re.search(r"\bterra\b", lower) and not any(term in lower for term in specific):
        return ["terra_generic_ambiguity"]
    if any(term in lower for term in generic_terms):
        return ["terra_generic_ambiguity"]
    return []


def validate_allowed(value: Any, allowed: list[str]) -> bool:
    return isinstance(value, str) and value in allowed


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and normalize Nexus news feed quality.")
    parser.add_argument(
        "--feed",
        default=str(repo_root() / "nexus" / "news_data.json"),
        help="Path to the JSON feed file.",
    )
    parser.add_argument(
        "--contract",
        default=str(repo_root() / "nexus" / "news_quality_contract.json"),
        help="Path to the quality contract / source registry JSON file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output instead of a human-readable report.",
    )
    args = parser.parse_args()

    feed_path = Path(args.feed)
    contract_path = Path(args.contract)

    if not feed_path.exists():
        print(f"Feed not found: {feed_path}", file=sys.stderr)
        return 2

    try:
        contract = load_contract(contract_path)
    except Exception as exc:
        print(f"Failed to load contract {contract_path}: {exc}", file=sys.stderr)
        return 2

    try:
        feed = load_json(feed_path)
    except Exception as exc:
        print(f"Failed to load feed {feed_path}: {exc}", file=sys.stderr)
        return 2

    if not isinstance(feed, list):
        print("Feed JSON must be an array of news items.", file=sys.stderr)
        return 2

    required_fields = contract["required_fields"]
    allowed = contract["allowed_values"]
    stale_after = timedelta(hours=int(contract["freshness"]["stale_after_hours"]))
    future_grace = timedelta(minutes=int(contract["freshness"]["future_grace_minutes"]))
    assume_tz = datetime.now().astimezone().tzinfo or timezone.utc
    now = datetime.now().astimezone()

    all_categories = set(allowed["category_global"])
    topic_categories = allowed["categories_by_topic"]

    issues_by_item: list[dict[str, Any]] = []
    error_count = 0
    warning_count = 0
    normalized_urls: list[str] = []
    canonical_titles: list[str] = []
    canonical_ids: list[str] = []

    for index, item in enumerate(feed):
        item_issues: list[dict[str, str]] = []
        if not isinstance(item, dict):
            error_count += 1
            issues_by_item.append({"index": index, "issues": [{"severity": "error", "code": "item_not_object"}]})
            continue

        item_id = str(item.get("id", ""))
        title = item.get("title", "")
        summary = item.get("summary", "")
        source = item.get("source", "")
        url = item.get("url", "")
        topic = item.get("topic")
        category = item.get("category")
        impact = item.get("impact")
        sentiment = item.get("sentiment")

        missing = [field for field in required_fields if field not in item or item.get(field) in (None, "")]
        if missing:
            error_count += len(missing)
            item_issues.append({"severity": "error", "code": "missing_required_fields", "detail": ",".join(missing)})

        if impact not in (None, "") and not validate_allowed(impact, allowed["impact"]):
            error_count += 1
            item_issues.append({"severity": "error", "code": "invalid_impact", "detail": str(impact)})

        if sentiment not in (None, "") and not validate_allowed(sentiment, allowed["sentiment"]):
            error_count += 1
            item_issues.append({"severity": "error", "code": "invalid_sentiment", "detail": str(sentiment)})

        if topic not in (None, "") and not validate_allowed(topic, allowed["topic"]):
            error_count += 1
            item_issues.append({"severity": "error", "code": "invalid_topic", "detail": str(topic)})

        if category not in (None, "") and isinstance(category, str):
            if category not in all_categories:
                error_count += 1
                item_issues.append({"severity": "error", "code": "invalid_category", "detail": category})
            elif isinstance(topic, str) and topic in topic_categories and category not in topic_categories[topic]:
                warning_count += 1
                item_issues.append({"severity": "warning", "code": "topic_category_mismatch", "detail": f"{topic} → {category}"})
        elif category not in (None, ""):
            error_count += 1
            item_issues.append({"severity": "error", "code": "invalid_category", "detail": str(category)})

        normalized_url = ""
        if isinstance(url, str):
            normalized_url = canonical_url(url)
            if url.strip() == "#":
                error_count += 1
                item_issues.append({"severity": "error", "code": "placeholder_url", "detail": "#"})
            else:
                from urllib.parse import urlsplit

                parsed_url = urlsplit(url.strip())
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    error_count += 1
                    item_issues.append({"severity": "error", "code": "invalid_url", "detail": url})
        else:
            error_count += 1
            item_issues.append({"severity": "error", "code": "invalid_url", "detail": str(url)})

        parsed_ts, ts_issues, normalized_ts = parse_timestamp(item.get("timestamp"), assume_tz)
        for code in ts_issues:
            if code == "timestamp_unparseable":
                error_count += 1
                item_issues.append({"severity": "error", "code": code})
            else:
                warning_count += 1
                item_issues.append({"severity": "warning", "code": code})

        if parsed_ts is not None:
            if parsed_ts - now > future_grace:
                warning_count += 1
                item_issues.append({"severity": "warning", "code": "future_dated_item", "detail": normalized_ts or ""})
            if now - parsed_ts > stale_after:
                warning_count += 1
                item_issues.append({"severity": "warning", "code": "stale_item", "detail": normalized_ts or ""})

        stripped_summary, html_detected, tag_count = strip_html_summary(summary)
        if html_detected:
            warning_count += 1
            item_issues.append({"severity": "warning", "code": "html_summary_stripped", "detail": f"{tag_count} tags"})

        if placeholder_summary(stripped_summary, contract["summary_rules"]["placeholder_phrases"]):
            error_count += 1
            item_issues.append({"severity": "error", "code": "placeholder_summary"})

        for code in sensational_flags(f"{title} {stripped_summary}"):
            warning_count += 1
            item_issues.append({"severity": "warning", "code": code})

        for code in terra_ambiguity(f"{title} {stripped_summary} {source}", contract["entity_disambiguation"]):
            warning_count += 1
            item_issues.append({"severity": "warning", "code": code})

        if not isinstance(item.get("source_tier"), (str, type(None))):
            warning_count += 1
            item_issues.append({"severity": "warning", "code": "invalid_source_tier"})
        if not isinstance(item.get("primary_source"), (bool, type(None))):
            warning_count += 1
            item_issues.append({"severity": "warning", "code": "invalid_primary_source"})

        canonical_ids.append(canonical_key(item_id))
        if normalized_url:
            normalized_urls.append(normalized_url.casefold())
        if isinstance(title, str):
            canonical_titles.append(canonical_key(title))

        issues_by_item.append(
            {
                "id": item_id,
                "title": title,
                "source": source,
                "issues": item_issues,
                "normalized_timestamp": normalized_ts,
                "normalized_url": normalized_url,
            }
        )

    duplicate_ids = Counter(value for value in canonical_ids if value)
    duplicate_urls = Counter(value for value in normalized_urls if value)
    duplicate_titles = Counter(value for value in canonical_titles if value)

    for item in issues_by_item:
        if duplicate_ids[canonical_key(str(item.get("id", "")))] > 1:
            item["issues"].append({"severity": "error", "code": "duplicate_id"})
            error_count += 1
        if isinstance(item.get("title"), str) and duplicate_titles[canonical_key(item["title"])] > 1:
            item["issues"].append({"severity": "error", "code": "duplicate_title"})
            error_count += 1
        normalized_url = item.get("normalized_url", "")
        if isinstance(normalized_url, str) and normalized_url and duplicate_urls[normalized_url.casefold()] > 1:
            item["issues"].append({"severity": "error", "code": "duplicate_url"})
            error_count += 1

    report = {
        "feed_path": str(feed_path),
        "contract_path": str(contract_path),
        "item_count": len(feed),
        "error_count": error_count,
        "warning_count": warning_count,
        "duplicates": {
            "ids": sum(1 for c in duplicate_ids.values() if c > 1),
            "urls": sum(1 for c in duplicate_urls.values() if c > 1),
            "titles": sum(1 for c in duplicate_titles.values() if c > 1),
        },
        "items": issues_by_item,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Feed: {feed_path}")
        print(f"Items: {len(feed)}")
        print(f"Errors: {error_count}  Warnings: {warning_count}")
        print(
            "Duplicates: "
            f"ids={report['duplicates']['ids']} urls={report['duplicates']['urls']} titles={report['duplicates']['titles']}"
        )
        print()
        for item in issues_by_item:
            if not item["issues"]:
                continue
            issue_codes = ", ".join(f"{issue['severity']}:{issue['code']}" for issue in item["issues"])
            print(f"- {item.get('id', '?')} | {item.get('source', '')} | {issue_codes}")
            if item.get("title"):
                print(f"  title: {item['title']}")

    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
