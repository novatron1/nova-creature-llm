"""Base class for specialist cortex modules."""
from abc import ABC, abstractmethod
from nova.schema import MeaningPacket, SpecialistResult


class SpecialistCortex(ABC):
    """A specialist reasoning module."""

    name: str = "base"

    @abstractmethod
    def analyze(self, packet: MeaningPacket) -> SpecialistResult:
        pass

    def __repr__(self) -> str:
        return "<%s>" % self.name
