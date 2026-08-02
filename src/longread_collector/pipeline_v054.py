"""Compatibility entrypoint forwarding shadow runs to v0.5.6 PR-D."""

from .pipeline_v056d import NativeCollectorPipeline

__all__ = ["NativeCollectorPipeline"]
