# Nova Hybrid Game Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Nova recognize game creation requests, research and enhance each idea, wait for `GO`, build a saved playable browser game, test and repair it until it plays, expose an Open Game link, and provide an editable code-plus-preview sandbox with automatic checkpoints and fixes.

**Architecture:** Add a persistent game-builder state machine under `nova_runtime/game_builder`, then expose it through focused HTTP APIs and the unified Nova web shell. Generated projects live only in `sandbox/game_builder_projects`, use tested browser-game templates with telemetry, and pass static plus Playwright gameplay gates. The repair engine applies bounded deterministic patches first and restores the latest verified checkpoint when safe repair cannot progress.

**Tech Stack:** Python 3.11 standard library, vanilla HTML/CSS/JavaScript Canvas games, JSON/JSONL persistence, GitHub CLI or public REST search, MediaWiki API, `unittest`, Node.js syntax checks, Playwright browser tests.

**Prerequisite:** Execute `docs/superpowers/plans/2026-06-20-nova-unified-home-movement-lab.md` through Task 11 first so `nova_runtime`, confined static serving, `build_server()`, the unified tab shell, and the movement API coexist before Game Workshop routes are added.

---

## File Structure

### Runtime modules

- Create `nova_runtime/game_builder/__init__.py` — package marker.
- Create `nova_runtime/game_builder/models.py` — state, proposal, research source, project, test, repair, and checkpoint records.
- Create `nova_runtime/game_builder/intent.py` — distinguish capability, creation, `GO`, revision, project, and modification commands.
- Create `nova_runtime/game_builder/store.py` — atomic persistent state and project-session storage.
- Create `nova_runtime/game_builder/research.py` — provider interface plus MediaWiki, GitHub, official-doc, and local-knowledge providers.
- Create `nova_runtime/game_builder/enhancer.py` — turn idea and research into an actionable proposal.
- Create `nova_runtime/game_builder/generator.py` — create projects from verified templates.
- Create `nova_runtime/game_builder/project_files.py` — confined file listing, reads, saves, checkpoints, and restore.
- Create `nova_runtime/game_builder/static_checks.py` — required-file, JSON, path, and JavaScript syntax checks.
- Create `nova_runtime/game_builder/playtest.py` — invoke Playwright gameplay smoke tests and parse results.
- Create `nova_runtime/game_builder/repair.py` — classify failures and apply bounded deterministic repairs.
- Create `nova_runtime/game_builder/service.py` — orchestrate research, approval, build, test, repair, source, and modification flows.

### Templates

- Create `game_templates/runner/index.html.tpl`.
- Create `game_templates/runner/styles.css.tpl`.
- Create `game_templates/runner/game.js.tpl`.
- Create `game_templates/runner/game.config.json.tpl`.
- Create `game_templates/shared/test-harness.js`.

### Data and generated projects

- Create `data/game_builder/sessions/.gitkeep`.
- Create `data/game_builder/research_cache/.gitkeep`.
- Create `sandbox/game_builder_projects/.gitkeep`.

### Web UI

- Create `web/game-workshop.js`.
- Create `web/code-preview.js`.
- Modify `web/index.html`.
- Modify `web/styles.css`.
- Modify `web/app.js`.

### Existing files

- Modify `nova_web_server.py` — game-builder chat routing, APIs, project serving, and editor endpoints.
- Modify `.gitignore` — runtime game sessions, generated test output, and browser artifacts.
- Modify `README_LAPTOP_INSTALL.md` — browser-test dependency and Game Workshop usage.

### Tests

- Create `tests/test_game_intent.py`.
- Create `tests/test_game_store.py`.
- Create `tests/test_game_research.py`.
- Create `tests/test_game_enhancer.py`.
- Create `tests/test_game_generator.py`.
- Create `tests/test_game_project_files.py`.
- Create `tests/test_game_static_checks.py`.
- Create `tests/test_game_repair.py`.
- Create `tests/test_game_service.py`.
- Modify `tests/test_nova_server_api.py`.
- Create `tests/browser/generated_game.spec.mjs`.
- Create `tests/browser/game_workshop.spec.mjs`.

## Task 1: Game Intent Classification Before Memory Recall

**Files:**
- Create: `nova_runtime/game_builder/__init__.py`
- Create: `nova_runtime/game_builder/intent.py`
- Test: `tests/test_game_intent.py`

- [ ] **Step 1: Write failing intent tests**

```python
# tests/test_game_intent.py
import unittest

from nova_runtime.game_builder.intent import classify_game_message


class GameIntentTests(unittest.TestCase):
    def test_creation_request_is_not_capability_question(self):
        result = classify_game_message(
            "yes can u make me a block jumping game runner real quick"
        )
        self.assertEqual(result.kind, "create")

    def test_capability_question_does_not_start_build(self):
        result = classify_game_message("can you make games?")
        self.assertEqual(result.kind, "capability")

    def test_go_is_approval(self):
        result = classify_game_message("GO")
        self.assertEqual(result.kind, "approve")

    def test_major_modification_is_classified(self):
        result = classify_game_message("turn it into online multiplayer")
        self.assertEqual(result.kind, "modify_major")

    def test_small_modification_is_classified(self):
        result = classify_game_message("make the jump higher")
        self.assertEqual(result.kind, "modify_small")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_intent -v
```

Expected: import failure for `nova_runtime.game_builder.intent`.

- [ ] **Step 3: Implement an explicit classifier**

```python
# nova_runtime/game_builder/intent.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GameMessageKind = Literal[
    "none",
    "capability",
    "create",
    "approve",
    "revise",
    "cancel",
    "open",
    "show_code",
    "edit_code",
    "status",
    "modify_small",
    "modify_major",
]


@dataclass(frozen=True)
class GameMessageIntent:
    kind: GameMessageKind
    text: str


def classify_game_message(text: str) -> GameMessageIntent:
    q = " ".join(text.lower().split())
    if q == "go":
        return GameMessageIntent("approve", text)
    if q in {"cancel", "cancel game", "cancel build"}:
        return GameMessageIntent("cancel", text)
    if q in {"open game", "play game"}:
        return GameMessageIntent("open", text)
    if q in {"show code", "show all code"} or q.startswith("show code "):
        return GameMessageIntent("show_code", text)
    if q in {"edit code", "open editor"}:
        return GameMessageIntent("edit_code", text)
    if q in {"game status", "build status"}:
        return GameMessageIntent("status", text)

    game_words = ("game", "runner", "platformer", "puzzle", "arcade", "clicker")
    build_words = ("make", "build", "create", "turn this into")
    if q.endswith("?") and any(word in q for word in game_words) and not any(
        word in q for word in build_words
    ):
        return GameMessageIntent("capability", text)
    if any(word in q for word in game_words) and any(word in q for word in build_words):
        return GameMessageIntent("create", text)

    if any(
        phrase in q
        for phrase in (
            "multiplayer",
            "new level system",
            "different engine",
            "turn it into",
            "change the genre",
            "accounts",
        )
    ):
        return GameMessageIntent("modify_major", text)
    if any(
        phrase in q
        for phrase in (
            "jump higher",
            "faster",
            "slower",
            "change color",
            "more obstacles",
            "less obstacles",
            "sound off",
            "sound on",
        )
    ):
        return GameMessageIntent("modify_small", text)
    if q.startswith(("add ", "remove ", "change ")):
        return GameMessageIntent("revise", text)
    return GameMessageIntent("none", text)
```

Create an empty `nova_runtime/game_builder/__init__.py`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_intent -v
```

Expected: `Ran 5 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/game_builder/__init__.py nova_runtime/game_builder/intent.py tests/test_game_intent.py
git commit -m "feat: classify Nova game builder messages"
```

## Task 2: Persistent Game Session State and Approval Hash

**Files:**
- Create: `nova_runtime/game_builder/models.py`
- Create: `nova_runtime/game_builder/store.py`
- Create: `data/game_builder/sessions/.gitkeep`
- Test: `tests/test_game_store.py`

- [ ] **Step 1: Write failing state tests**

```python
# tests/test_game_store.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.game_builder.models import GameProposal
from nova_runtime.game_builder.store import GameSessionStore


