# Transformer Route Hyper-Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair Nova’s live transformer route, train learned routing and seven role-specific answer models, and promote only a candidate that proves improvement on sealed tests without regressions.

**Architecture:** Add a deterministic byte tokenizer and a small PyTorch decoder-only transformer so the project can bootstrap real, trainable checkpoints without the missing historical model files. Build a guarded dual loop: a learned route classifier selects roles, role language models generate answers, and a registry/evaluator atomically promotes only candidates that beat the frozen baseline and previous winner.

**Tech Stack:** Python 3.11, PyTorch CPU, pytest, JSON/JSONL artifacts, existing Nova HTTP server and hybrid router.

---

## File Structure

### New runtime and training modules

- `src/nova_training_types.py` — shared role names, dataclasses, metric/result contracts.
- `src/nova_byte_tokenizer.py` — deterministic UTF-8 byte tokenizer with no unknown-token loss.
- `src/nova_torch_transformer.py` — trainable decoder-only transformer and checkpoint serialization.
- `src/nova_checkpoint_registry.py` — baseline/candidate/winner/rollback metadata and atomic promotion.
- `src/nova_training_preflight.py` — dependency, tokenizer, checkpoint, tensor, and registry validation.
- `src/nova_training_dataset.py` — source ingestion, quarantine, role labeling, grouped split, fingerprints.
- `src/nova_route_model.py` — learned domain/primary-role classifier and metrics.
- `src/nova_role_trainer.py` — answer-masked role fine-tuning with validation and early stopping.
- `src/nova_transformer_runtime.py` — promoted model loading, learned routing, generation result contract.
- `src/nova_hyper_training_evaluator.py` — baseline/candidate scoring, negative controls, promotion law.
- `src/nova_hyper_training_orchestrator.py` — end-to-end experiment, reporting, promotion/rollback.

### New commands and fixtures

- `scripts/bootstrap_nova_transformers.py` — explicit seeded base and seven-role baseline creation.
- `scripts/run_transformer_hyper_training.py` — preflight, baseline, training, evaluation, reporting.
- `benchmark_lab/test_banks/transformer_route_promotion_bank.json` — sealed route/answer cases.
- `requirements-training.txt` — pinned training and test dependencies.

### Existing integration points

- `src/nova_hybrid_router.py` — consume learned route/runtime results and expose transformer evidence.
- `src/v055_assisted_learning_bridge.py` — delegate fine-tuning to the guarded orchestrator; remove noise training.
- `src/v059_checkpoint_resolver.py` — delegate live selection to the registry.
- `nova_enhanced_server.py` — route “deep learn” through the guarded orchestrator and expose run status.
- `.gitignore` — ignore generated checkpoints, candidate artifacts, registry lock files, and run caches.

### Tests

- `tests/test_nova_byte_tokenizer.py`
- `tests/test_nova_torch_transformer.py`
- `tests/test_nova_checkpoint_registry.py`
- `tests/test_nova_training_preflight.py`
- `tests/test_nova_training_dataset.py`
- `tests/test_nova_route_model.py`
- `tests/test_nova_role_trainer.py`
- `tests/test_nova_transformer_runtime.py`
- `tests/test_nova_hyper_training_evaluator.py`
- `tests/test_nova_transformer_route_integration.py`
- `tests/test_nova_hyper_training_orchestrator.py`

---

### Task 1: Establish the training environment and shared contracts

**Files:**
- Create: `requirements-training.txt`
- Create: `src/nova_training_types.py`
- Test: `tests/test_nova_training_types.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing shared-contract test**

```python
# tests/test_nova_training_types.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_types import GenerationResult, ROLE_NAMES


def test_generation_result_requires_transformer_evidence():
    result = GenerationResult(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path="checkpoints/brain_slots/left_hemisphere/winner.pt",
        checkpoint_hash="a" * 64,
        tokens_generated=4,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
    )
    assert len(ROLE_NAMES) == 7
    assert result.ok is True
    assert result.to_trace()["source"] == "transformer"
    assert result.to_trace()["checkpoint_hash"] == "a" * 64


def test_generation_result_with_error_is_not_ok():
    result = GenerationResult.failed("planner_transformer", "checkpoint missing")
    assert result.ok is False
    assert result.error == "checkpoint missing"
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_training_types.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'nova_training_types'`.

- [ ] **Step 3: Add the dependency manifest**

```text
# requirements-training.txt
numpy>=2.0,<3
pytest>=8.0,<9
torch>=2.7,<3
```

- [ ] **Step 4: Implement the shared contracts**

```python
# src/nova_training_types.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

ROLE_NAMES = (
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
)

DOMAIN_NAMES = (
    "coding",
    "math",
    "science",
    "philosophy",
    "psychology",
    "creative",
    "memory_recall",
    "planning",
    "critic",
    "speech",
    "dream",
    "general",
)


@dataclass(frozen=True)
class GenerationResult:
    text: str
    role: str
    checkpoint_path: str
    checkpoint_hash: str
    tokens_generated: int
    elapsed_seconds: float
    tokens_per_second: float
    finish_reason: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip()) and bool(self.checkpoint_hash)

    @classmethod
    def failed(cls, role: str, error: str) -> "GenerationResult":
        return cls("", role, "", "", 0, 0.0, 0.0, "error", error)

    def to_trace(self) -> dict:
        return {"source": "transformer", **asdict(self), "ok": self.ok}


@dataclass(frozen=True)
class RoutePrediction:
    domain: str
    primary_role: str
    support_roles: Sequence[str]
    confidence: float
    model_hash: str
    source: str = "learned_route_model"


@dataclass(frozen=True)
class PromotionDecision:
    verdict: str
    reasons: Sequence[str]
    baseline_joint: float
    candidate_joint: float
    previous_winner_joint: float | None
