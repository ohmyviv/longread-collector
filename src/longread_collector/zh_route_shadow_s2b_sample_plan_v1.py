"""Deterministic sample planning for the bounded Chinese Route S2-B body audit.

DESIGN / OFFLINE only. This module does not perform network requests, body
acquisition, Sheet writes, Editor wiring, or production mutation. It freezes
which S2-A metadata strata are eligible for later body validation and selects a
reproducible bounded sample before any body request is authorized.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

S2B_SAMPLE_PLAN_VERSION = "zh-route-shadow-s2b-sample-plan-v1"
S2B_SAMPLE_SEED = "zh-route-shadow-s2b-20260829-v1"
S2B_BODY_ATTEMPT_CAP = 40
S2B_PRIMARY_PLAUSIBLE_N = 30
S2B_UNCERTAINTY_EXPLORE_N = 10
S2B_REPLACEMENT_ALLOWED = False

PLAUSIBLE = "plausible_standard_longread"
INSUFFICIENT = "insufficient_evidence"

# Quotas are source-specific because S2-B estimates source-level body survival,
# not a pooled portfolio average. `first_surface` is the frozen attribution key
# from the S2-A canonical cohort.
S2B_STRATUM_QUOTAS: dict[tuple[str, str, str], int] = {
    # Jiemian: 15 plausible + 4 insufficient = 19
    ("jiemian-depth", PLAUSIBLE, "jiemian_medicine"): 8,
    ("jiemian-depth", PLAUSIBLE, "jiemian_consumer"): 6,
    ("jiemian-depth", PLAUSIBLE, "jiemian_health_face"): 1,
    ("jiemian-depth", INSUFFICIENT, "jiemian_medicine"): 1,
    ("jiemian-depth", INSUFFICIENT, "jiemian_consumer"): 3,
    # Yicai: 15 plausible + 6 insufficient = 21
    ("yicai", PLAUSIBLE, "yicai_kechuang"): 7,
    ("yicai", PLAUSIBLE, "yicai_finance"): 5,
    ("yicai", PLAUSIBLE, "yicai_news_breadth"): 2,
    ("yicai", PLAUSIBLE, "yicai_auto"): 1,
    ("yicai", INSUFFICIENT, "yicai_finance"): 3,
    ("yicai", INSUFFICIENT, "yicai_kechuang"): 1,
    ("yicai", INSUFFICIENT, "yicai_news_breadth"): 1,
    ("yicai", INSUFFICIENT, "yicai_auto"): 1,
}


@dataclass(slots=True, frozen=True)
class S2BSampleItem:
    url_canonical: str
    source_id: str
    first_surface: str
    metadata_class: str
    sampling_role: str
    deterministic_rank: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rank(url: str, *, source_id: str, metadata_class: str, first_surface: str) -> str:
    payload = "|".join(
        (S2B_SAMPLE_SEED, source_id, metadata_class, first_surface, url)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_s2b_sample(rows: Iterable[dict[str, Any]]) -> tuple[S2BSampleItem, ...]:
    """Select the frozen 40-item S2-B sample from the reviewed S2-A cohort.

    Fail-closed properties:
    - only the exact source/class/surface strata with frozen quotas are admitted;
    - canonical URLs must be unique in the supplied S2-A cohort;
    - every quota must be satisfiable; there is no cross-stratum substitution;
    - selection is order-independent and deterministic under the fixed seed;
    - no replacement policy is encoded by the contract constant, not by peeking
      at later acquisition outcomes.
    """

    grouped: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
    seen_urls: set[str] = set()

    for row in rows:
        url = _text(row.get("url_canonical"))
        source_id = _text(row.get("source_id"))
        metadata_class = _text(row.get("metadata_class"))
        first_surface = _text(row.get("first_surface"))

        if not url:
            continue
        if url in seen_urls:
            raise ValueError(f"duplicate canonical URL in S2-A cohort: {url}")
        seen_urls.add(url)

        key = (source_id, metadata_class, first_surface)
        if key not in S2B_STRATUM_QUOTAS:
            # S2-A obvious-out-of-scope rows and any future non-authorized strata
            # do not silently become body targets.
            continue
        grouped[key].append((url, _rank(
            url,
            source_id=source_id,
            metadata_class=metadata_class,
            first_surface=first_surface,
        )))

    selected: list[S2BSampleItem] = []
    for key, quota in sorted(S2B_STRATUM_QUOTAS.items()):
        source_id, metadata_class, first_surface = key
        available = sorted(grouped.get(key, []), key=lambda value: (value[1], value[0]))
        if len(available) < quota:
            raise ValueError(
                "S2-B stratum under quota: "
                f"{source_id}/{metadata_class}/{first_surface} "
                f"needs {quota}, found {len(available)}"
            )
        role = "primary_plausible" if metadata_class == PLAUSIBLE else "uncertainty_explore"
        for url, rank in available[:quota]:
            selected.append(
                S2BSampleItem(
                    url_canonical=url,
                    source_id=source_id,
                    first_surface=first_surface,
                    metadata_class=metadata_class,
                    sampling_role=role,
                    deterministic_rank=rank,
                )
            )

    if len(selected) != S2B_BODY_ATTEMPT_CAP:
        raise AssertionError(
            f"frozen S2-B sample must contain {S2B_BODY_ATTEMPT_CAP} items; "
            f"selected {len(selected)}"
        )

    primary = sum(item.sampling_role == "primary_plausible" for item in selected)
    explore = sum(item.sampling_role == "uncertainty_explore" for item in selected)
    if primary != S2B_PRIMARY_PLAUSIBLE_N or explore != S2B_UNCERTAINTY_EXPLORE_N:
        raise AssertionError(
            "S2-B role totals drifted: "
            f"primary={primary}, explore={explore}"
        )

    return tuple(
        sorted(
            selected,
            key=lambda item: (
                item.source_id,
                item.sampling_role,
                item.first_surface,
                item.deterministic_rank,
                item.url_canonical,
            ),
        )
    )


def sample_summary(sample: Iterable[S2BSampleItem]) -> dict[str, Any]:
    items = tuple(sample)
    by_stratum: dict[str, int] = defaultdict(int)
    by_source_role: dict[str, int] = defaultdict(int)
    for item in items:
        by_stratum[
            f"{item.source_id}|{item.metadata_class}|{item.first_surface}"
        ] += 1
        by_source_role[f"{item.source_id}|{item.sampling_role}"] += 1
    return {
        "version": S2B_SAMPLE_PLAN_VERSION,
        "seed": S2B_SAMPLE_SEED,
        "body_attempt_cap": S2B_BODY_ATTEMPT_CAP,
        "replacement_allowed": S2B_REPLACEMENT_ALLOWED,
        "selected_total": len(items),
        "by_source_role": dict(sorted(by_source_role.items())),
        "by_stratum": dict(sorted(by_stratum.items())),
    }


__all__ = [
    "INSUFFICIENT",
    "PLAUSIBLE",
    "S2B_BODY_ATTEMPT_CAP",
    "S2B_PRIMARY_PLAUSIBLE_N",
    "S2B_REPLACEMENT_ALLOWED",
    "S2B_SAMPLE_PLAN_VERSION",
    "S2B_SAMPLE_SEED",
    "S2B_STRATUM_QUOTAS",
    "S2B_UNCERTAINTY_EXPLORE_N",
    "S2BSampleItem",
    "sample_summary",
    "select_s2b_sample",
]
