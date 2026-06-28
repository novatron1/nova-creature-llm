"""Base class for all tiny control modules."""
from abc import ABC, abstractmethod
from nova.schema import MeaningPacket


class TinyModule(ABC):
    """A tiny, focused module that operates on a MeaningPacket."""

    name: str = "base"

    @abstractmethod
    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Process the packet and return an enriched/modified version."""
        pass

    def __repr__(self) -> str:
        return "<%s>" % self.name