class GameStoreTests(unittest.TestCase):
    def test_proposal_hash_changes_when_plan_changes(self):
        first = GameProposal.from_idea("block jumping runner", ["jump"])
        second = GameProposal.from_idea("block jumping runner", ["jump", "dash"])
        self.assertNotEqual(first.proposal_hash, second.proposal_hash)

    def test_store_round_trip_preserves_waiting_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GameSessionStore(Path(tmp))
            proposal = GameProposal.from_idea("runner", ["jump"])
            store.save(
                {
                    "state": "WAITING_FOR_GO",
                    "proposal": proposal.to_dict(),
                    "active_project": None,
                }
            )
            loaded = store.load()
            self.assertEqual(loaded["state"], "WAITING_FOR_GO")
            self.assertEqual(
                loaded["proposal"]["proposal_hash"], proposal.proposal_hash
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_store -v
```

Expected: import failure for models or store.

- [ ] **Step 3: Implement proposal and research models**

```python
# nova_runtime/game_builder/models.py
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchSource:
    title: str
    url: str
    provider: str
    summary: str
    design_signal: str
    retrieved_at: str


@dataclass(frozen=True)
class GameProposal:
    idea: str
    title: str
    genre: str
    core_loop: str
    controls: tuple[str, ...]
    features: tuple[str, ...]
    visual_direction: str
    accessibility: tuple[str, ...]
    optional_features: tuple[str, ...] = field(default_factory=tuple)
    sources: tuple[ResearchSource, ...] = field(default_factory=tuple)
    proposal_hash: str = ""

    @classmethod
    def from_idea(cls, idea: str, features: list[str]) -> "GameProposal":
        payload = {"idea": idea, "features": features}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return cls(
            idea=idea,
            title="Nova Runner",
            genre="endless_runner",
            core_loop="Run, jump obstacles, score, lose, and restart.",
            controls=("Space / Up / Tap to jump",),
            features=tuple(features),
            visual_direction="Original geometric neon world",
            accessibility=("keyboard", "touch", "reduced motion"),
            proposal_hash=digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Implement atomic session storage**

```python
# nova_runtime/game_builder/store.py
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any


class GameSessionStore:
    def __init__(self, root: Path, session_id: str = "default") -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f"{session_id}.json"
        self._lock = RLock()

    def save(self, payload: dict[str, Any]) -> None:
        with self._lock:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=self.root,
                suffix=".tmp",
            ) as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                temp = Path(handle.name)
            os.replace(temp, self.path)

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {
                    "state": "IDLE",
                    "proposal": None,
                    "active_project": None,
                }
            return json.loads(self.path.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_store -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 6: Commit**

```powershell
git add nova_runtime/game_builder/models.py nova_runtime/game_builder/store.py data/game_builder/sessions/.gitkeep tests/test_game_store.py
git commit -m "feat: persist Nova game build sessions"
```

## Task 3: Read-Only Internet Research Providers

**Files:**
- Create: `nova_runtime/game_builder/research.py`
- Create: `data/game_builder/research_cache/.gitkeep`
- Test: `tests/test_game_research.py`

- [ ] **Step 1: Write provider tests with local HTTP fixtures**

```python
# tests/test_game_research.py
import unittest
from unittest.mock import patch

from nova_runtime.game_builder.research import (
    LocalKnowledgeProvider,
    MediaWikiProvider,
    ResearchService,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class GameResearchTests(unittest.TestCase):
    @patch("nova_runtime.game_builder.research.urlopen")
    def test_mediawiki_returns_attributed_result(self, mocked):
        mocked.return_value = FakeResponse(
            b'["endless runner",["Platform game"],["A game genre"],["https://example.test"]]'
        )
        results = MediaWikiProvider().search("endless runner")
        self.assertEqual(results[0].provider, "mediawiki")
        self.assertEqual(results[0].url, "https://example.test")

    def test_service_survives_provider_failure(self):
        class BrokenProvider:
            def search(self, query):
                raise OSError("offline")

        service = ResearchService([BrokenProvider(), LocalKnowledgeProvider()])
        report = service.research("block jumping runner")
        self.assertTrue(report["sources"])
        self.assertIn("BrokenProvider", report["provider_errors"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_research -v
```

Expected: import failure for research providers.

- [ ] **Step 3: Implement MediaWiki and local providers**

```python
# nova_runtime/game_builder/research.py
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nova_runtime.game_builder.models import ResearchSource


class ResearchProvider(Protocol):
    def search(self, query: str) -> list[ResearchSource]: ...


class MediaWikiProvider:
    def search(self, query: str) -> list[ResearchSource]:
        params = urlencode(
            {
                "action": "opensearch",
                "search": query,
                "limit": 3,
                "namespace": 0,
                "format": "json",
            }
        )
        request = Request(
            f"https://en.wikipedia.org/w/api.php?{params}",
            headers={"User-Agent": "NovaCreature/1.0"},
        )
        with urlopen(request, timeout=8) as response:
            _, titles, descriptions, urls = json.loads(response.read())
        return [
            ResearchSource(
                title=title,
                url=url,
                provider="mediawiki",
                summary=description,
                design_signal=f"Use genre context from {title}; do not copy identity.",
                retrieved_at=datetime.now().isoformat(),
            )
            for title, description, url in zip(titles, descriptions, urls)
        ]


class LocalKnowledgeProvider:
    def search(self, query: str) -> list[ResearchSource]:
        return [
            ResearchSource(
                title="Nova browser-game design knowledge",
                url="local://game-builder",
                provider="local",
                summary="Use a short polished loop, keyboard and touch controls, clear restart, and deterministic telemetry.",
                design_signal="Prefer a reliable Canvas MVP with original shapes.",
                retrieved_at=datetime.now().isoformat(),
            )
        ]
```

- [ ] **Step 4: Add GitHub and official-document providers**

Add these classes to `nova_runtime/game_builder/research.py`:

```python
class GitHubProvider:
    def _convert(self, item: dict[str, object]) -> ResearchSource:
        name = str(item.get("fullName") or item.get("full_name") or "GitHub project")
        description = str(item.get("description") or "No description supplied.")
        return ResearchSource(
            title=name,
            url=str(item["url"] if "url" in item else item["html_url"]),
            provider="github",
            summary=description,
            design_signal=(
                "Use only high-level mechanics and technical patterns from metadata; "
                "do not copy code, art, names, or level layouts."
            ),
            retrieved_at=datetime.now().isoformat(),
        )

    def search(self, query: str) -> list[ResearchSource]:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "search",
                    "repos",
                    query,
                    "--limit",
                    "5",
                    "--json",
                    "fullName,description,url,updatedAt",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            return [self._convert(item) for item in json.loads(result.stdout)]
        except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
            params = urlencode({"q": query, "per_page": 5})
            request = Request(
                f"https://api.github.com/search/repositories?{params}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "NovaCreature-GameResearch/1.0",
                },
            )
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read())
            return [self._convert(item) for item in payload.get("items", [])]


class OfficialDocsProvider:
    DOCS = (
        (
            "MDN Canvas API",
            "https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API",
            "Canvas provides browser-native 2D graphics.",
            "Use Canvas for a dependency-light playable first build.",
        ),
        (
            "MDN requestAnimationFrame",
            "https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame",
            "requestAnimationFrame synchronizes rendering with browser repaint.",
            "Use frame timestamps so movement remains stable across refresh rates.",
        ),
        (
            "MDN Pointer Events",
            "https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events",
            "Pointer events unify mouse, pen, and touch input.",
            "Expose keyboard and touch controls from one input layer.",
        ),
        (
            "itch.io HTML5",
            "https://itch.io/docs/creators/html5",
            "HTML5 games can be packaged as browser-playable projects.",
            "Keep file paths relative and the entry point at index.html.",
        ),
    )

    def search(self, query: str) -> list[ResearchSource]:
        now = datetime.now().isoformat()
        return [
            ResearchSource(
                title=title,
                url=url,
                provider="official",
                summary=summary,
                design_signal=signal,
                retrieved_at=now,
            )
            for title, url, summary, signal in self.DOCS
        ]
```

These providers only read metadata or documentation. They never clone repositories, download executable assets, or run remote code.

- [ ] **Step 5: Implement provider isolation**

```python
class ResearchService:
    def __init__(self, providers: list[ResearchProvider]) -> None:
        self.providers = providers

    def research(self, query: str) -> dict[str, object]:
        sources: list[ResearchSource] = []
        errors: dict[str, str] = {}
        for provider in self.providers:
            try:
                sources.extend(provider.search(query))
            except Exception as error:
                errors[type(provider).__name__] = str(error)
        return {
            "query": query,
            "sources": [source.__dict__ for source in sources],
            "provider_errors": errors,
            "coverage": "full" if len(sources) >= 4 else "reduced",
        }
```

- [ ] **Step 6: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_research -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 7: Commit**

```powershell
git add nova_runtime/game_builder/research.py data/game_builder/research_cache/.gitkeep tests/test_game_research.py
git commit -m "feat: research game ideas from public sources"
```

## Task 4: Concept Enhancer and `WAITING_FOR_GO`

**Files:**
- Create: `nova_runtime/game_builder/enhancer.py`
- Test: `tests/test_game_enhancer.py`

- [ ] **Step 1: Write failing proposal tests**

```python
# tests/test_game_enhancer.py
import unittest

from nova_runtime.game_builder.enhancer import enhance_game_idea


class GameEnhancerTests(unittest.TestCase):
    def test_runner_proposal_includes_required_sections(self):
        proposal = enhance_game_idea(
            "block jumping runner",
            {
                "coverage": "full",
                "sources": [
                    {
                        "title": "Canvas",
                        "url": "https://example.test/canvas",
                        "provider": "official",
                        "summary": "Canvas graphics",
                        "design_signal": "Use Canvas",
                        "retrieved_at": "2026-06-20T00:00:00",
                    }
                ],
            },
        )
        self.assertEqual(proposal.genre, "endless_runner")
        self.assertIn("restart", proposal.features)
        self.assertTrue(proposal.sources)
        self.assertTrue(proposal.proposal_hash)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_enhancer -v
```

Expected: import failure for enhancer.

- [ ] **Step 3: Implement a deterministic first-release enhancer**

```python
# nova_runtime/game_builder/enhancer.py
from __future__ import annotations

import hashlib
import json

from nova_runtime.game_builder.models import GameProposal, ResearchSource


def enhance_game_idea(
    idea: str, research: dict[str, object]
) -> GameProposal:
    q = idea.lower()
    genre = "endless_runner" if any(
        word in q for word in ("runner", "jump", "platform")
    ) else "top_down_dodger"
    title = "Blockbound Runner" if genre == "endless_runner" else "Nova Arena"
    features = (
        "jump",
        "progressive speed",
        "score",
        "game over",
        "restart",
        "keyboard controls",
        "touch controls",
        "reduced motion option",
        "deterministic test mode",
    )
    source_items = tuple(
        ResearchSource(**item) for item in research.get("sources", [])
    )
    payload = {
        "idea": idea,
        "genre": genre,
        "features": features,
        "sources": [source.url for source in source_items],
    }
    proposal_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return GameProposal(
        idea=idea,
        title=title,
        genre=genre,
        core_loop="Survive by timing jumps, build score, lose on collision, restart instantly.",
        controls=("Space / Up / Tap to jump", "R to restart"),
        features=features,
        visual_direction="Original geometric neon blocks with high contrast",
        accessibility=("keyboard", "touch", "reduced motion", "high contrast"),
        optional_features=("dash", "collectibles", "multiple biomes"),
        sources=source_items,
        proposal_hash=proposal_hash,
    )
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_enhancer -v
```

Expected: `Ran 1 test ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/game_builder/enhancer.py tests/test_game_enhancer.py
git commit -m "feat: enhance researched game ideas"
```

## Task 5: Verified Runner Template and Project Generator

**Files:**
- Create: `game_templates/runner/index.html.tpl`
- Create: `game_templates/runner/styles.css.tpl`
- Create: `game_templates/runner/game.js.tpl`
- Create: `game_templates/runner/game.config.json.tpl`
- Create: `game_templates/shared/test-harness.js`
- Create: `nova_runtime/game_builder/generator.py`
- Create: `sandbox/game_builder_projects/.gitkeep`
- Test: `tests/test_game_generator.py`

- [ ] **Step 1: Write failing generator tests**

```python
# tests/test_game_generator.py
import json
import tempfile
import unittest
from pathlib import Path

from nova_runtime.game_builder.enhancer import enhance_game_idea
from nova_runtime.game_builder.generator import generate_project


class GameGeneratorTests(unittest.TestCase):
    def test_generates_required_runner_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposal = enhance_game_idea(
                "block jumping runner", {"sources": [], "coverage": "reduced"}
            )
            project = generate_project(proposal, Path(tmp))
            for name in (
                "index.html",
                "styles.css",
                "game.js",
                "game.config.json",
                "manifest.json",
                "plan.json",
                "research.json",
                "test-report.json",
                "repair-log.jsonl",
            ):
                self.assertTrue((project / name).exists(), name)
            config = json.loads((project / "game.config.json").read_text())
            self.assertGreater(config["jumpPower"], 0)

    def test_project_slug_stays_inside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposal = enhance_game_idea(
                "../../escape", {"sources": [], "coverage": "reduced"}
            )
            project = generate_project(proposal, Path(tmp))
            self.assertIn(Path(tmp).resolve(), project.resolve().parents)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_generator -v
```

Expected: import failure for generator.

- [ ] **Step 3: Create the game HTML and configuration templates**

`index.html.tpl` must include:

```html
<canvas id="game" width="960" height="540" aria-label="__TITLE__"></canvas>
<div id="touch-controls">
  <button id="jump-button">Jump</button>
</div>
<script src="test-harness.js"></script>
<script src="game.js"></script>
```

`game.config.json.tpl`:

```json
{
  "title": "__TITLE__",
  "gravity": 0.8,
  "jumpPower": 14,
  "baseSpeed": 6,
  "maxSpeed": 15,
  "obstacleMinGap": 320,
  "obstacleMaxGap": 560,
  "reducedMotion": false
}
```

`styles.css.tpl`:

```css
* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: #08111f; color: #fff; }
body {
  display: grid;
  place-items: center;
  font-family: system-ui, sans-serif;
  padding: 16px;
}
#game {
  width: min(100%, 960px);
  height: auto;
  border: 2px solid #5aa9e6;
  border-radius: 16px;
  box-shadow: 0 0 36px #2d8fd955;
  touch-action: none;
}
#touch-controls { margin-top: 12px; text-align: center; }
#jump-button {
  min-width: 140px;
  min-height: 52px;
  border: 0;
  border-radius: 14px;
  background: #1976d2;
  color: #fff;
  font: 700 18px system-ui;
}
@media (pointer: fine) {
  #touch-controls { display: none; }
}
```

`game_templates/shared/test-harness.js`:

```javascript
window.addEventListener("error", (event) => {
  document.documentElement.dataset.runtimeError = event.message;
});
window.addEventListener("unhandledrejection", (event) => {
  document.documentElement.dataset.runtimeError = String(event.reason);
});
```

- [ ] **Step 4: Implement gameplay with telemetry**

```javascript
// game_templates/runner/game.js.tpl
const canvas = document.querySelector("#game");
const context = canvas.getContext("2d");
const jumpButton = document.querySelector("#jump-button");
const groundY = 450;

let config;
let lastTime = 0;
let spawnDistance = 360;

const state = {
  mode: "loading",
  score: 0,
  restartCount: 0,
  player: {
    x: 150,
    y: groundY - 54,
    width: 42,
    height: 54,
    velocityY: 0,
    onGround: true,
  },
  obstacles: [],
};

function requestJump() {
  if (state.mode !== "playing" || !state.player.onGround) return;
  state.player.velocityY = -config.jumpPower;
  state.player.onGround = false;
}

function restartGame() {
  state.mode = "playing";
  state.score = 0;
  state.restartCount += 1;
  state.player.y = groundY - state.player.height;
  state.player.velocityY = 0;
  state.player.onGround = true;
  state.obstacles = [];
  spawnDistance = 360;
}

function spawnObstacle() {
  state.obstacles.push({
    x: canvas.width + 20,
    y: groundY - 48,
    width: 44,
    height: 48,
  });
  const range = config.obstacleMaxGap - config.obstacleMinGap;
  spawnDistance = config.obstacleMinGap + Math.random() * range;
}

function intersects(a, b) {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

function update(deltaSeconds) {
  if (state.mode !== "playing") return;
  const player = state.player;
  player.velocityY += config.gravity * 60 * deltaSeconds;
  player.y += player.velocityY * 60 * deltaSeconds;
  const floor = groundY - player.height;
  if (player.y >= floor) {
    player.y = floor;
    player.velocityY = 0;
    player.onGround = true;
  }

  const speed = Math.min(
    config.maxSpeed,
    config.baseSpeed + state.score / 500,
  );
  spawnDistance -= speed * 60 * deltaSeconds;
  if (spawnDistance <= 0) spawnObstacle();

  for (const obstacle of state.obstacles) {
    obstacle.x -= speed * 60 * deltaSeconds;
    if (intersects(player, obstacle)) state.mode = "gameover";
  }
  state.obstacles = state.obstacles.filter(
    (obstacle) => obstacle.x + obstacle.width > -20,
  );
  state.score += Math.round(60 * deltaSeconds);
}

function render() {
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#11213d";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#264a2d";
  context.fillRect(0, groundY, canvas.width, canvas.height - groundY);
  context.fillStyle = "#f6c85f";
  context.fillRect(
    state.player.x,
    state.player.y,
    state.player.width,
    state.player.height,
  );
  context.fillStyle = "#db4f63";
  for (const obstacle of state.obstacles) {
    context.fillRect(obstacle.x, obstacle.y, obstacle.width, obstacle.height);
  }
  context.fillStyle = "#ffffff";
  context.font = "700 26px system-ui";
  context.fillText(`SCORE ${state.score}`, 24, 42);
  if (state.mode === "gameover") {
    context.fillText("GAME OVER — PRESS R", 320, 220);
  }
}

function frame(time) {
  const deltaSeconds = Math.min((time - lastTime) / 1000 || 0, 0.05);
  lastTime = time;
  update(deltaSeconds);
  render();
  requestAnimationFrame(frame);
}

function handleKey(event) {
  if (event.code === "Space" || event.code === "ArrowUp") {
    event.preventDefault();
    requestJump();
  }
  if (event.code === "KeyR") restartGame();
}

async function start() {
  config = await fetch("game.config.json").then((response) => response.json());
  state.mode = "playing";
  window.addEventListener("keydown", handleKey);
  jumpButton.addEventListener("pointerdown", requestJump);
  requestAnimationFrame(frame);

  if (new URLSearchParams(location.search).get("test") === "1") {
    window.__NOVA_GAME_TEST__ = {
      snapshot: () => structuredClone(state),
      jump: () => requestJump(),
      forceCollision: () => {
        state.obstacles.push({
          x: state.player.x,
          y: state.player.y,
          width: 44,
          height: 48,
        });
      },
      restart: () => restartGame(),
    };
  }
}

start().catch((error) => {
  state.mode = "error";
  console.error(error);
});
```

- [ ] **Step 5: Implement confined generator**

```python
# nova_runtime/game_builder/generator.py
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from nova_runtime.game_builder.models import GameProposal

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "game_templates"


def safe_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48] or "nova-game"


def generate_project(proposal: GameProposal, projects_root: Path) -> Path:
    projects_root = projects_root.resolve()
    project = (projects_root / safe_slug(proposal.title)).resolve()
    if projects_root not in project.parents:
        raise ValueError("Project path escapes game root")
    project.mkdir(parents=True, exist_ok=True)

    template_root = TEMPLATES / "runner"
    replacements = {"__TITLE__": proposal.title}
    for source_name, target_name in (
        ("index.html.tpl", "index.html"),
        ("styles.css.tpl", "styles.css"),
        ("game.js.tpl", "game.js"),
        ("game.config.json.tpl", "game.config.json"),
    ):
        text = (template_root / source_name).read_text(encoding="utf-8")
        for before, after in replacements.items():
            text = text.replace(before, after)
        (project / target_name).write_text(text, encoding="utf-8")

    (project / "test-harness.js").write_text(
        (TEMPLATES / "shared" / "test-harness.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (project / "manifest.json").write_text(
        json.dumps(
            {
                "project_slug": project.name,
                "proposal_hash": proposal.proposal_hash,
                "template": "runner-v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (project / "plan.json").write_text(
        json.dumps(asdict(proposal), indent=2), encoding="utf-8"
    )
    (project / "research.json").write_text(
        json.dumps([asdict(source) for source in proposal.sources], indent=2),
        encoding="utf-8",
    )
    (project / "test-report.json").write_text("{}\n", encoding="utf-8")
    (project / "repair-log.jsonl").touch()
    return project
```

- [ ] **Step 6: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_generator -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 7: Commit**

```powershell
git add game_templates nova_runtime/game_builder/generator.py sandbox/game_builder_projects/.gitkeep tests/test_game_generator.py
git commit -m "feat: generate playable Nova runner projects"
```

## Task 6: Static Validation

**Files:**
- Create: `nova_runtime/game_builder/static_checks.py`
- Test: `tests/test_game_static_checks.py`

- [ ] **Step 1: Write failing validation tests**

```python
# tests/test_game_static_checks.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.game_builder.static_checks import run_static_checks


class GameStaticCheckTests(unittest.TestCase):
    def test_missing_game_js_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "index.html").write_text("<canvas></canvas>")
            result = run_static_checks(project)
            self.assertFalse(result["passed"])
            self.assertIn("game.js", result["failures"][0])

    def test_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            for name in ("index.html", "styles.css", "game.js"):
                (project / name).write_text("")
            (project / "game.config.json").write_text("{bad")
            result = run_static_checks(project)
            self.assertFalse(result["passed"])
            self.assertTrue(any(item["category"] == "json" for item in result["details"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_static_checks -v
```

Expected: import failure for static checks.

- [ ] **Step 3: Implement required, JSON, and JavaScript checks**

```python
# nova_runtime/game_builder/static_checks.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REQUIRED = (
    "index.html",
    "styles.css",
    "game.js",
    "game.config.json",
    "test-harness.js",
)


def run_static_checks(project: Path) -> dict[str, object]:
    details: list[dict[str, object]] = []
    failures: list[str] = []
    for name in REQUIRED:
        exists = (project / name).is_file()
        details.append({"category": "required", "file": name, "passed": exists})
        if not exists:
            failures.append(f"Missing required file: {name}")

    config = project / "game.config.json"
    if config.exists():
        try:
            values = json.loads(config.read_text(encoding="utf-8"))
            details.append({"category": "json", "file": config.name, "passed": True})
            gap_ok = (
                int(values["obstacleMinGap"]) >= 240
                and int(values["obstacleMaxGap"])
                >= int(values["obstacleMinGap"]) + 80
            )
            details.append(
                {
                    "category": "config_range",
                    "file": config.name,
                    "passed": gap_ok,
                }
            )
            if not gap_ok:
                failures.append("Obstacle gap is outside verified range")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            failures.append(f"Invalid JSON: {error}")
            details.append({"category": "json", "file": config.name, "passed": False})

    script = project / "game.js"
    if script.exists():
        result = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        passed = result.returncode == 0
        details.append(
            {
                "category": "javascript",
                "file": script.name,
                "passed": passed,
                "stderr": result.stderr,
            }
        )
        if not passed:
            failures.append(result.stderr.strip())

    return {"passed": not failures, "failures": failures, "details": details}
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_static_checks -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/game_builder/static_checks.py tests/test_game_static_checks.py
git commit -m "feat: validate generated game projects"
```

## Task 7: Project Files, Checkpoints, Undo, and Restore

**Files:**
- Create: `nova_runtime/game_builder/project_files.py`
- Test: `tests/test_game_project_files.py`

- [ ] **Step 1: Write failing checkpoint tests**

```python
# tests/test_game_project_files.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.game_builder.project_files import ProjectFiles


class ProjectFileTests(unittest.TestCase):
    def test_save_creates_checkpoint_before_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "game.js").write_text("const speed = 1;", encoding="utf-8")
            files = ProjectFiles(project)
            checkpoint = files.save("game.js", "const speed = 2;")
            self.assertEqual(
                (checkpoint / "game.js").read_text(encoding="utf-8"),
                "const speed = 1;",
            )
            self.assertEqual(
                (project / "game.js").read_text(encoding="utf-8"),
                "const speed = 2;",
            )

    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = ProjectFiles(Path(tmp))
            with self.assertRaises(ValueError):
                files.read("../secret.txt")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_project_files -v
```

Expected: import failure for project files.

- [ ] **Step 3: Implement confined file operations**

```python
# nova_runtime/game_builder/project_files.py
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ALLOWED_SUFFIXES = {".html", ".css", ".js", ".json", ".md"}


class ProjectFiles:
    def __init__(self, project: Path) -> None:
        self.project = project.resolve()
        self.checkpoints = self.project / "checkpoints"
        self.checkpoints.mkdir(exist_ok=True)

    def _resolve(self, relative: str) -> Path:
        target = (self.project / relative).resolve()
        if self.project not in target.parents:
            raise ValueError("Path escapes project")
        if target.suffix not in ALLOWED_SUFFIXES:
            raise ValueError("File type is not editable")
        return target

    def read(self, relative: str) -> str:
        return self._resolve(relative).read_text(encoding="utf-8")

    def list(self) -> list[str]:
        return sorted(
            str(path.relative_to(self.project)).replace("\\", "/")
            for path in self.project.rglob("*")
            if path.is_file()
            and "checkpoints" not in path.parts
            and path.suffix in ALLOWED_SUFFIXES
        )

    def checkpoint(self, label: str) -> Path:
        target = self.checkpoints / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{label}"
        target.mkdir(parents=True)
        for path in self.project.iterdir():
            if path.name == "checkpoints":
                continue
            if path.is_file():
                shutil.copy2(path, target / path.name)
        return target

    def save(self, relative: str, content: str) -> Path:
        checkpoint = self.checkpoint("manual-save")
        self._resolve(relative).write_text(content, encoding="utf-8")
        return checkpoint

    def restore(self, checkpoint: Path) -> None:
        for path in checkpoint.iterdir():
            if path.is_file():
                shutil.copy2(path, self.project / path.name)
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_project_files -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/game_builder/project_files.py tests/test_game_project_files.py
git commit -m "feat: checkpoint editable game files"
```

## Task 8: Real Browser Playtest Contract

**Files:**
- Create: `nova_runtime/game_builder/playtest.py`
- Create: `tests/browser/generated_game.spec.mjs`
- Modify: `package.json`

- [ ] **Step 1: Write the browser gameplay test**

```javascript
// tests/browser/generated_game.spec.mjs
import { test, expect } from "@playwright/test";

const project = process.env.NOVA_GAME_PROJECT ?? "blockbound-runner";

test("generated runner loads, jumps, loses, scores, and restarts", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`http://127.0.0.1:3000/games/${project}/?test=1`);

  const canvas = page.locator("#game");
  await expect(canvas).toBeVisible();

  const before = await page.evaluate(() => window.__NOVA_GAME_TEST__.snapshot());
  await page.evaluate(() => window.__NOVA_GAME_TEST__.jump());
  await page.waitForTimeout(120);
  const duringJump = await page.evaluate(() => window.__NOVA_GAME_TEST__.snapshot());
  expect(duringJump.player.y).toBeLessThan(before.player.y);

  await page.waitForFunction(() => window.__NOVA_GAME_TEST__.snapshot().score > 0);
  await page.evaluate(() => window.__NOVA_GAME_TEST__.forceCollision());
  await page.waitForFunction(() => window.__NOVA_GAME_TEST__.snapshot().mode === "gameover");

  await page.evaluate(() => window.__NOVA_GAME_TEST__.restart());
  const restarted = await page.evaluate(() => window.__NOVA_GAME_TEST__.snapshot());
  expect(restarted.mode).toBe("playing");
  expect(restarted.restartCount).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});
```

- [ ] **Step 2: Add the Playwright script**

Extend `package.json`:

```json
{
  "scripts": {
    "test:browser": "playwright test tests/browser",
    "test:generated-game": "playwright test tests/browser/generated_game.spec.mjs"
  }
}
```

- [ ] **Step 3: Implement the Python playtest runner**

```python
# nova_runtime/game_builder/playtest.py
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def run_playtest(project: Path, repo_root: Path) -> dict[str, object]:
    environment = os.environ.copy()
    environment["NOVA_GAME_PROJECT"] = project.name
    result = subprocess.run(
        ["npm.cmd", "run", "test:generated-game", "--", "--reporter=json"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        report = {"raw_stdout": result.stdout}
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "report": report,
        "stderr": result.stderr,
    }
```

- [ ] **Step 4: Run the test against a generated project**

Start Nova:

```powershell
py -3 nova_web_server.py 3000
```

In another terminal:

```powershell
$env:NOVA_GAME_PROJECT='blockbound-runner'
npm.cmd run test:generated-game
```

Expected: the generated runner test passes.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/game_builder/playtest.py tests/browser/generated_game.spec.mjs package.json package-lock.json
git commit -m "test: play generated Nova games in Chromium"
```

## Task 9: Failure Classification and Deterministic Repair

**Files:**
- Create: `nova_runtime/game_builder/repair.py`
- Test: `tests/test_game_repair.py`

- [ ] **Step 1: Write failing repair tests**

```python
# tests/test_game_repair.py
import tempfile
import unittest
from pathlib import Path

from nova_runtime.game_builder.repair import RepairEngine


class GameRepairTests(unittest.TestCase):
    def test_repairs_invalid_jump_power(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "game.config.json").write_text(
                '{"jumpPower": 0, "gravity": 0.8}',
                encoding="utf-8",
            )
            repair = RepairEngine(project).repair(
                {
                    "category": "gameplay",
                    "message": "jump did not move player upward",
                }
            )
            self.assertTrue(repair["applied"])
            self.assertIn('"jumpPower": 14', (project / "game.config.json").read_text())

    def test_unknown_failure_does_not_rewrite_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "game.js").write_text("original", encoding="utf-8")
            repair = RepairEngine(project).repair(
                {"category": "unknown", "message": "unclassified"}
            )
            self.assertFalse(repair["applied"])
            self.assertEqual((project / "game.js").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_repair -v
```

Expected: import failure for repair engine.

- [ ] **Step 3: Implement bounded repairs**

```python
# nova_runtime/game_builder/repair.py
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


class RepairEngine:
    TEMPLATE_FILES = {
        "index.html": ("runner", "index.html.tpl"),
        "styles.css": ("runner", "styles.css.tpl"),
        "game.js": ("runner", "game.js.tpl"),
        "game.config.json": ("runner", "game.config.json.tpl"),
        "test-harness.js": ("shared", "test-harness.js"),
    }

    def __init__(self, project: Path, templates_root: Path | None = None) -> None:
        self.project = project
        self.log = project / "repair-log.jsonl"
        self.templates_root = templates_root

    def _restore_template_file(self, name: str) -> bool:
        if self.templates_root is None or name not in self.TEMPLATE_FILES:
            return False
        folder, template_name = self.TEMPLATE_FILES[name]
        source = self.templates_root / folder / template_name
        if not source.exists():
            return False
        text = source.read_text(encoding="utf-8")
        title = "Nova Game"
        config_path = self.project / "game.config.json"
        if config_path.exists():
            try:
                title = json.loads(config_path.read_text(encoding="utf-8")).get(
                    "title", title
                )
            except json.JSONDecodeError:
                pass
        (self.project / name).write_text(
            text.replace("__TITLE__", title),
            encoding="utf-8",
        )
        return True

    def _restore_checkpoint(self, checkpoint: str | None) -> list[str]:
        if not checkpoint:
            return []
        source = Path(checkpoint)
        if not source.is_dir():
            return []
        changed: list[str] = []
        for path in source.iterdir():
            if path.is_file():
                shutil.copy2(path, self.project / path.name)
                changed.append(path.name)
        return changed

    def repair(self, failure: dict[str, object]) -> dict[str, object]:
        changed: list[str] = []
        action = "none"
        category = str(failure.get("category", "unknown"))
        message = str(failure.get("message", "")).lower()

        if category == "gameplay" and "jump" in message:
            config_path = self.project / "game.config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if config.get("jumpPower", 0) <= 0:
                config["jumpPower"] = 14
                config_path.write_text(
                    json.dumps(config, indent=2) + "\n",
                    encoding="utf-8",
                )
                changed.append("game.config.json")
                action = "restore_positive_jump_power"

        elif category == "missing_file":
            name = str(failure.get("file", ""))
            if self._restore_template_file(name):
                changed.append(name)
                action = "restore_generated_file"

        elif category == "telemetry":
            if self._restore_template_file("test-harness.js"):
                changed.append("test-harness.js")
                action = "restore_test_harness"

        elif category == "config_range":
            config_path = self.project / "game.config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["obstacleMinGap"] = max(240, int(config["obstacleMinGap"]))
            config["obstacleMaxGap"] = max(
                config["obstacleMinGap"] + 80,
                int(config["obstacleMaxGap"]),
            )
            config_path.write_text(
                json.dumps(config, indent=2) + "\n",
                encoding="utf-8",
            )
            changed.append("game.config.json")
            action = "clamp_obstacle_gap"

        elif category in {"json", "javascript", "restart"}:
            changed = self._restore_checkpoint(
                str(failure.get("checkpoint") or "") or None
            )
            if changed:
                action = "restore_verified_checkpoint"

        record = {
            "created_at": datetime.now().isoformat(),
            "failure": failure,
            "action": action,
            "changed_files": changed,
            "applied": bool(changed),
        }
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return record
```

The repair engine has no generic source-rewriting branch. Unknown failures return `applied: false`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_repair -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit**

```powershell
git add nova_runtime/game_builder/repair.py tests/test_game_repair.py
git commit -m "feat: repair bounded generated game failures"
```

## Task 10: Game Builder Orchestrator and Play-Until-Passing Loop

**Files:**
- Create: `nova_runtime/game_builder/service.py`
- Test: `tests/test_game_service.py`

- [ ] **Step 1: Write failing state-machine tests**

```python
# tests/test_game_service.py
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nova_runtime.game_builder.service import GameBuilderService


class GameBuilderServiceTests(unittest.TestCase):
    def build_service(self, root):
        research = Mock()
        research.research.return_value = {"sources": [], "coverage": "reduced"}
        playtest = Mock()
        playtest.return_value = {"passed": True, "report": {}, "stderr": ""}
        return GameBuilderService(
            root=Path(root),
            research_service=research,
            playtest_runner=playtest,
        )

    def test_create_waits_for_go_without_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.build_service(tmp)
            response = service.handle(
                "make me a block jumping game runner real quick"
            )
            self.assertEqual(response["state"], "WAITING_FOR_GO")
            self.assertFalse(
                (Path(tmp) / "sandbox" / "game_builder_projects").exists()
            )

    def test_go_builds_and_reaches_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.build_service(tmp)
            service.handle("make me a block jumping game runner")
            response = service.handle("GO")
            self.assertEqual(response["state"], "READY")
            self.assertTrue(Path(response["project_path"]).exists())

    def test_go_without_pending_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.build_service(tmp)
            response = service.handle("GO")
            self.assertEqual(response["state"], "IDLE")
            self.assertIn("no pending", response["message"].lower())

    def test_revision_invalidates_previous_plan_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.build_service(tmp)
            first = service.handle("make me a block jumping game runner")
            revised = service.handle("add dash")
            self.assertEqual(revised["state"], "WAITING_FOR_GO")
            self.assertNotEqual(
                first["proposal"]["proposal_hash"],
                revised["proposal"]["proposal_hash"],
            )

    def test_major_ready_modification_returns_to_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.build_service(tmp)
            service.handle("make me a block jumping game runner")
            service.handle("GO")
            response = service.handle("turn it into online multiplayer")
            self.assertEqual(response["state"], "WAITING_FOR_GO")

    def test_cancel_clears_pending_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self.build_service(tmp)
            service.handle("make me a block jumping game runner")
            response = service.handle("cancel")
            self.assertEqual(response["state"], "CANCELLED")
            self.assertIsNone(response["proposal"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_game_service -v
```

Expected: import failure for service.

- [ ] **Step 3: Implement research and approval transitions**

```python
# nova_runtime/game_builder/service.py
from __future__ import annotations

from pathlib import Path
from typing import Callable

from nova_runtime.game_builder.enhancer import enhance_game_idea
from nova_runtime.game_builder.generator import generate_project
from nova_runtime.game_builder.intent import classify_game_message
from nova_runtime.game_builder.models import GameProposal, ResearchSource
from nova_runtime.game_builder.project_files import ProjectFiles
from nova_runtime.game_builder.repair import RepairEngine
from nova_runtime.game_builder.static_checks import run_static_checks
from nova_runtime.game_builder.store import GameSessionStore


def proposal_from_dict(data: dict[str, object]) -> GameProposal:
    return GameProposal(
        idea=str(data["idea"]),
        title=str(data["title"]),
        genre=str(data["genre"]),
        core_loop=str(data["core_loop"]),
        controls=tuple(data["controls"]),
        features=tuple(data["features"]),
        visual_direction=str(data["visual_direction"]),
        accessibility=tuple(data["accessibility"]),
        optional_features=tuple(data.get("optional_features", [])),
        sources=tuple(
            ResearchSource(**source) for source in data.get("sources", [])
        ),
        proposal_hash=str(data["proposal_hash"]),
    )


def failure_fingerprint(failure: dict[str, object]) -> str:
    return f"{failure.get('category')}:{failure.get('message')}"


class GameBuilderService:
    def __init__(
        self,
        root: Path,
        research_service,
        playtest_runner: Callable[[Path, Path], dict[str, object]],
    ) -> None:
        self.root = root
        self.repo_root = root
        self.projects = root / "sandbox" / "game_builder_projects"
        self.store = GameSessionStore(root / "data" / "game_builder" / "sessions")
        self.templates = root / "game_templates"
        self.research_service = research_service
        self.playtest_runner = playtest_runner

    def handle(self, text: str) -> dict[str, object]:
        intent = classify_game_message(text)
        session = self.store.load()
        if intent.kind == "create":
            research = self.research_service.research(text)
            proposal = enhance_game_idea(text, research)
            session = {
                "state": "WAITING_FOR_GO",
                "proposal": proposal.to_dict(),
                "active_project": None,
                "research_coverage": research["coverage"],
            }
            self.store.save(session)
            return {
                **session,
                "message": "Plan ready. Add or remove features, then say GO.",
            }
        if intent.kind == "revise" and session.get("proposal"):
            previous = session["proposal"]
            research = {
                "sources": previous.get("sources", []),
                "coverage": "cached",
            }
            proposal = enhance_game_idea(
                f"{previous['idea']} | revision: {text}",
                research,
            )
            session.update(
                state="WAITING_FOR_GO",
                proposal=proposal.to_dict(),
                active_project=None,
            )
            self.store.save(session)
            return {**session, "message": "Plan revised. Say GO to build it."}
        if intent.kind == "approve":
            if session["state"] != "WAITING_FOR_GO" or not session["proposal"]:
                return {**session, "message": "There is no pending game plan to approve."}
            return self._build(session)
        if intent.kind == "cancel":
            cancelled = {
                "state": "CANCELLED",
                "proposal": None,
                "active_project": None,
            }
            self.store.save(cancelled)
            return {**cancelled, "message": "Pending game build cancelled."}
        if intent.kind == "modify_major" and session.get("active_project"):
            previous = session["proposal"]
            proposal = enhance_game_idea(
                f"{previous['idea']} | major revision: {text}",
                {"sources": previous.get("sources", []), "coverage": "cached"},
            )
            session.update(state="WAITING_FOR_GO", proposal=proposal.to_dict())
            self.store.save(session)
            return {
                **session,
                "message": "Major modification planned. Say GO to rebuild.",
            }
        if intent.kind == "modify_small" and session.get("active_project"):
            return self._apply_small_modification(session, text)
        if intent.kind == "show_code" and session.get("active_project"):
            project = Path(str(session["active_project"]))
            words = text.strip().split()
            relative = words[2] if len(words) > 2 else "game.js"
            return {
                **session,
                "source_file": relative,
                "source": ProjectFiles(project).read(relative),
                "message": f"Showing {relative}.",
            }
        if intent.kind == "open" and session.get("project_slug"):
            return {
                **session,
                "open_game_url": f"/games/{session['project_slug']}/",
                "message": "Open the active game.",
            }
        if intent.kind == "edit_code" and session.get("project_slug"):
            return {
                **session,
                "edit_code_url": f"/?tab=code&project={session['project_slug']}",
                "message": "Open the code and preview workspace.",
            }
        if intent.kind == "status":
            return {**session, "message": f"Game builder state: {session['state']}"}
        return {**session, "message": "No game-builder action was selected."}

    def _run_checks(self, project: Path) -> tuple[dict[str, object], dict[str, object]]:
        static = run_static_checks(project)
        playtest = (
            self.playtest_runner(project, self.repo_root)
            if static["passed"]
            else {"passed": False, "report": {}, "stderr": "Static checks failed"}
        )
        return static, playtest

    def _failure(
        self,
        static: dict[str, object],
        playtest: dict[str, object],
        checkpoint: Path,
    ) -> dict[str, object]:
        if not static["passed"]:
            detail = next(
                item for item in static["details"] if not item["passed"]
            )
            category = (
                "missing_file"
                if detail["category"] == "required"
                else detail["category"]
            )
            return {
                "category": category,
                "file": detail.get("file"),
                "message": static["failures"][0],
                "checkpoint": str(checkpoint),
            }
        return {
            "category": "gameplay",
            "message": str(playtest.get("stderr") or "Browser gameplay gate failed"),
            "checkpoint": str(checkpoint),
        }

    def _apply_small_modification(
        self, session: dict[str, object], text: str
    ) -> dict[str, object]:
        project = Path(str(session["active_project"]))
        files = ProjectFiles(project)
        config = json.loads(files.read("game.config.json"))
        q = text.lower()
        if "jump higher" in q:
            config["jumpPower"] = min(24, config["jumpPower"] + 2)
        elif "faster" in q:
            config["baseSpeed"] = min(config["maxSpeed"], config["baseSpeed"] + 1)
        elif "slower" in q:
            config["baseSpeed"] = max(2, config["baseSpeed"] - 1)
        checkpoint = files.save(
            "game.config.json",
            json.dumps(config, indent=2) + "\n",
        )
        return self._verify_saved_candidate(session, project, checkpoint)
```

- [ ] **Step 4: Implement build, test, repair, and blockage rules**

```python
    def _build(self, session: dict[str, object]) -> dict[str, object]:
        proposal = proposal_from_dict(session["proposal"])
        session.update(state="BUILDING")
        self.store.save(session)
        previous_project = session.get("active_project")
        if previous_project and Path(str(previous_project)).is_dir():
            ProjectFiles(Path(str(previous_project))).checkpoint("pre-major-rebuild")
        project = generate_project(proposal, self.projects)
        files = ProjectFiles(project)
        baseline = files.checkpoint("generated")
        seen: dict[str, int] = {}
        repairs: list[dict[str, object]] = []

        for attempt in range(1, 10):
            static, playtest = self._run_checks(project)
            if static["passed"] and playtest["passed"]:
                verified = files.checkpoint("verified")
                report = {
                    "passed": True,
                    "attempts": attempt,
                    "static": static,
                    "playtest": playtest,
                    "repairs": repairs,
                }
                (project / "test-report.json").write_text(
                    json.dumps(report, indent=2),
                    encoding="utf-8",
                )
                ready = {
                    **session,
                    "state": "READY",
                    "active_project": str(project),
                    "project_path": str(project),
                    "project_slug": project.name,
                    "verified_checkpoint": str(verified),
                    "open_game_url": f"/games/{project.name}/",
                    "edit_code_url": f"/?tab=code&project={project.name}",
                    "test_report": report,
                    "message": "Game built, playtested, and ready.",
                }
                self.store.save(ready)
                return ready

            failure = self._failure(static, playtest, baseline)
            fingerprint = failure_fingerprint(failure)
            seen[fingerprint] = seen.get(fingerprint, 0) + 1
            if seen[fingerprint] >= 3:
                break
            repair = RepairEngine(project, self.templates).repair(failure)
            repairs.append(repair)
            if not repair["applied"]:
                break

        blocked = {
            **session,
            "state": "BLOCKED",
            "active_project": str(project),
            "project_path": str(project),
            "project_slug": project.name,
            "repairs": repairs,
            "message": "Game could not pass a required gate.",
        }
        (project / "test-report.json").write_text(
            json.dumps(blocked, indent=2),
            encoding="utf-8",
        )
        self.store.save(blocked)
        return blocked
```

Add `import json` at the top of `service.py`.

- [ ] **Step 5: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_game_service -v
```

Expected: `Ran 6 tests ... OK`.

- [ ] **Step 6: Commit**

```powershell
git add nova_runtime/game_builder/service.py tests/test_game_service.py
git commit -m "feat: orchestrate Nova game research and builds"
```

## Task 11: Serve Generated Games and Source Safely

**Files:**
- Modify: `nova_web_server.py`
- Modify: `tests/test_nova_server_api.py`

- [ ] **Step 1: Add failing project-route tests**

Add `import shutil` and import `GAME_ROOT` from `nova_web_server` in `tests/test_nova_server_api.py`, then add:

```python
def test_game_route_serves_only_inside_project_root(self):
    project = GAME_ROOT / "blockbound-runner"
    project.mkdir(parents=True, exist_ok=True)
    (project / "index.html").write_text(
        '<canvas id="game"></canvas>',
        encoding="utf-8",
    )
    try:
        status, content_type, body = self.request(
            "GET", "/games/blockbound-runner/index.html"
        )
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b'<canvas id="game"', body)
    finally:
        shutil.rmtree(project)

def test_game_route_rejects_traversal(self):
    status, _, _ = self.request("GET", "/games/../nova_web_server.py")
    self.assertIn(status, (400, 404))
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_game_route_serves_only_inside_project_root -v
```

Expected: HTTP `404`.

- [ ] **Step 3: Add game project serving**

In `nova_web_server.py`, define:

```python
GAME_ROOT = ROOT / "sandbox" / "game_builder_projects"


def resolve_game_asset(request_path: str) -> Path:
    remainder = request_path.removeprefix("/games/").lstrip("/")
    slug, _, relative = remainder.partition("/")
    if not slug:
        raise ValueError("Missing game slug")
    project = resolve_confined_path(GAME_ROOT, slug)
    if not project.is_dir():
        raise FileNotFoundError(slug)
    return resolve_confined_path(project, relative or "index.html")
```

In `NovaHandler.do_GET()`:

```python
if path.startswith("/games/"):
    try:
        asset = resolve_game_asset(path)
        if not asset.is_file():
            raise FileNotFoundError(path)
        self.send_response(200)
        self.send_header("Content-Type", content_type(asset))
        self.end_headers()
        self.wfile.write(asset.read_bytes())
    except (ValueError, FileNotFoundError):
        self.send_response(404)
        self.end_headers()
    return
```

For source APIs:

```python
if path == "/api/game-builder/status":
    self._send_json(200, GAME_BUILDER.store.load())
    return

if path.startswith("/api/games/") and path.endswith("/files"):
    slug = path.split("/")[3]
    project = resolve_confined_path(GAME_ROOT, slug)
    self._send_json(200, {"files": ProjectFiles(project).list()})
    return

if path.startswith("/api/games/") and path.endswith("/source"):
    slug = path.split("/")[3]
    relative = parse_qs(parsed.query).get("file", [""])[0]
    project = resolve_confined_path(GAME_ROOT, slug)
    self._send_json(
        200,
        {"file": relative, "content": ProjectFiles(project).read(relative)},
    )
    return
```

Add `_send_json(status, payload)` to `NovaHandler` using `encode_json()`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api -v
```

Expected: all API tests pass.

- [ ] **Step 5: Commit**

```powershell
git add nova_web_server.py tests/test_nova_server_api.py
git commit -m "feat: serve Nova game projects safely"
```

## Task 12: Chat Routing for Research, `GO`, and Project Commands

**Files:**
- Modify: `nova_web_server.py`
- Modify: `tests/test_nova_server_api.py`

- [ ] **Step 1: Add a failing chat regression test**

```python
def test_game_request_does_not_fall_into_memory_search(self):
    status, _, body = self.request(
        "POST",
        "/api/chat",
        {"text": "make me a block jumping game runner real quick"},
    )
    self.assertEqual(status, 200)
    payload = json.loads(body)
    self.assertIn("WAITING_FOR_GO", payload["response"])
    self.assertNotIn("related knowledge", payload["response"].lower())
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_game_request_does_not_fall_into_memory_search -v
```

Expected: current response contains related lesson memory.

- [ ] **Step 3: Route game intent before dictionary and fuzzy memory**

Initialize the service beside the movement service:

```python
from nova_runtime.game_builder.playtest import run_playtest
from nova_runtime.game_builder.research import (
    GitHubProvider,
    LocalKnowledgeProvider,
    MediaWikiProvider,
    OfficialDocsProvider,
    ResearchService,
)
from nova_runtime.game_builder.service import GameBuilderService

GAME_BUILDER = GameBuilderService(
    root=ROOT,
    research_service=ResearchService(
        [
            OfficialDocsProvider(),
            GitHubProvider(),
            MediaWikiProvider(),
            LocalKnowledgeProvider(),
        ]
    ),
    playtest_runner=run_playtest,
)
```

At the top of `brain_route()`, after safety/permission commands:

```python
game_intent = classify_game_message(text)
if game_intent.kind != "none":
    result = GAME_BUILDER.handle(text)
    trace["roles"] = [
        "planner_transformer",
        "right_hemisphere",
        "critic_conscience_transformer",
        "speech_output_transformer",
    ]
    trace["skills"] = [
        "game_intent",
        "internet_research",
        "approval_gate",
        "game_builder",
    ]
    trace["confidence"] = 0.96
    trace["memory_event"] = f"game_builder:{result['state']}"
    return format_game_builder_response(result), trace
```

Implement the response formatter:

```python
def format_game_builder_response(result: dict[str, object]) -> str:
    state = str(result["state"])
    lines = [f"[GAME BUILDER:{state}]"]
    proposal = result.get("proposal")
    if isinstance(proposal, dict):
        lines.extend(
            [
                f"Title: {proposal['title']}",
                f"Core loop: {proposal['core_loop']}",
                "Controls: " + ", ".join(proposal["controls"]),
                "Features: " + ", ".join(proposal["features"]),
            ]
        )
        optional = proposal.get("optional_features", [])
        if optional:
            lines.append("Optional: " + ", ".join(optional))
        sources = proposal.get("sources", [])
        if sources:
            lines.append("Research:")
            for source in sources[:6]:
                lines.append(f"  - {source['title']}: {source['url']}")
    if state == "WAITING_FOR_GO":
        if result.get("research_coverage") == "reduced":
            lines.append(
                "Research coverage is reduced; the proposal also uses local verified patterns."
            )
        lines.append("Add or remove features, or say GO to build.")
    if state == "READY":
        lines.append(f"Open Game: {result['open_game_url']}")
        lines.append(f"Edit Code: {result['edit_code_url']}")
    if result.get("source_file"):
        lines.append(f"Source: {result['source_file']}")
        lines.append("```")
        lines.append(str(result["source"]))
        lines.append("```")
    lines.append(str(result.get("message", "")))
    return "\n".join(lines)
```

Add the workshop API in `NovaHandler.do_POST()`:

```python
if parsed.path == "/api/game-builder/command":
    body = self._read_json_body()
    result = GAME_BUILDER.handle(str(body.get("text", "")))
    self._send_json(200, result)
    return
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_game_request_does_not_fall_into_memory_search -v
```

Expected: test passes.

- [ ] **Step 5: Commit**

```powershell
git add nova_web_server.py tests/test_nova_server_api.py
git commit -m "fix: route game creation before fuzzy memory"
```

## Task 13: Game Workshop UI

**Files:**
- Create: `web/game-workshop.js`
- Modify: `web/index.html`
- Modify: `web/styles.css`
- Modify: `web/app.js`
- Create: `tests/browser/game_workshop.spec.mjs`

- [ ] **Step 1: Add the workshop panel**

`web/index.html`:

```html
<section id="games-panel" data-panel="games" hidden>
  <header class="workshop-header">
    <h2>Game Workshop</h2>
    <span id="game-builder-state">IDLE</span>
  </header>
  <form id="game-idea-form">
    <textarea id="game-idea" placeholder="Describe your game idea…"></textarea>
    <button type="submit">Research + Enhance</button>
  </form>
  <article id="game-proposal" hidden>
    <h3 id="proposal-title"></h3>
    <div id="proposal-core-loop"></div>
    <div id="proposal-features"></div>
    <div id="proposal-sources"></div>
    <button id="approve-game">GO — Build This</button>
  </article>
  <section id="game-build-progress"></section>
  <a id="open-game" hidden target="_blank">Open Game</a>
  <button id="open-editor" hidden>Edit Code</button>
</section>
```

- [ ] **Step 2: Implement workshop API calls**

```javascript
// web/game-workshop.js
export function mountGameWorkshop() {
  const form = document.querySelector("#game-idea-form");
  const idea = document.querySelector("#game-idea");
  const approve = document.querySelector("#approve-game");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendGameCommand(idea.value);
  });
  approve.addEventListener("click", () => sendGameCommand("GO"));
}

