"""Compatibility entrypoint forwarding production runs to collector v0.5.5."""

from .pipeline_v055 import NativeCollectorPipeline

__all__ = ["NativeCollectorPipeline"]
