"""Compatibility entrypoint forwarding production runs to v0.5.6 PR-A shadow."""

from .pipeline_v056a import NativeCollectorPipeline

__all__ = ["NativeCollectorPipeline"]
