"""Compatibility entrypoint forwarding shadow runs to v0.5.6 PR-B."""

from .pipeline_v056b import NativeCollectorPipeline

__all__ = ["NativeCollectorPipeline"]