async function sendGameCommand(text) {
  const response = await fetch("/api/game-builder/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const payload = await response.json();
  renderGameBuilder(payload);
}

function renderGameBuilder(payload) {
  document.querySelector("#game-builder-state").textContent = payload.state;
  const article = document.querySelector("#game-proposal");
  const proposal = payload.proposal;
  article.hidden = !proposal;
  if (proposal) {
    document.querySelector("#proposal-title").textContent = proposal.title;
    document.querySelector("#proposal-core-loop").textContent = proposal.core_loop;
    document.querySelector("#proposal-features").textContent =
      proposal.features.join(" · ");
    const sources = document.querySelector("#proposal-sources");
    sources.replaceChildren(
      ...proposal.sources.map((source) => {
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = source.title;
        return link;
      }),
    );
  }
  const openGame = document.querySelector("#open-game");
  openGame.hidden = payload.state !== "READY";
  if (!openGame.hidden) openGame.href = payload.open_game_url;
  const editor = document.querySelector("#open-editor");
  editor.hidden = payload.state !== "READY";
  editor.dataset.project = payload.project_slug ?? "";
  document.querySelector("#game-build-progress").textContent =
    payload.message ?? "";
}
```

Render source links with safe anchors, state, test results, repair count, Open Game URL, and Edit Code button.

- [ ] **Step 3: Add the browser approval-gate test**

```javascript
// tests/browser/game_workshop.spec.mjs
import { test, expect } from "@playwright/test";

test("game workshop researches, waits for GO, then exposes the game", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000");
  await page.getByRole("button", { name: "Game Workshop" }).click();
  await page.getByPlaceholder("Describe your game idea…").fill(
    "Make me a block jumping game runner"
  );
  await page.getByRole("button", { name: "Research + Enhance" }).click();
  await expect(page.getByText("WAITING_FOR_GO")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Game" })).toBeHidden();
  await page.getByRole("button", { name: "GO — Build This" }).click();
  await expect(page.getByText("READY")).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole("link", { name: "Open Game" })).toBeVisible();
});
```

- [ ] **Step 4: Run the browser test**

Run:

```powershell
npm.cmd run test:browser -- tests/browser/game_workshop.spec.mjs
```

Expected: one workshop test passes.

- [ ] **Step 5: Commit**

```powershell
git add web/game-workshop.js web/index.html web/styles.css web/app.js tests/browser/game_workshop.spec.mjs
git commit -m "feat: add Nova game workshop UI"
```

## Task 14: Code Editor and Live Preview APIs

**Files:**
- Create: `web/code-preview.js`
- Modify: `web/index.html`
- Modify: `web/styles.css`
- Modify: `nova_web_server.py`
- Modify: `tests/test_nova_server_api.py`

- [ ] **Step 1: Add failing editor API tests**

```python
def test_editor_save_creates_checkpoint_and_returns_test_state(self):
    status, _, body = self.request(
        "POST",
        "/api/games/blockbound-runner/save",
        {"file": "game.config.json", "content": '{"jumpPower": 15}'},
    )
    self.assertEqual(status, 200)
    payload = json.loads(body)
    self.assertTrue(payload["checkpoint"])
    self.assertIn(payload["state"], ("READY", "REPAIRING", "BLOCKED"))