```

- [ ] **Step 5: Extend generated-artifact ignores**

```gitignore
# Transformer hyper-training artifacts
checkpoints/
artifacts/transformer_training/
data/transformer_training_runs/
*.registry.lock
```

- [ ] **Step 6: Install the declared environment and run GREEN**

Run:

```powershell
py -3 -m pip install -r requirements-training.txt
py -3 -m pytest tests/test_nova_training_types.py -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```powershell
git add requirements-training.txt src/nova_training_types.py tests/test_nova_training_types.py .gitignore
git commit -m "build: add transformer training contracts"
```

---

### Task 2: Implement a lossless tokenizer and real trainable transformer

**Files:**
- Create: `src/nova_byte_tokenizer.py`
- Create: `src/nova_torch_transformer.py`
- Test: `tests/test_nova_byte_tokenizer.py`
- Test: `tests/test_nova_torch_transformer.py`

- [ ] **Step 1: Write failing tokenizer tests**

```python
# tests/test_nova_byte_tokenizer.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_byte_tokenizer import NovaByteTokenizer


def test_utf8_round_trip_has_no_unknown_tokens():
    tokenizer = NovaByteTokenizer()
    text = "Nova can debug Python — café 🚀"
    ids = tokenizer.encode(text)
    assert tokenizer.decode(ids) == text
    assert tokenizer.vocab_size == 260
    assert ids[0] == tokenizer.BOS
    assert ids[-1] == tokenizer.EOS


def test_answer_boundary_is_preserved():
    tokenizer = NovaByteTokenizer()
    prompt_ids, answer_ids = tokenizer.encode_pair("Question?", "Answer.")
    assert tokenizer.decode(prompt_ids) == "Question?"
    assert tokenizer.decode(answer_ids) == "Answer."
```

- [ ] **Step 2: Run tokenizer tests and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_byte_tokenizer.py -q
```

Expected: import failure for `nova_byte_tokenizer`.

- [ ] **Step 3: Implement the byte tokenizer**

```python
# src/nova_byte_tokenizer.py
from __future__ import annotations


class NovaByteTokenizer:
    PAD = 0
    BOS = 1
    EOS = 2
    SEP = 3
    BYTE_OFFSET = 4
    vocab_size = 260

    def encode(self, text: str, *, add_special: bool = True) -> list[int]:
        payload = [byte + self.BYTE_OFFSET for byte in str(text).encode("utf-8")]
        return [self.BOS, *payload, self.EOS] if add_special else payload

    def decode(self, token_ids: list[int]) -> str:
        payload = bytes(
            token_id - self.BYTE_OFFSET
            for token_id in token_ids
            if self.BYTE_OFFSET <= int(token_id) < self.vocab_size
        )
        return payload.decode("utf-8", errors="replace")

    def encode_pair(self, prompt: str, answer: str) -> tuple[list[int], list[int]]:
        return self.encode(prompt), self.encode(answer)
```

- [ ] **Step 4: Run tokenizer tests and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_byte_tokenizer.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Write failing model tests**

```python
# tests/test_nova_torch_transformer.py
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_torch_transformer import ModelConfig, NovaCausalLM, load_checkpoint, save_checkpoint


def test_model_computes_answer_masked_loss(tmp_path):
    torch.manual_seed(7)
    config = ModelConfig(vocab_size=260, block_size=32, d_model=32, n_heads=4, n_layers=1, dropout=0.0)
    model = NovaCausalLM(config)
    tokens = torch.tensor([[1, 10, 11, 3, 12, 13, 2]], dtype=torch.long)
    targets = tokens.clone()
    targets[:, :4] = -100
    logits, loss = model(tokens, targets)
    assert logits.shape == (1, 7, 260)
    assert torch.isfinite(loss)


def test_checkpoint_round_trip_preserves_logits(tmp_path):
    torch.manual_seed(11)
    config = ModelConfig(vocab_size=260, block_size=32, d_model=32, n_heads=4, n_layers=1, dropout=0.0)
    model = NovaCausalLM(config).eval()
    tokens = torch.tensor([[1, 40, 41, 2]], dtype=torch.long)
    expected, _ = model(tokens)
    path = tmp_path / "model.pt"
    save_checkpoint(path, model, metadata={"role": "left_hemisphere"})
    loaded, payload = load_checkpoint(path)
    actual, _ = loaded.eval()(tokens)
    assert payload["metadata"]["role"] == "left_hemisphere"
    assert torch.equal(expected, actual)
```

- [ ] **Step 6: Run model tests and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_torch_transformer.py -q
```

Expected: import failure for `nova_torch_transformer`.

- [ ] **Step 7: Implement the PyTorch transformer**

Create `src/nova_torch_transformer.py` with `ModelConfig`, `NovaCausalLM`, `save_checkpoint`, and `load_checkpoint` as public names:

```python
@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 260
    block_size: int = 192
    d_model: int = 96
    n_heads: int = 4
    n_layers: int = 2
    dropout: float = 0.1
```

Use the existing architecture in `nova_mini_llm/model.py` as the behavioral reference, but implement the complete module in `src` with:

```python
loss = F.cross_entropy(
    logits.reshape(-1, logits.size(-1)),
    targets.reshape(-1),
    ignore_index=-100,
)
```

`save_checkpoint()` writes to `path.with_suffix(".tmp")`, includes `format_version`, `config`, `model_state`, and `metadata`, then atomically replaces the target. `load_checkpoint()` uses `weights_only=False`, reconstructs `ModelConfig`, loads with `strict=True`, and rejects non-finite parameters.

- [ ] **Step 8: Run model tests and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_torch_transformer.py -q
```

Expected: `2 passed`.

- [ ] **Step 9: Commit**

```powershell
git add src/nova_byte_tokenizer.py src/nova_torch_transformer.py tests/test_nova_byte_tokenizer.py tests/test_nova_torch_transformer.py
git commit -m "feat: add trainable Nova transformer core"
```

---

### Task 3: Bootstrap real seeded baselines and enforce registry-controlled loading

**Files:**
- Create: `src/nova_checkpoint_registry.py`
- Create: `scripts/bootstrap_nova_transformers.py`
- Test: `tests/test_nova_checkpoint_registry.py`
- Modify: `src/v059_checkpoint_resolver.py`

- [ ] **Step 1: Write failing registry tests**

```python
# tests/test_nova_checkpoint_registry.py
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry


def test_registry_prefers_promoted_winner(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline.write_bytes(b"baseline")
    candidate.write_bytes(b"candidate")
    registry.register_baseline("left_hemisphere", baseline, "basehash")
    registry.register_candidate("left_hemisphere", candidate, "candidatehash", {"joint": 88.0})
    assert registry.resolve_live("left_hemisphere").path == baseline
    registry.promote("left_hemisphere", "candidatehash")
    assert registry.resolve_live("left_hemisphere").path == candidate


def test_rejected_candidate_never_becomes_live(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline.write_bytes(b"baseline")
    candidate.write_bytes(b"candidate")
    registry.register_baseline("planner_transformer", baseline, "basehash")
    registry.register_candidate("planner_transformer", candidate, "candidatehash", {"joint": 70.0})
    registry.reject("planner_transformer", "candidatehash", ["route regression"])
    assert registry.resolve_live("planner_transformer").path == baseline
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_checkpoint_registry.py -q
```

Expected: import failure for `nova_checkpoint_registry`.

- [ ] **Step 3: Implement the registry**

`src/nova_checkpoint_registry.py` must expose the immutable result type:

```python
@dataclass(frozen=True)
class ResolvedCheckpoint:
    role: str
    path: Path
    sha256: str
    status: str
    metrics: dict
```

Implement `CheckpointRegistry.__init__(project_root)`, `register_baseline(role, path, sha256)`, `register_candidate(role, path, sha256, metrics)`, `promote(role, candidate_sha256)`, `reject(role, candidate_sha256, reasons)`, `resolve_live(role)`, and `snapshot()`. Store registry data at `checkpoints/registry.json`. Use a temporary JSON file and `Path.replace()` for every write. `promote()` records the previous winner as `rollback_sha256`.

- [ ] **Step 4: Run registry tests and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_checkpoint_registry.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Write the bootstrap command**

`scripts/bootstrap_nova_transformers.py` must require the explicit flag `--initialize-approved-base` and:

```python
torch.manual_seed(args.seed)
config = ModelConfig()
base_model = NovaCausalLM(config)
base_path = root / "checkpoints" / "base" / "nova_seeded_base.pt"
base_hash = save_checkpoint(
    base_path,
    base_model,
    metadata={
        "status": "fresh_seeded_base",
        "approved_by": "explicit_cli_flag",
        "seed": args.seed,
    },
)
for role in ROLE_NAMES:
    role_path = root / "checkpoints" / "brain_slots" / role / f"{role}_baseline.pt"
    shutil.copy2(base_path, role_path)
    registry.register_baseline(role, role_path, sha256(role_path))
```

Exit nonzero if the flag is absent. Never write a text placeholder.

- [ ] **Step 6: Delegate the legacy resolver**

Replace the candidate list inside `src/v059_checkpoint_resolver.py:34-77` with:

```python
registry = CheckpointRegistry(root())
resolved = registry.resolve_live(role)
return {
    "role": role,
    "selected_checkpoint": str(resolved.path.relative_to(root())),
    "checkpoint_version": resolved.status,
    "exists": resolved.path.exists(),
    "size_bytes": resolved.path.stat().st_size,
    "sha256": resolved.sha256,
    "fallback_used": resolved.status == "baseline",
    "promote_ready": resolved.status == "promoted",
}
```

- [ ] **Step 7: Bootstrap and verify seven real baselines**

Run:

```powershell
py -3 scripts/bootstrap_nova_transformers.py --initialize-approved-base --seed 20260622
py -3 -c "from pathlib import Path; print(len(list(Path('checkpoints/brain_slots').glob('*/*_baseline.pt'))))"
```

Expected: `7`.

- [ ] **Step 8: Commit**

```powershell
git add src/nova_checkpoint_registry.py scripts/bootstrap_nova_transformers.py tests/test_nova_checkpoint_registry.py src/v059_checkpoint_resolver.py
git commit -m "feat: add guarded checkpoint registry"
```

---

### Task 4: Add a hard preflight that blocks fake readiness

**Files:**
- Create: `src/nova_training_preflight.py`
- Test: `tests/test_nova_training_preflight.py`

- [ ] **Step 1: Write failing preflight tests**

```python
# tests/test_nova_training_preflight.py
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_preflight import run_preflight


def test_preflight_rejects_placeholder_checkpoint(tmp_path):
    role_dir = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere"
    role_dir.mkdir(parents=True)
    (role_dir / "left_hemisphere_baseline.pt").write_text("PLACEHOLDER", encoding="utf-8")
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))
    assert result["verdict"] == "BLOCKED"
    assert any("placeholder" in reason.lower() or "invalid" in reason.lower() for reason in result["reasons"])


def test_preflight_accepts_valid_registry_checkpoint(tmp_path):
    from nova_checkpoint_registry import CheckpointRegistry
    from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint

    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    model = NovaCausalLM(ModelConfig(d_model=32, n_heads=4, n_layers=1, block_size=32))
    digest = save_checkpoint(path, model, {"role": "left_hemisphere"})
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, digest)
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))
    assert result["verdict"] == "READY"
    assert result["roles_ready"] == 1
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_training_preflight.py -q
```

Expected: import failure for `nova_training_preflight`.

- [ ] **Step 3: Implement preflight**

`run_preflight(project_root, required_roles=ROLE_NAMES)` must:

```python
checks = {
    "python": sys.version_info >= (3, 11),
    "torch": importlib.util.find_spec("torch") is not None,
    "pytest": importlib.util.find_spec("pytest") is not None,
}
for role in required_roles:
    resolved = registry.resolve_live(role)
    model, payload = load_checkpoint(resolved.path)
    assert payload["config"]["vocab_size"] == NovaByteTokenizer.vocab_size
    assert all(torch.isfinite(parameter).all() for parameter in model.parameters())
