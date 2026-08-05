"""Compatibility entrypoint forwarding shadow runs to v0.5.6 PR-E."""

from .pipeline_v056e import NativeCollectorPipeline

__all__ = ["NativeCollectorPipeline"]