def test_editor_rejects_path_escape(self):
    status, _, _ = self.request(
        "POST",
        "/api/games/blockbound-runner/save",
        {"file": "../nova_web_server.py", "content": "bad"},
    )
    self.assertEqual(status, 400)
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api.NovaServerApiTests.test_editor_save_creates_checkpoint_and_returns_test_state -v
```

Expected: HTTP `404`.

- [ ] **Step 3: Add editor routes**

Add these methods to `GameBuilderService`:

```python
    def _project(self, slug: str) -> Path:
        project = (self.projects / slug).resolve()
        if self.projects.resolve() not in project.parents or not project.is_dir():
            raise ValueError("Unknown game project")
        return project

    def save_file(
        self,
        slug: str,
        relative: str,
        content: str,
    ) -> dict[str, object]:
        session = self.store.load()
        project = self._project(slug)
        checkpoint = ProjectFiles(project).save(relative, content)
        return self._verify_saved_candidate(
            session,
            project,
            checkpoint,
            edited_file=relative,
        )

    def _verify_saved_candidate(
        self,
        session: dict[str, object],
        project: Path,
        checkpoint: Path,
        edited_file: str = "game.config.json",
    ) -> dict[str, object]:
        files = ProjectFiles(project)
        original = (
            checkpoint / edited_file
        ).read_text(encoding="utf-8") if (checkpoint / edited_file).exists() else ""
        repairs: list[dict[str, object]] = []
        seen: dict[str, int] = {}

        for _ in range(3):
            static, playtest = self._run_checks(project)
            if static["passed"] and playtest["passed"]:
                verified = files.checkpoint("verified")
                current = files.read(edited_file)
                diff = "".join(
                    difflib.unified_diff(
                        original.splitlines(True),
                        current.splitlines(True),
                        fromfile=f"{edited_file}:before",
                        tofile=f"{edited_file}:verified",
                    )
                )
                ready = {
                    **session,
                    "state": "READY",
                    "active_project": str(project),
                    "project_slug": project.name,
                    "verified_checkpoint": str(verified),
                    "checkpoint": str(checkpoint),
                    "repairs": repairs,
                    "repair_diff": diff,
                    "test_report": {"static": static, "playtest": playtest},
                }
                self.store.save(ready)
                return ready

            failure = self._failure(static, playtest, checkpoint)
            fingerprint = failure_fingerprint(failure)
            seen[fingerprint] = seen.get(fingerprint, 0) + 1
            if seen[fingerprint] >= 3:
                break
            repair = RepairEngine(project, self.templates).repair(failure)
            repairs.append(repair)
            if not repair["applied"]:
                break

        broken_root = project / "broken-drafts"
        broken_root.mkdir(exist_ok=True)
        broken = broken_root / f"{datetime.now():%Y%m%d-%H%M%S-%f}"
        broken.mkdir()
        for path in project.iterdir():
            if path.is_file():
                shutil.copy2(path, broken / path.name)

        restore_path = Path(
            str(session.get("verified_checkpoint") or checkpoint)
        )
        files.restore(restore_path)
        blocked = {
            **session,
            "state": "BLOCKED",
            "checkpoint": str(checkpoint),
            "broken_draft_path": str(broken),
            "repairs": repairs,
            "message": "Draft preserved; last verified game restored.",
        }
        self.store.save(blocked)
        return blocked

    def test_project(self, slug: str) -> dict[str, object]:
        session = self.store.load()
        project = self._project(slug)
        checkpoint = ProjectFiles(project).checkpoint("manual-test")
        return self._verify_saved_candidate(session, project, checkpoint)

    def restore_working(self, slug: str) -> dict[str, object]:
        session = self.store.load()
        checkpoint = Path(str(session["verified_checkpoint"]))
        project = self._project(slug)
        ProjectFiles(project).restore(checkpoint)
        return {**session, "state": "READY", "message": "Working version restored."}

    def undo(self, slug: str) -> dict[str, object]:
        session = self.store.load()
        checkpoint = Path(str(session["checkpoint"]))
        project = self._project(slug)
        ProjectFiles(project).restore(checkpoint)
        return {**session, "state": "READY", "message": "Previous edit restored."}
