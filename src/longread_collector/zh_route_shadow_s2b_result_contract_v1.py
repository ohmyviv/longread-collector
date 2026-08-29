"""Fail-closed result-ledger contract for Chinese Route S2-B.

OFFLINE validation only. No body acquisition, network request, Sheet write,
Editor wiring, or production mutation is performed here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from .zh_route_shadow_s2b_sample_plan_v1 import S2BSampleItem

S2B_RESULT_CONTRACT_VERSION = "zh-route-shadow-s2b-result-contract-v1"
MIN_STANDARD_LONGREAD_CONTENT_CHARS = 2500

ACQUISITION_STATUSES = frozenset(
    {
        "usable_body",
        "acquisition_failed",
        "wrong_or_shell_body",
        "duplicate_or_noncanonical_body",
    }
)
BODY_PRODUCT_CLASSES = frozenset(
    {
        "body_confirmed_standard_longread",
        "body_confirmed_non_target",
        "body_borderline_insufficient",
        "not_evaluable",
    }
)
DEPTH_SIGNALS = frozenset(
    {
        "multi_source_or_substantive_interview",
        "interpreted_quantitative_or_documentary_evidence",
        "causal_explanatory_strategic_or_mechanism_analysis",
        "historical_competitive_regulatory_or_policy_context",
        "original_field_investigative_or_primary_source_reporting",
    }
)
NON_TARGET_REASONS = frozenset(
    {
        "too_short_under_2500_chars",
        "press_release_or_corporate_promotion",
        "event_recap",
        "digest_roundup_or_quick_update",
        "brief_or_shallow_news",
        "listing_or_non_article",
        "academic_or_primary_document",
        "other_frozen_non_target",
    }
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _signals(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(_text(item) for item in value if _text(item))


def validate_s2b_results(
    sample: Iterable[S2BSampleItem],
    result_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Validate one completed S2-B ledger against the frozen sample manifest."""

    sample_items = tuple(sample)
    sample_by_url = {item.url_canonical: item for item in sample_items}
    if len(sample_by_url) != len(sample_items):
        raise ValueError("duplicate canonical URL in S2-B sample manifest")

    rows = list(result_rows)
    urls = [_text(row.get("url_canonical")) for row in rows]
    row_urls = set(urls)
    duplicate_urls = sorted(url for url, count in Counter(urls).items() if url and count > 1)
    missing_urls = sorted(set(sample_by_url) - row_urls)
    unexpected_urls = sorted(row_urls - set(sample_by_url))
    errors: list[dict[str, str]] = []

    if duplicate_urls:
        errors.extend({"url_canonical": url, "error": "duplicate_result_row"} for url in duplicate_urls)
    if "" in row_urls:
        errors.append({"url_canonical": "", "error": "missing_result_url"})

    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    by_source_role: dict[str, Counter[str]] = defaultdict(Counter)
    network_requests_total = 0
    firecrawl_calls_total = 0

    for row in rows:
        url = _text(row.get("url_canonical"))
        item = sample_by_url.get(url)
        if item is None:
            continue

        # Manifest identity cannot be rewritten by the result ledger.
        for field, expected in (
            ("source_id", item.source_id),
            ("first_surface", item.first_surface),
            ("metadata_class", item.metadata_class),
            ("sampling_role", item.sampling_role),
        ):
            if _text(row.get(field)) != expected:
                errors.append({"url_canonical": url, "error": f"manifest_mismatch:{field}"})

        acquisition_status = _text(row.get("acquisition_status"))
        body_class = _text(row.get("body_product_class"))
        if acquisition_status not in ACQUISITION_STATUSES:
            errors.append({"url_canonical": url, "error": "invalid_acquisition_status"})
            continue
        if body_class not in BODY_PRODUCT_CLASSES:
            errors.append({"url_canonical": url, "error": "invalid_body_product_class"})
            continue

        try:
            content_chars = _int(row.get("content_chars"))
            network_request_count = _int(row.get("network_request_count"))
            firecrawl_calls = _int(row.get("firecrawl_calls"))
        except (TypeError, ValueError):
            errors.append({"url_canonical": url, "error": "invalid_numeric_telemetry"})
            continue
        if content_chars < 0 or network_request_count < 0 or firecrawl_calls < 0:
            errors.append({"url_canonical": url, "error": "negative_numeric_telemetry"})
            continue
        network_requests_total += network_request_count
        firecrawl_calls_total += firecrawl_calls

        signals = _signals(row.get("depth_signals"))
        invalid_signals = sorted(set(signals) - DEPTH_SIGNALS)
        if invalid_signals:
            errors.append({"url_canonical": url, "error": "invalid_depth_signal"})

        non_target_reason = _text(row.get("non_target_reason"))
        if acquisition_status != "usable_body":
            if body_class != "not_evaluable":
                errors.append({"url_canonical": url, "error": "nonusable_body_must_be_not_evaluable"})
        else:
            if not _text(row.get("body_fingerprint")):
                errors.append({"url_canonical": url, "error": "usable_body_missing_fingerprint"})
            if not _text(row.get("extraction_path")):
                errors.append({"url_canonical": url, "error": "usable_body_missing_extraction_path"})
            if body_class == "not_evaluable":
                errors.append({"url_canonical": url, "error": "usable_body_cannot_be_not_evaluable"})
            elif body_class == "body_confirmed_standard_longread":
                if content_chars < MIN_STANDARD_LONGREAD_CONTENT_CHARS:
                    errors.append({"url_canonical": url, "error": "confirmed_longread_too_short"})
                if len(set(signals)) < 2:
                    errors.append({"url_canonical": url, "error": "confirmed_longread_needs_two_depth_signals"})
                if non_target_reason:
                    errors.append({"url_canonical": url, "error": "confirmed_longread_has_non_target_reason"})
            elif body_class == "body_confirmed_non_target":
                if non_target_reason not in NON_TARGET_REASONS:
                    errors.append({"url_canonical": url, "error": "non_target_missing_or_invalid_reason"})

        by_source[item.source_id][f"acquisition:{acquisition_status}"] += 1
        by_source[item.source_id][f"body:{body_class}"] += 1
        by_source_role[f"{item.source_id}|{item.sampling_role}"][f"body:{body_class}"] += 1

    return {
        "version": S2B_RESULT_CONTRACT_VERSION,
        "valid": not errors and not missing_urls and not unexpected_urls and len(rows) == len(sample_items),
        "sample_total": len(sample_items),
        "result_rows": len(rows),
        "missing_urls": missing_urls,
        "unexpected_urls": unexpected_urls,
        "errors": errors,
        "network_requests_total": network_requests_total,
        "firecrawl_calls_total": firecrawl_calls_total,
        "by_source": {key: dict(sorted(value.items())) for key, value in sorted(by_source.items())},
        "by_source_role": {
            key: dict(sorted(value.items())) for key, value in sorted(by_source_role.items())
        },
    }


__all__ = [
    "ACQUISITION_STATUSES",
    "BODY_PRODUCT_CLASSES",
    "DEPTH_SIGNALS",
    "MIN_STANDARD_LONGREAD_CONTENT_CHARS",
    "NON_TARGET_REASONS",
    "S2B_RESULT_CONTRACT_VERSION",
    "validate_s2b_results",
]
