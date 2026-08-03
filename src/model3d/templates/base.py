"""PackageTemplate ABC: family-specific parametric body generators.

A template turns a Body3DSpec into a cadquery Assembly whose named nodes are
"Body" plus one "Lead_<pin>" per lead. Geometry follows the shared coordinate
contract: millimetres, +Z up, seating plane at Z=0, origin at component centre.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import cadquery as cq

from ..spec import Body3DSpec


class PackageTemplate(ABC):
    """Base class for parametric package-body generators."""

    #: lead style this template handles (matches Body3DSpec.lead_style)
    lead_style: str = ""

    @abstractmethod
    def build(self, spec: Body3DSpec) -> cq.Assembly:
        """Return a cadquery Assembly for the package body described by spec."""
        raise NotImplementedError
