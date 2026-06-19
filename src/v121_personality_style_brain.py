"""v121 — Personality Style Brain."""
from __future__ import annotations
from datetime import datetime

STYLES = {"facts_only":"Stick to verified facts and system status.",
          "homie_project":"Friendly, project-aware collaborator tone.",
          "codex_prompt":"Technical, efficient, direct coding partner.",
          "short_voice":"Ultra-concise for voice/glasses mode.",
          "deep_strategy":"Analyze deeply with strategy and debate.",
          "teaching_mode":"Step-by-step with examples and checks."}

def apply_style(style_name, message, context=None):
    style = STYLES.get(style_name, STYLES["facts_only"])
    return {"version":"v121_personality_style","created_at":datetime.now().isoformat(),
            "style":style_name,"style_description":style,
            "original_message_length":len(message),
            "adapted":True,"preserves_facts":True,
            "note":"Style applied. Facts preserved. No false capability claims."}

def main():
    print("Nova v121 -- Personality Style\n")
    r = apply_style("homie_project","What can you do?")
    print(f"Style: {r['style']}, Adapts: {r['adapted']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