```

Return a JSON-serializable dictionary with `verdict`, `reasons`, `checks`, `roles_ready`, runtime versions, and hashes. Catch each failure and report the role/path; never use a blanket `except: pass`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_training_preflight.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Run the real preflight**

Run:

```powershell
py -3 -m nova_training_preflight
```

Expected: verdict `READY`, `roles_ready: 7`.

- [ ] **Step 6: Commit**

```powershell
git add src/nova_training_preflight.py tests/test_nova_training_preflight.py
git commit -m "feat: block invalid transformer training runs"
```

---

### Task 5: Build clean, grouped, leak-resistant training data

**Files:**
- Create: `src/nova_training_dataset.py`
- Test: `tests/test_nova_training_dataset.py`
- Create: `benchmark_lab/test_banks/transformer_route_promotion_bank.json`

- [ ] **Step 1: Write failing cleaner and split tests**

```python
# tests/test_nova_training_dataset.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_dataset import clean_record, grouped_split


def test_recursive_followup_is_quarantined():
    record = {
        "user": "yeah",
        "nova": "I recall your last question. I recall your last question. More?",
        "source": "conversation",
    }
    cleaned, reason = clean_record(record)
    assert cleaned is None
    assert reason == "recursive_followup"


def test_truncated_answer_is_quarantined():
    cleaned, reason = clean_record(
        {"prompt": "What is love?", "answer": "Love is a deep emotional bon", "source": "dictionary_hit"}
    )
    assert cleaned is None
    assert reason == "truncated_answer"


def test_paraphrase_group_never_crosses_splits():
    rows = [
        {"id": "1", "intent_group": "creator_identity", "prompt": "Who made you?", "answer": "Mr. Novotron."},
        {"id": "2", "intent_group": "creator_identity", "prompt": "Who created you?", "answer": "Mr. Novotron."},
        {"id": "3", "intent_group": "quadratic", "prompt": "Quadratic formula?", "answer": "x = (-b ± sqrt(b² - 4ac)) / (2a)."},
    ]
    splits = grouped_split(rows, seed=20260622)
    locations = {
        row["intent_group"]: split
        for split, values in splits.items()
        for row in values
    }
    assert sum(any(row["intent_group"] == "creator_identity" for row in values) for values in splits.values()) == 1
    assert set(splits) == {"train", "validation", "promotion"}
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_training_dataset.py -q
```

Expected: import failure for `nova_training_dataset`.

- [ ] **Step 3: Implement normalized records and quarantine rules**

Use this accepted-record shape:

```python
{
    "id": stable_sha256,
    "source": source,
    "intent_group": intent_group,
    "domain": domain,
    "primary_role": role,
    "support_roles": support_roles,
    "prompt": prompt,
    "answer": answer,
    "quality_flags": [],
}
```

`clean_record()` must reject:

```python
if answer.lower().count("i recall your last question") >= 2:
    return None, "recursive_followup"
if answer in FALLBACK_TEMPLATES:
    return None, "fallback_template"
if len(answer.strip()) < 2:
    return None, "empty_answer"
if looks_truncated(answer):
    return None, "truncated_answer"
if repetition_ratio(answer) > 0.35:
    return None, "high_repetition"
```

`grouped_split()` hashes `f"{seed}:{intent_group}"` into 100 buckets: `0-69` train, `70-84` validation, `85-99` promotion.

- [ ] **Step 4: Add the sealed benchmark bank**

Create JSON with at least three cases per role and these required fields:

```json
[
  {
    "id": "route-coding-001",
    "prompt": "Help me debug a Python loop that never stops.",
    "domain": "coding",
    "primary_role": "left_hemisphere",
    "required_terms": ["loop"],
    "protected": true
  },
  {
    "id": "route-planning-001",
    "prompt": "Give me an ordered plan to test and release this app.",
    "domain": "planning",
    "primary_role": "planner_transformer",
    "required_terms": ["test", "release"],
    "protected": true
  },
  {
    "id": "route-critic-001",
    "prompt": "Verify this claim and say when the evidence is insufficient.",
    "domain": "critic",
    "primary_role": "critic_conscience_transformer",
    "required_terms": ["evidence"],
    "protected": true
  },
  {
    "id": "route-creative-001",
    "prompt": "Design a calm blue visual pattern for Nova's interface.",
    "domain": "creative",
    "primary_role": "right_hemisphere",
    "required_terms": ["blue"],
    "protected": true
  },
  {
    "id": "route-memory-001",
    "prompt": "Who created Nova Creature?",
    "domain": "memory_recall",
    "primary_role": "memory_transformer",
    "required_terms": ["Mr. Novotron"],
    "protected": true
  },
  {
    "id": "route-dream-001",
    "prompt": "Simulate what happens if the first deployment fails.",
    "domain": "dream",
    "primary_role": "dream_simulation_transformer",
    "required_terms": ["if"],
    "protected": true
  },
  {
    "id": "route-speech-001",
    "prompt": "Explain transformer routing in one clear sentence.",
    "domain": "speech",
    "primary_role": "speech_output_transformer",
    "required_terms": ["route"],
    "protected": true
  }
]
```

Expand this exact pattern to 21 total cases, varying wording without duplicating training examples.

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_training_dataset.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Build the real cleaned dataset**

Run:

```powershell
py -3 -m nova_training_dataset --project-root .
```

Expected outputs:

- `artifacts/transformer_training/dataset/train.jsonl`
- `artifacts/transformer_training/dataset/validation.jsonl`
- `artifacts/transformer_training/dataset/promotion.jsonl`
- `artifacts/transformer_training/dataset/quarantine.jsonl`
- `artifacts/transformer_training/dataset/manifest.json`

- [ ] **Step 7: Commit**

```powershell
git add src/nova_training_dataset.py tests/test_nova_training_dataset.py benchmark_lab/test_banks/transformer_route_promotion_bank.json
git commit -m "feat: build guarded transformer datasets"
```

---

### Task 6: Train and evaluate the learned route classifier

**Files:**
- Create: `src/nova_route_model.py`
- Test: `tests/test_nova_route_model.py`

- [ ] **Step 1: Write failing route-model tests**

```python
# tests/test_nova_route_model.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_route_model import RouteExample, train_route_model, evaluate_route_model


