"""Canonical article identity, date, source, medium and genre components."""

from .genre import GENRE_VERSION, resolve_genre
from .medium import MEDIUM_VERSION, MediumResolution, resolve_medium
from .publication_v073 import PUBLICATION_VERSION, PublicationResolution, resolve_publication
from .service_v073 import CANONICAL_SERVICE_VERSION, CanonicalArticleResolver
from .source_resolution_v073 import SOURCE_VERSION, SourceResolution, resolve_source

__all__ = [
    "CANONICAL_SERVICE_VERSION",
    "CanonicalArticleResolver",
    "GENRE_VERSION",
    "MEDIUM_VERSION",
    "MediumResolution",
    "PUBLICATION_VERSION",
    "PublicationResolution",
    "SOURCE_VERSION",
    "SourceResolution",
    "resolve_genre",
    "resolve_medium",
    "resolve_publication",
    "resolve_source",
]
