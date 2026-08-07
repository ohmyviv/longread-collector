"""Internal extractor contracts for v0.6 PR-5 Acquisition Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from ..contracts import DiscoveryRecord


ACQUISITION_EXTRACTOR_CONTRACT_VERSION = "acquisition-extractor-v0.6-pr5"


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class ExtractorPayload:
    """Normalized extractor output before sufficiency evaluation.

    Extractors report observable payload facts only.  They do not decide whether
    the item is a candidate, whether Firecrawl should be called next, or whether
    the article should be selected.
    """

    extractor: str
    markdown: str = ""
    text: str = ""
    title: str = ""
    author: str = ""
    published_at: str = ""
    canonical_links: tuple[str, ...] = ()
    outbound_links: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    credits_used: float = 0.0
    http_status: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def body(self) -> str:
        return self.markdown or self.text


class AcquisitionExtractor(Protocol):
    """Explicit extractor port used by AcquisitionService."""

    name: str
    paid: bool

    async def extract(self, record: DiscoveryRecord) -> ExtractorPayload: ...


__all__ = [
    "ACQUISITION_EXTRACTOR_CONTRACT_VERSION",
    "AcquisitionExtractor",
    "ExtractorPayload",
]