def examples():
    return [
        RouteExample("debug this Python function", "coding", "left_hemisphere"),
        RouteExample("solve this equation", "math", "left_hemisphere"),
        RouteExample("make an ordered release plan", "planning", "planner_transformer"),
        RouteExample("check whether this claim is true", "critic", "critic_conscience_transformer"),
        RouteExample("imagine a visual pattern", "creative", "right_hemisphere"),
        RouteExample("remember who made you", "memory_recall", "memory_transformer"),
        RouteExample("simulate a failed launch", "dream", "dream_simulation_transformer"),
        RouteExample("explain this clearly", "speech", "speech_output_transformer"),
    ]


def test_route_training_beats_untrained_baseline(tmp_path):
    model, metadata = train_route_model(examples() * 8, seed=7, epochs=80)
    metrics = evaluate_route_model(model, examples())
    assert metrics["primary_role_accuracy"] >= 0.75
    assert metrics["macro_f1"] >= 0.70
    assert metadata["seed"] == 7


def test_shuffled_labels_fail_negative_control():
    rows = examples() * 6
    shuffled = [
        RouteExample(row.text, row.domain, rows[(index + 1) % len(rows)].primary_role)
        for index, row in enumerate(rows)
    ]
    model, _ = train_route_model(shuffled, seed=11, epochs=20)
    metrics = evaluate_route_model(model, examples())
    assert metrics["macro_f1"] < 0.70
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_route_model.py -q
```

Expected: import failure for `nova_route_model`.

- [ ] **Step 3: Implement the classifier**

Use byte-token mean pooling:

```python
class NovaRouteClassifier(nn.Module):
    def __init__(self, vocab_size: int, hidden_size: int, domain_count: int, role_count: int):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, hidden_size, padding_idx=0)
        self.encoder = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.GELU(),
            nn.Dropout(0.1),
        )
        self.domain_head = nn.Linear(hidden_size, domain_count)
        self.role_head = nn.Linear(hidden_size, role_count)

    def forward(self, token_ids, mask):
        embedded = self.embedding(token_ids)
        pooled = (embedded * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        hidden = self.encoder(pooled)
        return self.domain_head(hidden), self.role_head(hidden)
```

Train with summed domain and role cross-entropy, deterministic seed, AdamW, gradient clipping, and best validation macro F1. Save class maps and model hash beside the state dict.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_route_model.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/nova_route_model.py tests/test_nova_route_model.py
git commit -m "feat: train learned transformer routes"
```

---

### Task 7: Train role answer models with answer-only loss

**Files:**
- Create: `src/nova_role_trainer.py`
- Test: `tests/test_nova_role_trainer.py`

- [ ] **Step 1: Write failing role-trainer tests**

```python
# tests/test_nova_role_trainer.py
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_byte_tokenizer import NovaByteTokenizer
from nova_role_trainer import build_supervised_sequence, train_role_candidate
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint


def test_prompt_tokens_are_masked_from_answer_loss():
    tokenizer = NovaByteTokenizer()
    token_ids, targets = build_supervised_sequence(tokenizer, "Question?", "Answer.", block_size=64)
    sep_index = token_ids.index(tokenizer.SEP)
    assert all(value == -100 for value in targets[: sep_index + 1])
    assert any(value != -100 for value in targets[sep_index + 1 :])


def test_role_training_reduces_validation_loss(tmp_path):
    torch.manual_seed(5)
    baseline = tmp_path / "baseline.pt"
    save_checkpoint(
        baseline,
        NovaCausalLM(ModelConfig(block_size=64, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
        {"role": "memory_transformer"},
    )
    rows = [
        {"prompt": "Who created Nova?", "answer": "Mr. Novotron."},
        {"prompt": "What is Nova's name?", "answer": "Nova Creature."},
    ] * 12
    result = train_role_candidate(
        role="memory_transformer",
        baseline_path=baseline,
        train_rows=rows[:18],
        validation_rows=rows[18:],
        output_path=tmp_path / "candidate.pt",
        seed=5,
        epochs=30,
    )
    assert result["best_validation_loss"] < result["baseline_validation_loss"]
    assert Path(result["checkpoint_path"]).exists()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_role_trainer.py -q
```

Expected: import failure for `nova_role_trainer`.

- [ ] **Step 3: Implement answer-masked sequence building**

```python
def build_supervised_sequence(tokenizer, prompt, answer, block_size):
    prompt_ids = tokenizer.encode(prompt, add_special=False)
    answer_ids = tokenizer.encode(answer, add_special=False)
    token_ids = [tokenizer.BOS, *prompt_ids, tokenizer.SEP, *answer_ids, tokenizer.EOS]
    token_ids = token_ids[:block_size]
    targets = token_ids[1:] + [tokenizer.EOS]
    sep_index = token_ids.index(tokenizer.SEP)
    for index in range(min(sep_index + 1, len(targets))):
        targets[index] = -100
    return token_ids, targets
```

- [ ] **Step 4: Implement guarded role training**

`train_role_candidate()` must:

- load the frozen baseline;
- measure baseline validation loss before updates;
- shuffle only with a seeded generator;
- use mini-batches and `AdamW`;
- clip gradient norm at `1.0`;
- abort on non-finite loss or gradients;
- retain the lowest-validation-loss state;
- stop after five validation checks without improvement;
- save to a candidate path, never overwrite baseline/live;
- return losses, steps, duration, hashes, seed, and checkpoint path.

Use:

```python
optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=0.01)
torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_role_trainer.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/nova_role_trainer.py tests/test_nova_role_trainer.py
git commit -m "feat: train role answers with masked loss"
```

---

### Task 8: Repair the live transformer runtime and hybrid route contract

**Files:**
- Create: `src/nova_transformer_runtime.py`
- Test: `tests/test_nova_transformer_runtime.py`
- Modify: `src/nova_hybrid_router.py:27-165`

- [ ] **Step 1: Write failing runtime tests**

```python
# tests/test_nova_transformer_runtime.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint
from nova_transformer_runtime import NovaTransformerRuntime


class FixedRouteModel:
    model_hash = "routehash"

    def predict(self, text):
        from nova_training_types import RoutePrediction
        return RoutePrediction("coding", "left_hemisphere", ("planner_transformer",), 0.91, self.model_hash)


def test_runtime_returns_generation_evidence(tmp_path):
    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    digest = save_checkpoint(
        path,
        NovaCausalLM(ModelConfig(block_size=64, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
        {"role": "left_hemisphere"},
    )
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, digest)
    runtime = NovaTransformerRuntime(tmp_path, route_model=FixedRouteModel())
    route = runtime.route("debug this code")
    result = runtime.generate(route.primary_role, "debug this code", max_new_tokens=4)
    assert route.source == "learned_route_model"
    assert result.role == "left_hemisphere"
    assert result.checkpoint_hash == digest
    assert result.to_trace()["source"] == "transformer"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_transformer_runtime.py -q
```

Expected: import failure for `nova_transformer_runtime`.

- [ ] **Step 3: Implement the runtime**

`NovaTransformerRuntime` must:

```python
class NovaTransformerRuntime:
    def __init__(self, project_root: Path, route_model=None):
        self.project_root = project_root
        self.registry = CheckpointRegistry(project_root)
        self.tokenizer = NovaByteTokenizer()
        self.route_model = route_model or load_promoted_route_model(project_root)
        self.models = {}
```

Add `route(text: str) -> RoutePrediction` and `generate(role: str, prompt: str, max_new_tokens: int = 80) -> GenerationResult`. `generate()` resolves the live checkpoint through the registry, caches by `(role, sha256)`, creates `[BOS] prompt [SEP]`, greedily generates, decodes only tokens after `SEP`, rejects empty/repetitive output, and returns `GenerationResult`.

- [ ] **Step 4: Repair `nova_hybrid_router.py`**

Replace `_ensure_brain()` with:

```python
def _ensure_brain():
    global BRAIN
    if BRAIN is None:
        from nova_transformer_runtime import NovaTransformerRuntime
        BRAIN = NovaTransformerRuntime(ROOT)
    return BRAIN
```

Replace `generate_transformer_response()` with a contract that returns `(GenerationResult | None, RoutePrediction)` and does not treat tuples as strings:

```python
prediction = brain.route(text)
result = brain.generate(prediction.primary_role, text, max_new_tokens=80)
if not result.ok:
    return None, prediction
return result, prediction
```

Add `transformer_only: bool = False` to `route_and_respond()`. When true, skip dictionary and memory paths and return an explicit error rather than a fallback template if transformer generation fails.

The successful trace must include:

```python
trace.update({
    "source": "transformer",
    "domain": prediction.domain,
    "roles": [prediction.primary_role, *prediction.support_roles],
    "confidence": prediction.confidence,
    "route_model_hash": prediction.model_hash,
    "checkpoint_hash": result.checkpoint_hash,
    "checkpoint_path": result.checkpoint_path,
    "generation": result.to_trace(),
})
```

- [ ] **Step 5: Run runtime tests and focused router tests**

Run:

```powershell
py -3 -m pytest tests/test_nova_transformer_runtime.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/nova_transformer_runtime.py tests/test_nova_transformer_runtime.py src/nova_hybrid_router.py
git commit -m "fix: wire verified transformer routes"
```

---

### Task 9: Build the evaluator, promotion law, and negative controls

**Files:**
- Create: `src/nova_hyper_training_evaluator.py`
- Test: `tests/test_nova_hyper_training_evaluator.py`

- [ ] **Step 1: Write failing promotion tests**

```python
# tests/test_nova_hyper_training_evaluator.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hyper_training_evaluator import decide_promotion


def metrics(joint, route, answer, repetition=0.01, protected=True, reload_ok=True):
    return {
        "joint": joint,
        "routing": {"macro_f1": route, "protected_domain_floor_delta": 0.0},
        "answers": {
            "composite": answer,
            "protected_perfect": protected,
            "malformed_rate": 0.0,
            "repetition_rate": repetition,
        },
        "stability": {"reload_ok": reload_ok, "confirmation_ok": True, "regressions": 0},
    }


def test_candidate_promotes_only_when_all_gates_pass():
    decision = decide_promotion(
        baseline=metrics(70.0, 70.0, 70.0),
        candidate=metrics(75.0, 76.0, 74.0),
        previous_winner=None,
    )
    assert decision.verdict == "PROMOTED"


def test_hash_change_cannot_override_answer_regression():
    decision = decide_promotion(
        baseline=metrics(80.0, 80.0, 80.0),
        candidate=metrics(83.0, 86.0, 79.0),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"
    assert any("answer" in reason.lower() for reason in decision.reasons)


def test_repetition_blocks_promotion():
    decision = decide_promotion(
        baseline=metrics(80.0, 80.0, 80.0),
        candidate=metrics(85.0, 86.0, 84.0, repetition=0.03),
        previous_winner=None,
    )
    assert decision.verdict == "REJECTED"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_hyper_training_evaluator.py -q
```

Expected: import failure for `nova_hyper_training_evaluator`.

- [ ] **Step 3: Implement scoring and promotion**

Use:

```python
joint = 0.50 * routing_score + 0.40 * answer_score + 0.10 * stability_score
reference_joint = max(
    baseline["joint"],
    previous_winner["joint"] if previous_winner else float("-inf"),
)
```

Reject unless every rule from the specification is satisfied:

- joint gain at least `2.0`, unless candidate is at least `95.0`;
- route macro F1 improves;
- answer composite improves;
- protected domain floor delta is at least `-1.0`;
- protected facts perfect;
- malformed rate does not increase;
- repetition does not increase and is below `0.02`;
- reload and confirmation succeed;
- regression count is zero.

- [ ] **Step 4: Add evaluator functions**

Implement `evaluate_routes(route_model, cases)`, `evaluate_answers(runtime, cases)`, `evaluate_stability(runtime, regression_result)`, `decide_promotion(baseline, candidate, previous_winner)`, and `run_negative_controls(project_root, cases)` with the metric keys used by the tests above.

Negative controls must verify that shuffled route labels, absent checkpoints, invalid checkpoint payloads, repetitive output, and a candidate with random weights are rejected.

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_hyper_training_evaluator.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/nova_hyper_training_evaluator.py tests/test_nova_hyper_training_evaluator.py
git commit -m "feat: enforce transformer promotion law"
```

---

### Task 10: Orchestrate training, reporting, and guarded promotion

**Files:**
- Create: `src/nova_hyper_training_orchestrator.py`
- Create: `scripts/run_transformer_hyper_training.py`
- Test: `tests/test_nova_hyper_training_orchestrator.py`
- Modify: `src/v055_assisted_learning_bridge.py:176-360`
- Modify: `nova_enhanced_server.py:54-91`
- Modify: `nova_enhanced_server.py:283-313`

- [ ] **Step 1: Write failing orchestrator rejection test**

```python
# tests/test_nova_hyper_training_orchestrator.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hyper_training_orchestrator import apply_decision
from nova_training_types import PromotionDecision
from nova_checkpoint_registry import CheckpointRegistry


def test_rejected_run_leaves_live_checkpoint_unchanged(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline.write_bytes(b"baseline")
    candidate.write_bytes(b"candidate")
    registry.register_baseline("memory_transformer", baseline, "basehash")
    registry.register_candidate("memory_transformer", candidate, "candidatehash", {"joint": 70.0})
    decision = PromotionDecision("REJECTED", ("answer regression",), 70.0, 69.0, None)
    apply_decision(registry, {"memory_transformer": "candidatehash"}, decision)
    assert registry.resolve_live("memory_transformer").sha256 == "basehash"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m pytest tests/test_nova_hyper_training_orchestrator.py -q
```

Expected: import failure for `nova_hyper_training_orchestrator`.

- [ ] **Step 3: Implement the orchestrator**

Expose `run_hyper_training(project_root, seed=20260622, route_epochs=80, role_epochs=30) -> dict` and `apply_decision(registry, candidate_hashes, decision) -> None`.

The run order is exactly:

1. preflight;
2. dataset build and fingerprint;
3. fresh baseline evaluation;
4. route candidate training;
5. seven role candidate trainings;
6. fresh-process reload check;
7. candidate evaluation;
8. negative controls;
9. promotion decision;
10. atomic registry update or rejection;
11. Markdown and JSON reports.

Reports are:

```text
reports/transformer_hyper_training_{run_id}.json
reports/transformer_hyper_training_{run_id}.md
```

The first Markdown line is `# PROMOTED`, `# REJECTED`, or `# BLOCKED`.

- [ ] **Step 4: Add the CLI**

```python
# scripts/run_transformer_hyper_training.py
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hyper_training_orchestrator import run_hyper_training

parser = argparse.ArgumentParser()
parser.add_argument("--seed", type=int, default=20260622)
parser.add_argument("--route-epochs", type=int, default=80)
parser.add_argument("--role-epochs", type=int, default=30)
args = parser.parse_args()
result = run_hyper_training(
    ROOT,
    seed=args.seed,
    route_epochs=args.route_epochs,
    role_epochs=args.role_epochs,
)
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["verdict"] in {"PROMOTED", "REJECTED"} else 2)
```

- [ ] **Step 5: Remove random-noise training from the assisted bridge**

Replace `run_finetune()` and delete `_run_numpy_finetune()` in `src/v055_assisted_learning_bridge.py`:

```python
def run_finetune(role=None):
    if role is not None:
        raise ValueError("Guarded hyper-training evaluates all roles jointly; role-only promotion is disabled")
    from nova_hyper_training_orchestrator import run_hyper_training
    return run_hyper_training(ROOT)
```

The bridge may continue to queue lessons, but queue size alone must not mutate live checkpoints.

- [ ] **Step 6: Replace server background training**

In `nova_enhanced_server.py`, replace direct `ConversationTrainer.train_role()` loops with one guarded background call:

```python
def _run_guarded_training():
    global _TRAINING_RUNNING
    try:
        from nova_hyper_training_orchestrator import run_hyper_training
        result = run_hyper_training(Path(ROOT))
        _TRAINING_LOG.append(
            f"[HYPERTRAIN] {result['verdict']} joint={result.get('candidate_joint')}"
        )
    except Exception as exc:
        _TRAINING_LOG.append(f"[HYPERTRAIN] BLOCKED {type(exc).__name__}: {exc}")
    finally:
        _TRAINING_RUNNING = False
```

“Deep learn” starts this function in one daemon thread and reports the run ID. It must not start a second run while one is active.

- [ ] **Step 7: Run and verify GREEN**

Run:

```powershell
py -3 -m pytest tests/test_nova_hyper_training_orchestrator.py -q
```

Expected: `1 passed`.

- [ ] **Step 8: Commit**

```powershell
git add src/nova_hyper_training_orchestrator.py scripts/run_transformer_hyper_training.py tests/test_nova_hyper_training_orchestrator.py src/v055_assisted_learning_bridge.py nova_enhanced_server.py
git commit -m "feat: orchestrate guarded hyper-training"
```

---

### Task 11: Prove transformer-only routing, reload, and live application wiring

**Files:**
- Create: `tests/test_nova_transformer_route_integration.py`
- Modify: `reports/HYBRID_ROUTER_TEST_REPORT.md`

- [ ] **Step 1: Write the transformer-only integration test**

```python
# tests/test_nova_transformer_route_integration.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_hybrid_router import route_and_respond


def test_transformer_only_prompts_produce_checkpoint_evidence():
    prompts = [
        "Debug this Python loop.",
        "Make an ordered release plan.",
        "Verify this claim using evidence.",
        "Design a calm blue pattern.",
        "Recall Nova's creator.",
        "Simulate a failed deployment.",
        "Explain routing clearly.",
    ]
    for prompt in prompts:
        response, trace = route_and_respond(prompt, transformer_only=True)
        assert response.strip()
        assert trace["source"] == "transformer"
        assert trace["route_model_hash"]
        assert trace["checkpoint_hash"]
        assert trace["generation"]["ok"] is True
        assert "fallback" not in trace.get("skills", [])
```

- [ ] **Step 2: Run before a promoted model and confirm the test cannot falsely pass**

Run:

```powershell
py -3 -m pytest tests/test_nova_transformer_route_integration.py -q
```

Expected before training: FAIL because no learned route winner has been promoted.

- [ ] **Step 3: Run the full hyper-training experiment**

Run:

```powershell
py -3 scripts/run_transformer_hyper_training.py --seed 20260622 --route-epochs 80 --role-epochs 30
```

Expected: a complete report with verdict `PROMOTED` or `REJECTED`. Do not change thresholds to force `PROMOTED`.

- [ ] **Step 4: If rejected, use report evidence for one targeted correction**

Permitted correction loop:

1. identify the single weakest failed gate from the report;
2. add or repair only the relevant clean training examples or implementation defect;
3. rerun the same sealed promotion bank and thresholds;
4. stop after three rejected candidates and report the architectural blocker rather than weakening gates.

- [ ] **Step 5: Verify a promoted run in a fresh process**

Run:

```powershell
py -3 -m pytest tests/test_nova_transformer_route_integration.py -q
py -3 -c "import sys; sys.path.insert(0, 'src'); from nova_training_preflight import run_preflight; from pathlib import Path; print(run_preflight(Path('.'))['verdict'])"
```

Expected: integration test passes and preflight prints `READY`.

- [ ] **Step 6: Run the complete regression suite**

Run:

```powershell
py -3 -m pytest tests -q
```

Expected: all tests pass, including existing dictionary, conversation-memory, and Windows launcher tests.

- [ ] **Step 7: Start the app and perform a smoke test**

Run in one terminal:

```powershell
py -3 nova_enhanced_server.py 3000
```

Then test:

```powershell
$body = @{ message = "Help me debug a Python loop" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:3000/api/chat -ContentType application/json -Body $body | ConvertTo-Json -Depth 8
```

Expected response trace has `source: "transformer"`, `roles: ["left_hemisphere"]`, and 64-character hexadecimal values for both `route_model_hash` and `checkpoint_hash`.

- [ ] **Step 8: Update the hybrid report with measured evidence**

Replace optimistic transformer claims in `reports/HYBRID_ROUTER_TEST_REPORT.md` with:

- historical results;
- fresh baseline;
- candidate and winner metrics;
- actual transformer-only pass count;
- route confusion matrix summary;
- checkpoint and route-model hashes;
- promotion verdict;
- remaining weaknesses.

- [ ] **Step 9: Commit**

```powershell
git add tests/test_nova_transformer_route_integration.py reports/HYBRID_ROUTER_TEST_REPORT.md
git commit -m "test: prove live transformer routing"
```

---

### Task 12: Final verification and evidence handoff

**Files:**
- Verify: newest file matching `reports/transformer_hyper_training_*.json`
- Verify: newest file matching `reports/transformer_hyper_training_*.md`
- Verify: `checkpoints/registry.json`

- [ ] **Step 1: Verify repository state**

Run:

```powershell
git status --short
git log --oneline -12
```

Expected: only expected runtime data or ignored checkpoint artifacts remain uncommitted.

- [ ] **Step 2: Verify the report is internally consistent**

Run:

```powershell
@'
import json
from pathlib import Path

reports = sorted(Path("reports").glob("transformer_hyper_training_*.json"))
assert reports, "No hyper-training report found"
data = json.loads(reports[-1].read_text(encoding="utf-8"))
assert data["verdict"] in {"PROMOTED", "REJECTED", "BLOCKED"}
assert data["baseline"]["joint"] >= 0
assert data["candidate"]["joint"] >= 0
assert data["negative_controls"]["passed"] is True
if data["verdict"] == "PROMOTED":
    assert data["candidate"]["joint"] >= data["baseline"]["joint"] + 2.0 or data["candidate"]["joint"] >= 95.0
print(reports[-1])
print(data["verdict"], data["baseline"]["joint"], data["candidate"]["joint"])
'@ | py -3 -
```

Expected: prints the report path and a consistent verdict.

- [ ] **Step 3: Verify the live registry matches the report**

Run:

```powershell
@'
import json
from pathlib import Path

registry = json.loads(Path("checkpoints/registry.json").read_text(encoding="utf-8"))
assert len(registry["roles"]) == 7
for role, entry in registry["roles"].items():
    assert entry["baseline"]["sha256"]
    if entry.get("winner"):
        assert Path(entry["winner"]["path"]).exists()
print("registry_roles=7")
'@ | py -3 -
```

Expected: `registry_roles=7`.

- [ ] **Step 4: Run final complete verification**

Run:

```powershell
py -3 -m pytest tests -q
py -3 -m nova_training_preflight
git diff --check
```

Expected: all tests pass, preflight is `READY`, and `git diff --check` exits zero.

- [ ] **Step 5: Commit any final report updates**

```powershell
git add reports/HYBRID_ROUTER_TEST_REPORT.md
git commit -m "docs: report transformer hyper-training evidence"
```
