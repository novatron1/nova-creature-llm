"""v792_knowledge_graph_builder — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def knowledge_graph_builder(lessons=None):
    """Build a simple knowledge graph from lessons."""
    if not lessons:
        return {"version": "v792_knowledge_graph_builder", "nodes": [], "edges": [], "status": "ok"}
    nodes = []
    edges = []
    seen_topics = set()
    for l in lessons:
        topic = l.get("topic", "general")
        if topic not in seen_topics:
            nodes.append({"id": topic, "label": topic, "lessons": 1})
            seen_topics.add(topic)
        else:
            for n in nodes:
                if n["id"] == topic:
                    n["lessons"] += 1
    topics = list(seen_topics)
    for i in range(len(topics)):
        for j in range(i+1, len(topics)):
            edges.append({"source": topics[i], "target": topics[j], "relation": "related"})
    return {"version": "v792_knowledge_graph_builder", "nodes": nodes, "edges": edges, "status": "ok"}


def main():
    print(f"Nova v792_knowledge_graph_builder")
    r = knowledge_graph_builder()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