```

Add these imports to `service.py`:

```python
import difflib
import shutil
from datetime import datetime
```

In `NovaHandler.do_POST()`, parse `/api/games/<slug>/<action>` and dispatch:

```python
if path.startswith("/api/games/"):
    _, _, _, slug, action = path.split("/", 4)
    body = self._read_json_body()
    try:
        if action == "save":
            payload = GAME_BUILDER.save_file(
                slug,
                str(body["file"]),
                str(body["content"]),
            )
        elif action == "test":
            payload = GAME_BUILDER.test_project(slug)
        elif action == "undo":
            payload = GAME_BUILDER.undo(slug)
        elif action == "restore-working":
            payload = GAME_BUILDER.restore_working(slug)
        else:
            self._send_json(404, {"error": "Unknown editor action"})
            return
        self._send_json(200, payload)
    except (KeyError, ValueError) as error:
        self._send_json(400, {"error": str(error)})
    return
```

- [ ] **Step 4: Build the editor UI**

`web/index.html`:

```html
<section id="code-panel" data-panel="code" hidden>
  <aside id="project-files"></aside>
  <section class="editor-column">
    <div class="editor-actions">
      <button id="run-code">Run</button>
      <button id="save-code">Save</button>
      <button id="test-code">Test</button>
      <button id="undo-code">Undo</button>
      <button id="restore-code">Restore Working Version</button>
    </div>
    <textarea id="source-editor" spellcheck="false"></textarea>
    <pre id="editor-console"></pre>
  </section>
  <section class="preview-column">
    <iframe id="game-preview" sandbox="allow-scripts allow-same-origin"></iframe>
    <pre id="repair-diff"></pre>
  </section>
