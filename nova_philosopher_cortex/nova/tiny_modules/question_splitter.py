"""Question Splitter - splits multi-part questions."""
import re
from nova.tiny_modules.base import TinyModule
from nova.schema import MeaningPacket


class QuestionSplitter(TinyModule):
    name = "question_splitter"

    def process(self, packet: MeaningPacket) -> MeaningPacket:
        """Split complex questions into constituent parts."""
        text = packet.cleaned_text
        # Split on numbered lists, bullet points, or multiple questions
        parts = re.split(r'\n|[;]|(?<=\?)\s+', text)
        sub_questions = [p.strip() for p in parts if p.strip().endswith("?")]
        if sub_questions:
            packet.questions = sub_questions
        packet.module_chain.append(self.name)
        return packet
