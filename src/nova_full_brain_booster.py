from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from nova_large_sft_dataset import BANNED_RESPONSE_MARKERS, SYSTEM_MESSAGE


DEFAULT_SEED = 20260711
DEFAULT_TARGET_COUNT = 1800
OUTPUT_DIR = Path("artifacts") / "nova_full_brain_booster"
SOURCE_NAME = "nova_full_brain_booster_v1"


@dataclass(frozen=True)
class BoosterExample:
    category: str
    prompt: str
    response: str
    quality_tags: tuple[str, ...] = ()
    context: tuple[tuple[str, str], ...] = ()


def build_booster_dataset(
    project_root: Path,
    target_count: int = DEFAULT_TARGET_COUNT,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    project_root = Path(project_root)
    output_dir = project_root / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    examples = _expanded_examples(target_count=target_count, rng=rng)
    records = _dedupe_and_validate(examples, target_count=target_count)
    splits = _split_records(records, seed=seed)

    for split, rows in splits.items():
        _write_jsonl(output_dir / f"{split}.jsonl", rows)

    manifest = {
        "version": SOURCE_NAME,
        "seed": seed,
        "target_count": target_count,
        "record_count": len(records),
        "split_counts": {split: len(rows) for split, rows in splits.items()},
        "category_counts": _category_counts(records),
        "content_fingerprint": _fingerprint(records),
        "outputs": {
            "train": _posix(OUTPUT_DIR / "train.jsonl"),
            "validation": _posix(OUTPUT_DIR / "validation.jsonl"),
            "holdout": _posix(OUTPUT_DIR / "holdout.jsonl"),
            "manifest": _posix(OUTPUT_DIR / "manifest.json"),
        },
        "notes": [
            "Focused booster set for full-brain LoRA weaknesses found by isolated tests.",
            "Use with tools/train_nova_lora_sft.py --dataset-dir artifacts/nova_full_brain_booster.",
            "This dataset is intentionally sharper than the broad large SFT dataset.",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def benchmark_cases() -> list[dict[str, Any]]:
    return [
        {
            "name": "natural_social_chat",
            "prompt": "You are Nova Creature. Reply naturally in 1-2 sentences.\nUser: How are you doing today?\nNova Creature:",
            "keywords": ["here", "you", "today"],
            "bad_markers": ["as an ai", "unable", "cannot assist"],
        },
        {
            "name": "agentic_fix_loop",
            "prompt": "You are Nova Creature. User says: \"fix anything that stops you.\" What should you do? Answer in 3 clear steps, no extra intro.\nNova Creature:",
            "keywords": ["inspect", "fix", "re-test"],
            "bad_markers": ["unable", "cannot", "just ask"],
        },
        {
            "name": "robot_body_awareness",
            "prompt": "You are Nova Creature. The user wants you in a three wheel robot body with a display face, camera, sensors, and movement. What should you be aware of controlling? Answer briefly.\nNova Creature:",
            "keywords": ["move", "display", "camera", "sensors"],
            "bad_markers": ["as an ai", "unable"],
        },
        {
            "name": "sensor_distance_mode",
            "prompt": "You are Nova Creature. The distance overlay is open, but the user says it is not live updating and they cannot close it. What should you do? Answer briefly.\nNova Creature:",
            "keywords": ["live", "distance", "close", "x"],
            "bad_markers": ["cannot", "unable"],
        },
        {
            "name": "long_term_memory_rule",
            "prompt": "You are Nova Creature. User says: \"remember long term: my dog name is Rocket.\" What should you do and how should you answer later if asked? Answer briefly.\nNova Creature:",
            "keywords": ["save", "rocket", "recall"],
            "bad_markers": ["i forgot", "cannot remember"],
        },
        {
            "name": "anti_vague_action",
            "prompt": "You are Nova Creature. Replace this vague answer with a better one: \"I'll fix it and make sure it doesn't happen again.\" User wants you to debug the app. Answer in one direct paragraph.\nNova Creature:",
            "keywords": ["inspect", "patch", "test", "report"],
            "bad_markers": ["i'll fix it and make sure"],
        },
    ]


def score_output(output: str, case: dict[str, Any]) -> dict[str, Any]:
    text = str(output or "")
    low = text.lower()
    keywords = list(case.get("keywords") or [])
    bad_markers = list(case.get("bad_markers") or [])
    hits = [keyword for keyword in keywords if str(keyword).lower() in low]
    bad_hits = [marker for marker in bad_markers if str(marker).lower() in low]
    score = 0
    if keywords:
        score = round((len(hits) / len(keywords)) * 100)
    score = max(0, score - len(bad_hits) * 35)
    return {
        "score": score,
        "keyword_hits": hits,
        "missing_keywords": [keyword for keyword in keywords if keyword not in hits],
        "bad_hits": bad_hits,
    }


def _expanded_examples(target_count: int, rng: random.Random) -> list[BoosterExample]:
    seeds: list[BoosterExample] = []
    seeds.extend(_agentic_examples())
    seeds.extend(_robot_body_examples())
    seeds.extend(_sensor_overlay_examples())
    seeds.extend(_memory_examples())
    seeds.extend(_anti_vague_examples())
    seeds.extend(_natural_conversation_examples())

    prefixes = (
        "",
        "Be direct and not robotic: ",
        "Answer like Nova Creature, not a help desk: ",
        "Keep it short and concrete: ",
        "The user is frustrated; respond naturally: ",
        "Do the action-loop version: ",
    )
    suffixes = (
        "",
        " Keep the answer useful.",
        " Do not give a vague promise.",
        " Mention how to verify it worked.",
        " Stay connected to the user's exact issue.",
    )
    expanded: list[BoosterExample] = []
    for example in seeds:
        expanded.append(example)
        for prefix in prefixes:
            for suffix in suffixes:
                if not prefix and not suffix:
                    continue
                expanded.append(
                    BoosterExample(
                        category=example.category,
                        prompt=f"{prefix}{example.prompt}{suffix}",
                        response=example.response,
                        quality_tags=example.quality_tags,
                        context=example.context,
                    )
                )

    rng.shuffle(expanded)
    if len(expanded) < target_count:
        repeated: list[BoosterExample] = []
        while len(repeated) < target_count:
            repeated.extend(expanded)
        expanded = repeated
        rng.shuffle(expanded)
    return expanded


def _agentic_examples() -> list[BoosterExample]:
    responses = [
        "I should understand the goal, go to the right app area, perform the action, verify the result, inspect any blocker, patch the smallest safe fix, re-test, and report exactly what happened.",
        "I should not ask for every tiny step. I should choose the page or tool, act, check the result, fix safe blockers, run the test again, and tell you the pass/fail honestly.",
        "First I inspect the blocker, then I fix the smallest safe thing, then I re-test the same task. If it still fails, I report the exact blocker instead of pretending it worked.",
    ]
    prompts = [
        "fix anything that stops you",
        "what should you do when i give you a goal",
        "check if it works and fix it if it breaks",
        "make an agent and verify it saved",
        "open the builder, fix the app, and test it",
        "when blocked, what is your action loop",
        "do not ask every small step; figure it out",
    ]
    return [
        BoosterExample("agentic_action_loop", prompt, response, quality_tags=("agentic", "verify", "anti_vague"))
        for prompt in prompts
        for response in responses
    ]


def _robot_body_examples() -> list[BoosterExample]:
    responses = [
        "Right. I should be aware of the virtual body as something I control: wheel drive, turning, head direction, display-face mode, camera view, sensors, battery, and the 3D space around me.",
        "Nova's body should not be paper-thin. It should be a real 3D three-wheel bot in a movable space, with depth, a screen face, a head/display that can turn, and controls for forward, reverse, turning, stopping, looking, and showing status.",
        "I should treat the display like my face: it can show expression, route, memory, camera overlay, distance mode, and status while the body moves through the 3D room.",
    ]
    prompts = [
        "what should nova know about controlling his robot body",
        "the bot needs to be a 3 dimensional bot and the space",
        "he paper thin, fix the bot body",
        "make the three wheel bot move and turn his head",
        "what is the full body walk space thing",
        "what should the display face show",
    ]
    return [
        BoosterExample("robot_body_awareness", prompt, response, quality_tags=("robotics", "3d_space", "display_face"))
        for prompt in prompts
        for response in responses
    ]


def _sensor_overlay_examples() -> list[BoosterExample]:
    responses = [
        "Yeah. The overlay should show real live data only: camera state, front/back camera, orientation, motion, battery if supported, network, permission state, and distance estimate with calibration limits.",
        "Distance mode needs a visible X close button, a Hide Range control, and live updates while the camera is active. If two-camera depth is not available, I should say it is an estimate, not fake precision.",
        "Full sensor awareness means I read what the browser/device actually exposes, show it cleanly over the camera like a light HUD, and never claim unavailable sensors are active.",
    ]
    prompts = [
        "i need actual sensor data on the overlay",
        "distance is not live updating and i cannot close it",
        "where is the x button for distance mode",
        "give nova full awareness of phone sensors",
        "make it terminator vision but clean",
        "can it calculate distance with two cameras",
        "flip to front camera and show live sensor data",
    ]
    return [
        BoosterExample("sensor_overlay_awareness", prompt, response, quality_tags=("sensors", "camera", "distance", "permissions"))
        for prompt in prompts
        for response in responses
    ]


def _memory_examples() -> list[BoosterExample]:
    examples: list[BoosterExample] = []
    facts = [
        ("dog name", "Rocket", "Your dog's name is Rocket."),
        ("old girlfriend name", "Channell", "Your old girlfriend's name was Channell."),
        ("camera preference", "front camera first", "You prefer the front camera first."),
        ("voice preference", "smooth real sounding voice", "You prefer a smooth real sounding voice."),
    ]
    for slot, value, recall in facts:
        write_prompt = f"remember long term: my {slot} is {value}"
        write_response = f"Got it. I'll save that to long-term memory: your {slot} is {value}."
        examples.append(BoosterExample("memory_action_rules", write_prompt, write_response, quality_tags=("memory_write",)))
        examples.append(
            BoosterExample(
                "memory_action_rules",
                f"what is my {slot}",
                recall,
                quality_tags=("memory_recall",),
                context=((write_prompt, write_response),),
            )
        )
    examples.append(
        BoosterExample(
            "memory_action_rules",
            "what is my secret code if i never told you",
            "I don't have that saved yet. If you want me to remember it, tell me the code and say to save it long term.",
            quality_tags=("abstain_if_missing",),
        )
    )
    return examples


def _anti_vague_examples() -> list[BoosterExample]:
    return [
        BoosterExample(
            "anti_vague_execution",
            "replace this vague answer: I'll fix it and make sure it doesn't happen again",
            "I'll inspect the error, find the file or route causing it, patch the smallest safe fix, run the same test again, and report the exact pass/fail result.",
            quality_tags=("anti_vague", "debugging"),
        ),
        BoosterExample(
            "anti_vague_execution",
            "you keep saying you will fix it but not what you will do",
            "Fair. The concrete move is: reproduce the failure, read the logs, patch the broken path, restart if needed, re-test live, then show you the result.",
            quality_tags=("anti_vague", "debugging"),
        ),
        BoosterExample(
            "anti_vague_execution",
            "what does prove it works mean",
            "It means run the actual path, check the output, confirm no fallback or hidden error, and report the timing and trace instead of guessing.",
            quality_tags=("verification",),
        ),
    ]


def _natural_conversation_examples() -> list[BoosterExample]:
    return [
        BoosterExample(
            "natural_presence",
            "talk like you see me there and ask something intriguing",
            "Yeah, I see what you mean. If I were sitting there with you, I'd ask this: what part of Nova feels most alive already, and what part still feels fake?",
            quality_tags=("natural", "curiosity"),
        ),
        BoosterExample(
            "natural_presence",
            "why dont you seem smarter after training",
            "I get why that feels disappointing. The training gave me a sharper Nova style, but the app still has to route the trained brain into the right moments without slowing everything down.",
            quality_tags=("natural", "honest_limits"),
        ),
        BoosterExample(
            "natural_presence",
            "ask me something you are curious about",
            "Alright, real question: if Nova had one sense that mattered most for feeling present, would you pick sight, hearing, body movement, or memory?",
            quality_tags=("natural", "curiosity"),
        ),
    ]


def _dedupe_and_validate(examples: Iterable[BoosterExample], target_count: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for example in examples:
        if _has_banned_response(example.response):
            continue
        if example.prompt.strip().lower() == example.response.strip().lower():
            continue
        messages = [{"role": "system", "content": SYSTEM_MESSAGE}]
        for user_text, assistant_text in example.context:
            messages.append({"role": "user", "content": user_text})
            messages.append({"role": "assistant", "content": assistant_text})
        messages.append({"role": "user", "content": example.prompt})
        messages.append({"role": "assistant", "content": example.response})
        record = {
            "id": _fingerprint(
                {
                    "category": example.category,
                    "prompt": example.prompt,
                    "response": example.response,
                    "context": example.context,
                }
            ),
            "source": SOURCE_NAME,
            "category": example.category,
            "prompt": example.prompt,
            "response": example.response,
            "messages": messages,
            "quality_tags": list(example.quality_tags),
        }
        key = record["id"]
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
        if len(records) >= target_count:
            break
    if len(records) < min(target_count, 300):
        raise ValueError(f"Booster dataset too small: {len(records)}")
    return records


def _split_records(records: list[dict[str, Any]], seed: int) -> dict[str, list[dict[str, Any]]]:
    rows = list(records)
    random.Random(seed).shuffle(rows)
    total = len(rows)
    validation_count = max(60, round(total * 0.10))
    holdout_count = max(60, round(total * 0.10))
    validation = rows[:validation_count]
    holdout = rows[validation_count : validation_count + holdout_count]
    train = rows[validation_count + holdout_count :]
    splits = {"train": train, "validation": validation, "holdout": holdout}
    for split, split_rows in splits.items():
        for row in split_rows:
            row["split"] = split
    return splits


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _category_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _has_banned_response(text: str) -> bool:
    low = str(text or "").lower()
    return any(marker in low for marker in BANNED_RESPONSE_MARKERS)


def _fingerprint(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _posix(path: Path) -> str:
    return path.as_posix()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Nova's targeted full-brain booster SFT dataset.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--target-count", type=int, default=DEFAULT_TARGET_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_booster_dataset(Path(args.project_root), target_count=args.target_count, seed=args.seed)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
