"""Compatibility entrypoint forwarding shadow runs to v0.5.6 PR-C."""

from .pipeline_v056c import NativeCollectorPipeline

__all__ = ["NativeCollectorPipeline"]
