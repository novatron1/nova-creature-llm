"""v157 — Mistake Replay Trainer."""
from __future__ import annotations
from datetime import datetime


MISTAKES = [
    {"original":"Nova can drive itself.","corrected":"Nova simulates movement only. Real movement blocked.","role":"speech_output_transformer"},
    {"original":"Maybe v032 is the best.","corrected":"v055 is live. v032 is base fallback preserved.","role":"memory_transformer"},
    {"original":"Train everything.","corrected":"Train only approved memory. Rejected/pending never trains.","role":"critic_conscience_transformer"},
]

def get_mistake_replays():
    replays = [{"original":m["original"],"corrected":m["corrected"],"why":"contradicted system status",
                "avoid":"check self-map before claiming","role":m["role"],"trainable_after_approval":True} for m in MISTAKES]
    return {"version":"v157_mistake_replay","created_at":datetime.now().isoformat(),
            "replays":replays,"count":len(replays),"uses_v074_mistake_memory":True}


def main():
    print(f"Nova v157_mistake_replay_trainer\n")
    r = get_mistake_replays()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