</section>
```

```javascript
// web/code-preview.js
let activeProject = null;
let activeFile = null;

export async function openGameEditor(slug) {
  activeProject = slug;
  const response = await fetch(`/api/games/${slug}/files`);
  const payload = await response.json();
  const list = document.querySelector("#project-files");
  list.replaceChildren(
    ...payload.files.map((name) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = name;
      button.addEventListener("click", () => loadSource(name));
      return button;
    }),
  );
  document.querySelector("#game-preview").src =
    `/games/${slug}/?preview=${Date.now()}`;
  if (payload.files.includes("game.js")) await loadSource("game.js");
}

async function loadSource(name) {
  activeFile = name;
  const response = await fetch(
    `/api/games/${activeProject}/source?file=${encodeURIComponent(name)}`,
  );
  const payload = await response.json();
  document.querySelector("#source-editor").value = payload.content;
}

async function postAction(action, body = {}) {
  const response = await fetch(
    `/api/games/${activeProject}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error ?? "Editor request failed");
  document.querySelector("#editor-console").textContent =
    JSON.stringify(payload.test_report ?? payload, null, 2);
  document.querySelector("#repair-diff").textContent =
    payload.repair_diff ?? "";
  if (payload.repairs?.length) {
    document.querySelector("#editor-console").prepend(
      "Minimal repair applied\n",
    );
  }
  document.querySelector("#game-preview").src =
    `/games/${activeProject}/?preview=${Date.now()}`;
  return payload;
}

export function mountCodePreview() {
  document.querySelector("#save-code").addEventListener("click", () =>
    postAction("save", {
      file: activeFile,
      content: document.querySelector("#source-editor").value,
    }),
  );
  document.querySelector("#run-code").addEventListener("click", () => {
    document.querySelector("#game-preview").src =
      `/games/${activeProject}/?preview=${Date.now()}`;
  });
  document.querySelector("#test-code").addEventListener(
    "click",
    () => postAction("test"),
  );
  document.querySelector("#undo-code").addEventListener(
    "click",
    () => postAction("undo"),
  );
  document.querySelector("#restore-code").addEventListener(
    "click",
    () => postAction("restore-working"),
  );
}
```

Import `openGameEditor` in `web/game-workshop.js`; the **Edit Code** button switches to the code tab and calls it with `button.dataset.project`. Source is assigned through `.value` or `.textContent`, never injected with `.innerHTML`.

- [ ] **Step 5: Run API tests and verify GREEN**

Run:

```powershell
py -3 -m unittest tests.test_nova_server_api -v
```

Expected: all API tests pass.

- [ ] **Step 6: Commit**

```powershell
git add web/code-preview.js web/index.html web/styles.css nova_web_server.py tests/test_nova_server_api.py
git commit -m "feat: add editable game code preview"
```

## Task 15: Manual-Break Regression and Auto-Repair Browser Test

**Files:**
- Modify: `tests/browser/game_workshop.spec.mjs`
- Modify: `tests/browser/generated_game.spec.mjs`
- Modify: `tests/test_game_service.py`

- [ ] **Step 1: Add the manual break test**

```javascript
test("broken manual jump edit is repaired and preview remains playable", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000");
  await page.getByRole("button", { name: "Code + Preview" }).click();
  await page.getByText("game.config.json", { exact: true }).click();
  await page.locator("#source-editor").fill(
    JSON.stringify({
      title: "Blockbound Runner",
      gravity: 0.8,
      jumpPower: 0,
      baseSpeed: 6,
      maxSpeed: 15,
      obstacleMinGap: 320,
      obstacleMaxGap: 560,
      reducedMotion: false,
    }, null, 2)
  );
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Minimal repair applied")).toBeVisible({
    timeout: 90000,
  });
  await expect(page.locator("#repair-diff")).toContainText("jumpPower");

  const frame = page.frameLocator("#game-preview");
  await expect(frame.locator("#game")).toBeVisible();
});
```

- [ ] **Step 2: Add an unrepairable-draft service test**

```python
def test_unrepairable_edit_restores_last_working_checkpoint(self):
    with tempfile.TemporaryDirectory() as tmp:
        service = self.build_service(tmp)
        service.handle("make me a block jumping runner")
        ready = service.handle("GO")
        project = Path(ready["project_path"])
        original = (project / "styles.css").read_text(encoding="utf-8")
        service.playtest_runner.return_value = {
            "passed": False,
            "report": {},
            "stderr": "unclassified visual failure",
        }
        result = service.save_file(
            ready["project_slug"],
            "styles.css",
            "body { background: hotpink; }",
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(
            (project / "styles.css").read_text(encoding="utf-8"), original
        )
        self.assertTrue(result["broken_draft_path"])

def test_small_modification_retests_without_new_go(self):
    with tempfile.TemporaryDirectory() as tmp:
        service = self.build_service(tmp)
        service.handle("make me a block jumping game runner")
        ready = service.handle("GO")
        before = json.loads(
            (Path(ready["project_path"]) / "game.config.json").read_text()
        )["jumpPower"]
        modified = service.handle("make the jump higher")
        after = json.loads(
            (Path(modified["active_project"]) / "game.config.json").read_text()
        )["jumpPower"]
        self.assertEqual(modified["state"], "READY")
        self.assertGreater(after, before)
```

- [ ] **Step 3: Run Python tests**

Run:

```powershell
py -3 -m unittest tests.test_game_service tests.test_game_repair tests.test_game_project_files -v
```

Expected: all tests pass.

- [ ] **Step 4: Run browser tests**

Run:

```powershell
npm.cmd run test:browser
```

Expected: workshop, generated game, editor repair, and Movement Lab tests all pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/browser/game_workshop.spec.mjs tests/browser/generated_game.spec.mjs tests/test_game_service.py
git commit -m "test: verify game editor automatic repair"
```

## Task 16: Documentation, Cleanup, and Full Verification

**Files:**
- Create: `docs/GAME_WORKSHOP_USER_GUIDE.md`
- Modify: `README_LAPTOP_INSTALL.md`
- Modify: `.gitignore`

- [ ] **Step 1: Document the user workflow**

Create `docs/GAME_WORKSHOP_USER_GUIDE.md` with:

```markdown
# Nova Game Workshop

1. Open **Game Workshop** and describe an idea.
2. Nova researches public sources and local verified patterns.
3. Review the enhanced proposal. Add or remove features.
4. Say or click **GO** only when the plan is right.
5. Wait for the build, browser playtest, and repair loop.
6. Use **Open Game**, **Show Code**, or **Edit Code**.

The editor provides **Run**, **Save**, **Test**, **Undo**, and
**Restore Working Version**. Every save creates a checkpoint. A broken edit
is tested and repaired automatically; Nova shows the repair diff. If safe
repair cannot progress, the draft is preserved and the last verified game is
restored.

Small changes such as jump height, speed, color, and obstacle frequency apply
and retest immediately. Major changes return to the proposal and **GO** gate.

Projects live in `sandbox/game_builder_projects/`. Each project contains
`test-report.json`, `repair-log.jsonl`, `checkpoints/`, and, when needed,
`broken-drafts/`.
```

- [ ] **Step 2: Ignore generated runtime artifacts**

Append:

```gitignore
# Nova Game Builder runtime
data/game_builder/sessions/*.json
data/game_builder/research_cache/*.json
sandbox/game_builder_projects/*/checkpoints/
sandbox/game_builder_projects/*/broken-drafts/
test-results/
playwright-report/
node_modules/
```

Keep `sandbox/game_builder_projects/.gitkeep`.

- [ ] **Step 3: Run all Python tests**

Run:

```powershell
py -3 -m unittest discover -s tests -v
```

Expected: all Python tests pass, including `test_windows_launcher`.

- [ ] **Step 4: Run all browser tests**

Start server:

```powershell
py -3 nova_web_server.py 3000
```

Run:

```powershell
npm.cmd run test:browser
```

Expected: all browser tests pass with no unhandled page errors.

- [ ] **Step 5: Verify the exact original failure**

Run:

```powershell
$body = @{text='YES CAN U MAKE ME A BLOCK JUMPING GAME RUNNER REAL QUICK'} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:3000/api/chat' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 10
```

Expected:

- response state is `WAITING_FOR_GO`;
- response includes an enhanced plan and source coverage;
- response does not contain `I found related knowledge`;
- no generated project exists yet.

Then:

```powershell
$body = @{text='GO'} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:3000/api/chat' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 10
```

Expected:

- response state is `READY`;
- Open Game URL is present;
- static and gameplay tests passed;
- physical output is unrelated and remains locked.

- [ ] **Step 6: Check repository cleanliness**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional implementation changes are present.

- [ ] **Step 7: Commit**

```powershell
git add docs/GAME_WORKSHOP_USER_GUIDE.md README_LAPTOP_INSTALL.md .gitignore
git commit -m "docs: explain Nova game workshop"
```

## Completion Gate

Do not claim this plan complete until:

- game creation requests outrank dictionary and fuzzy memory;
- research produces attributed sources or an honest reduced-coverage label;
- no project source exists before `GO`;
- generated game loads and plays in Chromium;
- jump, score, collision, game over, restart, keyboard, and touch gates pass;
- repair loop proves RED then GREEN on a seeded build defect;
- manual editor saves create checkpoints;
- a breaking manual edit is auto-repaired with a visible diff;
- an unrepairable draft is preserved while the last working game is restored;
- Game Workshop, Code + Preview, Movement Lab, and chat remain functional together;
- all Python and browser tests pass.
