#!/usr/bin/env python3
"""Build fine-tune approval package and owner review summary."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v184_finetune_approval_package import build_approval_package

def main():
    r = build_approval_package()
    print(f"Approval Package Summary\n")
    print(f"  Approved lessons: {r['approved_lessons']}")
    print(f"  Rejected lessons: {r['rejected_lessons']}")
    print(f"  Pending lessons:   {r['pending_lessons']}")
    print(f"\n  Lessons by role:")
    for role, count in r.get("lessons_by_role",{}).items():
        print(f"    {role}: {count}")
    print(f"\n  Lessons by skill:")
    for skill, count in r.get("lessons_by_skill",{}).items():
        print(f"    {skill}: {count}")
    print(f"\n  Owner approval present: {r['owner_approval_present']}")
    print(f"  Fine-tune blocked: {r['finetune_blocked']}")
    if r['finetune_blocked']:
        print(f"  Reason: {r['block_reason_if_blocked']}")
    print(f"\n  Expected maturity gain: {r['expected_maturity_gain']}")
    print(f"  Finetune command: {r['finetune_command']}")
    print(f"  Rollback plan: {r['rollback_plan']}")

    (ROOT/"reports"/"v184_finetune_approval_package_status.json").write_text(json.dumps(r, indent=2))

    # Write owner review markdown
    md = f"""# Nova v184 — Owner Review: Training & Fine-Tune Approval

## Training Batch Summary
- **Approved lessons:** {r['approved_lessons']}
- **Rejected lessons:** {r['rejected_lessons']}
- **Pending lessons:** {r['pending_lessons']}

## Lessons by Role
"""
    for role, count in r.get("lessons_by_role",{}).items():
        md += f"- **{role}:** {count} lessons\n"
    md += f"""
## Lessons by Skill Target
"""
    for skill, count in r.get("lessons_by_skill",{}).items():
        md += f"- **{skill}:** {count} lessons\n"
    md += f"""
## Risk Assessment
{r['risk_summary']}

## Blocked Items
"""
    for item in r.get("blocked_items",[]):
        md += f"- {item}\n"
    md += f"""
## Benchmarks to Run Before Fine-Tune
"""
    for bt in r.get("benchmark_tests_to_run_before",[]):
        md += f"- {bt}\n"
    md += f"""
## Benchmarks to Run After Fine-Tune
"""
    for bt in r.get("benchmark_tests_to_run_after",[]):
        md += f"- {bt}\n"
    md += f"""
## Fine-Tune Command (if approved)
```
{r['finetune_command']}
```

## Rollback Plan
{r['rollback_plan']}

## Checkpoint Tournament Plan
{r['checkpoint_tournament_plan']}

## Approval Status
**Owner approval present:** {r['owner_approval_present']}
**Fine-tune blocked:** {r['finetune_blocked']}
{r['block_reason_if_blocked'] if r['finetune_blocked'] else 'Ready to proceed if you approve.'}
"""
    (ROOT/"reports"/"v184_owner_review_training_summary.md").write_text(md)
    print(f"\nReport: reports/v184_finetune_approval_package_status.json")
    print(f"Owner review: reports/v184_owner_review_training_summary.md")
    return 0
if __name__ == "__main__": raise SystemExit(main())
