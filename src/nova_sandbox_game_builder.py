from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


PROJECT_SLUG = "Nova_Pac_Runner"
PROJECT_NAME = "Nova Pac Runner"
TEMPLE_PROJECT_SLUG = "Nova_Temple_Runner"
TEMPLE_PROJECT_NAME = "Nova Temple Runner"
SHOOTER_PROJECT_SLUG = "Nova_Sky_Shooter"
SHOOTER_PROJECT_NAME = "Nova Sky Shooter"
SANDBOX_URL_PREFIX = "/sandbox/app_builder_projects"


@dataclass(frozen=True)
class GameBuildResult:
    project_name: str
    project_dir: Path
    entry_file: Path
    url_path: str
    files: tuple[Path, ...]


def is_pacman_game_request(text: str) -> bool:
    normalized = _normalize(text)
    has_build_verb = re.search(r"\b(?:make|create|build|generate)\b", normalized) is not None
    names_pacman = re.search(r"\b(?:pac[\s-]?man|pacman)\b", normalized) is not None
    asks_for_game = re.search(r"\b(?:game|arcade|maze)\b", normalized) is not None
    asks_question = normalized.startswith(("what ", "why ", "when ", "where ", "who ", "how "))
    return has_build_verb and names_pacman and asks_for_game and not asks_question


def is_temple_run_game_request(text: str) -> bool:
    normalized = _normalize(text)
    has_build_verb = re.search(r"\b(?:make|create|build|generate)\b", normalized) is not None
    names_runner = (
        re.search(r"\btemple\s+run\b", normalized) is not None
        or re.search(r"\bendless\s+runner\b", normalized) is not None
        or re.search(r"\brunner\s+game\b", normalized) is not None
    )
    asks_for_game = re.search(r"\b(?:game|runner|3d|full)\b", normalized) is not None
    asks_question = normalized.startswith(("what ", "why ", "when ", "where ", "who ", "how "))
    return has_build_verb and names_runner and asks_for_game and not asks_question


def is_shooter_game_request(text: str) -> bool:
    normalized = _normalize(text)
    has_build_verb = re.search(r"\b(?:make|create|build|generate)\b", normalized) is not None
    has_want_intent = re.search(r"\b(?:i want|i need|give me|can you make|make me)\b", normalized) is not None
    names_shooter = (
        re.search(r"\b(?:shooting|shooter|space shooter|flying shooter|top shooter|top down shooter|bullet hell)\b", normalized) is not None
        or ("flying" in normalized and "game" in normalized)
    )
    asks_for_game = re.search(r"\b(?:game|arcade|shooter|shooting|flying|space)\b", normalized) is not None
    asks_question = normalized.startswith(("what ", "why ", "when ", "where ", "who ", "how "))
    recommends = re.search(r"\b(?:recommend|suggest|try|popular choices|ideas)\b", normalized) is not None
    return (has_build_verb or has_want_intent) and names_shooter and asks_for_game and not asks_question and not recommends


def build_pacman_game(projects_root: str | Path | None = None) -> GameBuildResult:
    root = Path(projects_root) if projects_root is not None else _default_projects_root()
    project_dir = root / PROJECT_SLUG
    project_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "index.html": _game_html(),
        "README.md": _readme(),
        "manifest.json": json.dumps(
            {
                "name": PROJECT_NAME,
                "kind": "browser_game",
                "entry": "index.html",
                "engine": "Three.js",
                "renderer": "three-webgl",
                "webgl": True,
                "autopilot": True,
                "scoring": True,
                "age_ticks": True,
                "safe_sandbox": True,
            },
            indent=2,
        )
        + "\n",
        "test_spec.json": json.dumps(
            {
                "checks": [
                    "loads index.html",
                    "renders with Three.js WebGLRenderer",
                    "exposes window.NovaPacGame.getState()",
                    "autopilot moves the player without keyboard input",
                    "score increases when pellets are eaten",
                    "ageTicks increases over time",
                    "DOM HUD stays synchronized with simulation state",
                ]
            },
            indent=2,
        )
        + "\n",
    }

    written: list[Path] = []
    for name, content in files.items():
        path = project_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return GameBuildResult(
        project_name=PROJECT_NAME,
        project_dir=project_dir,
        entry_file=project_dir / "index.html",
        url_path=f"{SANDBOX_URL_PREFIX}/{PROJECT_SLUG}/index.html",
        files=tuple(written),
    )


def build_temple_run_game(projects_root: str | Path | None = None) -> GameBuildResult:
    root = Path(projects_root) if projects_root is not None else _default_projects_root()
    project_dir = root / TEMPLE_PROJECT_SLUG
    project_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "index.html": _temple_run_html(),
        "README.md": _temple_run_readme(),
        "manifest.json": json.dumps(
            {
                "name": TEMPLE_PROJECT_NAME,
                "kind": "browser_game",
                "entry": "index.html",
                "engine": "Three.js",
                "renderer": "three-webgl",
                "genre": "3d_endless_runner",
                "lanes": 3,
                "levels": True,
                "level_count": 5,
                "progression": "distance_goals",
                "autopilot": True,
                "scoring": True,
                "jumping": True,
                "sliding": True,
                "safe_sandbox": True,
            },
            indent=2,
        )
        + "\n",
        "test_spec.json": json.dumps(
            {
                "checks": [
                    "loads index.html",
                    "renders with Three.js WebGLRenderer",
                    "exposes window.NovaTempleRunner.getState()",
                    "autopilot changes lanes without keyboard input",
                    "score and distance increase over time",
                    "level increases as distance goals are reached",
                    "coins increase score when collected",
                    "obstacles reset the runner when hit",
                    "ageTicks increases over time",
                ]
            },
            indent=2,
        )
        + "\n",
    }

    written: list[Path] = []
    for name, content in files.items():
        path = project_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return GameBuildResult(
        project_name=TEMPLE_PROJECT_NAME,
        project_dir=project_dir,
        entry_file=project_dir / "index.html",
        url_path=f"{SANDBOX_URL_PREFIX}/{TEMPLE_PROJECT_SLUG}/index.html",
        files=tuple(written),
    )


def build_sky_shooter_game(projects_root: str | Path | None = None) -> GameBuildResult:
    root = Path(projects_root) if projects_root is not None else _default_projects_root()
    project_dir = root / SHOOTER_PROJECT_SLUG
    project_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "index.html": _sky_shooter_html(),
        "README.md": _sky_shooter_readme(),
        "manifest.json": json.dumps(
            {
                "name": SHOOTER_PROJECT_NAME,
                "kind": "browser_game",
                "entry": "index.html",
                "engine": "Three.js",
                "renderer": "three-webgl",
                "genre": "top_down_flying_shooter",
                "waves": True,
                "boss_fights": True,
                "powerups": True,
                "touch_controls": True,
                "autopilot": True,
                "scoring": True,
                "safe_sandbox": True,
            },
            indent=2,
        )
        + "\n",
        "test_spec.json": json.dumps(
            {
                "checks": [
                    "loads index.html",
                    "renders with Three.js WebGLRenderer",
                    "exposes window.NovaSkyShooter.getState()",
                    "autopilot flies and fires without keyboard input",
                    "enemy waves spawn and move through the playfield",
                    "boss waves create a higher-health enemy",
                    "bullets can destroy enemies and increase score",
                    "powerups can increase fire rate and shield power",
                    "DOM HUD stays synchronized with score, wave, health, and power",
                    "keyboard and touch controls are available",
                ]
            },
            indent=2,
        )
        + "\n",
    }

    written: list[Path] = []
    for name, content in files.items():
        path = project_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return GameBuildResult(
        project_name=SHOOTER_PROJECT_NAME,
        project_dir=project_dir,
        entry_file=project_dir / "index.html",
        url_path=f"{SANDBOX_URL_PREFIX}/{SHOOTER_PROJECT_SLUG}/index.html",
        files=tuple(written),
    )


def _default_projects_root() -> Path:
    return Path(__file__).resolve().parents[1] / "sandbox" / "app_builder_projects"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def _readme() -> str:
    return dedent(
        f"""
        # {PROJECT_NAME}

        A sandboxed Pac-Man-style browser game created by Nova's game builder.

        - Open `index.html` in a browser.
        - The playfield renders with Three.js/WebGL.
        - The yellow runner moves on its own when you do not press arrows.
        - Arrow keys can override the autopilot.
        - Eating pellets increases score.
        - The HUD reports score, remaining pellets, age ticks, and a simple smart score.
        """
    ).strip() + "\n"


def _temple_run_readme() -> str:
    return dedent(
        f"""
        # {TEMPLE_PROJECT_NAME}

        A sandboxed 3D endless-runner browser game created by Nova's game builder.

        - Open `index.html` in a browser.
        - The runner uses a Three.js/WebGL scene with three lanes.
        - Five distance-based levels increase speed, obstacle density, and temple color.
        - Nova autopilot dodges obstacles and collects coins when you do not press keys.
        - Arrow Left/Right change lanes, Space jumps, and Arrow Down slides.
        - The HUD reports score, distance, coins, level, age ticks, and autopilot state.
        """
    ).strip() + "\n"


def _sky_shooter_readme() -> str:
    return dedent(
        f"""
        # {SHOOTER_PROJECT_NAME}

        A sandboxed top-down flying shooter created by Nova's game builder.

        - Open `index.html` in a browser or app preview.
        - The game renders with Three.js/WebGL.
        - Nova autopilot flies, dodges, and fires when you do not press controls.
        - Enemy waves, boss pressure, bullets, score, health, and powerups are included.
        - Arrow keys or WASD fly, Space fires, and touch or pointer drag steers.
        """
    ).strip() + "\n"


def _sky_shooter_html() -> str:
    return dedent(
        r"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <link rel="icon" href="data:," />
          <title>Nova Sky Shooter</title>
          <style>
            * { box-sizing: border-box; }
            :root {
              --void: #070915;
              --panel: #10172f;
              --panel-2: #151f42;
              --line: rgba(166, 187, 255, .24);
              --text: #f6f8ff;
              --muted: #aeb9d9;
              --cyan: #5fe5ff;
              --gold: #ffcf5a;
              --rose: #ff5f87;
              --green: #74f0a1;
            }
            html, body {
              margin: 0;
              min-height: 100%;
              background: radial-gradient(circle at 50% 0%, #142248 0, var(--void) 46%, #03050c 100%);
              color: var(--text);
              font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            body {
              width: 100%;
              min-height: 100vh;
              display: grid;
              place-items: center;
              padding: 16px;
              overflow-x: hidden;
            }
            .shell {
              width: min(100%, 920px);
              min-height: min(900px, calc(100vh - 32px));
              display: grid;
              grid-template-rows: auto auto 1fr auto;
              gap: 12px;
            }
            header {
              display: flex;
              align-items: end;
              justify-content: space-between;
              gap: 14px;
            }
            h1 {
              margin: 0;
              font-size: clamp(30px, 5.5vw, 58px);
              line-height: .92;
              letter-spacing: 0;
            }
            .brief {
              max-width: 580px;
              margin: 7px 0 0;
              color: var(--muted);
              font-size: clamp(14px, 2.1vw, 17px);
            }
            .status {
              display: grid;
              grid-template-columns: repeat(5, minmax(0, 1fr));
              gap: 8px;
            }
            .stat {
              min-height: 66px;
              padding: 10px;
              border: 1px solid var(--line);
              border-radius: 8px;
              background: rgba(16, 23, 47, .92);
            }
            .stat span {
              display: block;
              color: var(--muted);
              font-size: 11px;
              text-transform: uppercase;
            }
            .stat strong {
              display: block;
              margin-top: 4px;
              font-size: clamp(20px, 3.2vw, 30px);
              line-height: 1;
            }
            #game {
              position: relative;
              min-height: 520px;
              border: 1px solid rgba(166, 187, 255, .34);
              border-radius: 8px;
              overflow: hidden;
              background: #050815;
              box-shadow: 0 18px 70px rgba(0, 0, 0, .38);
              touch-action: none;
            }
            #game canvas {
              width: 100%;
              height: 100%;
              display: block;
            }
            .overlay {
              position: absolute;
              left: 14px;
              top: 14px;
              display: flex;
              gap: 8px;
              align-items: center;
              flex-wrap: wrap;
              pointer-events: none;
            }
            .chip {
              border: 1px solid rgba(255, 255, 255, .18);
              background: rgba(5, 9, 24, .72);
              border-radius: 8px;
              padding: 7px 9px;
              color: var(--text);
              font-size: 12px;
              backdrop-filter: blur(10px);
            }
            .chip strong { color: var(--cyan); }
            .controls {
              color: var(--muted);
              font-size: 14px;
              line-height: 1.45;
            }
            .controls kbd {
              display: inline-block;
              min-width: 28px;
              padding: 3px 7px;
              border-radius: 6px;
              border: 1px solid var(--line);
              background: var(--panel-2);
              color: var(--text);
              text-align: center;
              font: inherit;
            }
            @media (max-width: 620px) {
              body { padding: 10px; }
              .shell { width: 100%; gap: 10px; }
              header { display: block; }
              .status { grid-template-columns: repeat(2, minmax(0, 1fr)); }
              .stat { min-height: 58px; }
              #game { min-height: min(68vh, 620px); }
              .overlay { left: 10px; top: 10px; right: 10px; }
            }
          </style>
        </head>
        <body>
          <main class="shell">
            <header>
              <div>
                <h1>Nova Sky Shooter</h1>
                <p class="brief">Autopilot is on. Take over to dodge, chase targets, stack powerups, and clear waves.</p>
              </div>
            </header>
            <section class="status" aria-label="Game status">
              <div class="stat"><span>Score</span><strong id="score">0</strong></div>
              <div class="stat"><span>Wave</span><strong id="wave">1</strong></div>
              <div class="stat"><span>Health</span><strong id="health">100</strong></div>
              <div class="stat"><span>Power</span><strong id="power">0</strong></div>
              <div class="stat"><span>Mode</span><strong id="mode">AUTO</strong></div>
            </section>
            <section id="game" data-renderer="three-webgl" aria-label="Nova Sky Shooter Three.js playfield">
              <div class="overlay" aria-hidden="true">
                <div class="chip"><strong>Objective</strong> clear waves</div>
                <div class="chip" id="banner">Wave incoming</div>
              </div>
            </section>
            <p class="controls">
              Use <kbd>Arrow Keys</kbd> or <kbd>WASD</kbd> to fly, <kbd>Space</kbd> to fire, or drag on the playfield. Stop input and Nova autopilot resumes.
            </p>
          </main>

          <script type="module">
            import * as THREE from "https://unpkg.com/three@0.160.0/build/three.module.js";

            const container = document.getElementById("game");
            const hud = {
              score: document.getElementById("score"),
              wave: document.getElementById("wave"),
              health: document.getElementById("health"),
              power: document.getElementById("power"),
              mode: document.getElementById("mode"),
              banner: document.getElementById("banner"),
            };

            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x050815);
            const camera = new THREE.OrthographicCamera(-10, 10, 7, -7, 0.1, 80);
            camera.position.set(0, 0, 20);
            camera.lookAt(0, 0, 0);

            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
            renderer.domElement.dataset.engine = "three-webgl";
            renderer.domElement.dataset.threeRevision = THREE.REVISION;
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            container.appendChild(renderer.domElement);

            const state = {
              score: 0,
              wave: 1,
              health: 100,
              power: 0,
              ageTicks: 0,
              autopilot: true,
              mode: "AUTO",
              enemiesDestroyed: 0,
              bossActive: false,
            };

            const bounds = { x: 8.8, y: 6.1 };
            const keys = new Set();
            const enemies = [];
            const bullets = [];
            const powerups = [];
            let spawnTimer = 0;
            let fireCooldown = 0;
            let lastInputAt = 0;
            let pointerTarget = null;
            const clock = new THREE.Clock();

            const shipShape = new THREE.Shape();
            shipShape.moveTo(0, 0.74);
            shipShape.lineTo(-0.54, -0.52);
            shipShape.lineTo(0, -0.25);
            shipShape.lineTo(0.54, -0.52);
            shipShape.lineTo(0, 0.74);
            const player = new THREE.Group();
            player.add(new THREE.Mesh(new THREE.ShapeGeometry(shipShape), new THREE.MeshBasicMaterial({ color: 0x5fe5ff })));
            const cockpit = new THREE.Mesh(new THREE.CircleGeometry(0.17, 24), new THREE.MeshBasicMaterial({ color: 0xffcf5a }));
            cockpit.position.set(0, 0.08, 0.02);
            player.add(cockpit);
            const flame = new THREE.Mesh(new THREE.CircleGeometry(0.18, 18), new THREE.MeshBasicMaterial({ color: 0xff5f87, transparent: true, opacity: 0.82 }));
            flame.scale.set(0.7, 1.5, 1);
            flame.position.set(0, -0.7, -0.01);
            player.add(flame);
            player.position.set(0, -4.7, 1);
            scene.add(player);

            const starGeometry = new THREE.BufferGeometry();
            const starPositions = [];
            for (let i = 0; i < 260; i += 1) {
              starPositions.push((Math.random() - 0.5) * 22, (Math.random() - 0.5) * 16, -2);
            }
            starGeometry.setAttribute("position", new THREE.Float32BufferAttribute(starPositions, 3));
            const stars = new THREE.Points(starGeometry, new THREE.PointsMaterial({ color: 0x9ab5ff, size: 0.045, transparent: true, opacity: 0.75 }));
            scene.add(stars);

            function clamp(value, min, max) {
              return Math.max(min, Math.min(max, value));
            }

            function randomRange(min, max) {
              return min + Math.random() * (max - min);
            }

            function makeEnemyMesh(isBoss = false) {
              const group = new THREE.Group();
              const body = new THREE.Mesh(
                isBoss ? new THREE.IcosahedronGeometry(0.72, 1) : new THREE.OctahedronGeometry(0.38, 0),
                new THREE.MeshBasicMaterial({ color: isBoss ? 0xff5f87 : 0xa976ff, wireframe: isBoss })
              );
              group.add(body);
              const core = new THREE.Mesh(
                new THREE.CircleGeometry(isBoss ? 0.28 : 0.16, 22),
                new THREE.MeshBasicMaterial({ color: isBoss ? 0xffcf5a : 0x74f0a1 })
              );
              core.position.z = 0.04;
              group.add(core);
              return group;
            }

            function spawnEnemyWave() {
              const isBossWave = state.wave % 4 === 0;
              if (isBossWave) {
                const mesh = makeEnemyMesh(true);
                mesh.position.set(0, bounds.y + 0.8, 1);
                scene.add(mesh);
                enemies.push({ mesh, hp: 18 + state.wave * 4, maxHp: 18 + state.wave * 4, speed: 0.75, boss: true, phase: 0 });
                state.bossActive = true;
                hud.banner.textContent = "Boss wave";
                return;
              }

              const count = Math.min(5 + state.wave, 11);
              for (let i = 0; i < count; i += 1) {
                const mesh = makeEnemyMesh(false);
                mesh.position.set(randomRange(-bounds.x, bounds.x), bounds.y + 0.8 + i * 0.58, 1);
                scene.add(mesh);
                enemies.push({
                  mesh,
                  hp: 2 + Math.floor(state.wave / 3),
                  maxHp: 2 + Math.floor(state.wave / 3),
                  speed: randomRange(0.85, 1.35) + state.wave * 0.05,
                  boss: false,
                  phase: randomRange(0, 10),
                });
              }
              hud.banner.textContent = "Wave " + state.wave;
            }

            function fireBullet(offset = 0, angle = 0) {
              const mesh = new THREE.Mesh(
                new THREE.SphereGeometry(0.11, 12, 8),
                new THREE.MeshBasicMaterial({ color: offset === 0 ? 0xffcf5a : 0x5fe5ff })
              );
              mesh.position.set(player.position.x + offset, player.position.y + 0.7, 1.2);
              scene.add(mesh);
              bullets.push({ mesh, vx: angle, vy: 8.8, damage: state.power >= 3 ? 2 : 1, life: 1.45 });
            }

            function shootPattern() {
              fireBullet(0, 0);
              if (state.power >= 1) {
                fireBullet(-0.32, -0.9);
                fireBullet(0.32, 0.9);
              }
              if (state.power >= 3) {
                fireBullet(-0.58, -1.5);
                fireBullet(0.58, 1.5);
              }
            }

            function spawnPowerup(x, y) {
              const mesh = new THREE.Mesh(
                new THREE.TorusGeometry(0.22, 0.08, 10, 24),
                new THREE.MeshBasicMaterial({ color: Math.random() > 0.5 ? 0x74f0a1 : 0xffcf5a })
              );
              mesh.position.set(x, y, 1.1);
              scene.add(mesh);
              powerups.push({ mesh, vy: -1.25, life: 7 });
            }

            function distance(a, b) {
              return Math.hypot(a.x - b.x, a.y - b.y);
            }

            function noteInput() {
              state.autopilot = false;
              state.mode = "MANUAL";
              lastInputAt = performance.now();
            }

            function updatePlayer(dt) {
              let vx = 0;
              let vy = 0;
              if (keys.has("ArrowLeft") || keys.has("KeyA")) vx -= 1;
              if (keys.has("ArrowRight") || keys.has("KeyD")) vx += 1;
              if (keys.has("ArrowUp") || keys.has("KeyW")) vy += 1;
              if (keys.has("ArrowDown") || keys.has("KeyS")) vy -= 1;

              if (vx || vy) {
                noteInput();
                const length = Math.hypot(vx, vy) || 1;
                player.position.x += (vx / length) * dt * 6.1;
                player.position.y += (vy / length) * dt * 5.4;
              } else if (pointerTarget) {
                noteInput();
                player.position.x += clamp(pointerTarget.x - player.position.x, -1, 1) * dt * 7;
                player.position.y += clamp(pointerTarget.y - player.position.y, -1, 1) * dt * 7;
              } else if (!state.autopilot && performance.now() - lastInputAt > 2200) {
                state.autopilot = true;
                state.mode = "AUTO";
              }

              if (state.autopilot) {
                const nearest = enemies.reduce((best, enemy) => {
                  const score = Math.abs(enemy.mesh.position.x - player.position.x) + Math.max(0, enemy.mesh.position.y - player.position.y) * 0.15;
                  return !best || score < best.score ? { enemy, score } : best;
                }, null);
                const targetX = nearest ? nearest.enemy.mesh.position.x : Math.sin(state.ageTicks * 0.035) * 4.5;
                const danger = enemies.find((enemy) => enemy.mesh.position.y < player.position.y + 2.3 && Math.abs(enemy.mesh.position.x - player.position.x) < 1.1);
                const dodge = danger ? (player.position.x > 0 ? -2.7 : 2.7) : 0;
                player.position.x += clamp(targetX + dodge - player.position.x, -1, 1) * dt * 4.8;
                player.position.y += clamp(-4.45 - player.position.y, -1, 1) * dt * 2;
              }

              player.position.x = clamp(player.position.x, -bounds.x, bounds.x);
              player.position.y = clamp(player.position.y, -bounds.y + 0.8, bounds.y - 1.2);
              player.rotation.z = clamp((player.position.x / bounds.x) * -0.25, -0.35, 0.35);
              flame.scale.y = 1.2 + Math.sin(state.ageTicks * 0.35) * 0.35;
            }

            function updateEnemies(dt) {
              for (let i = enemies.length - 1; i >= 0; i -= 1) {
                const enemy = enemies[i];
                enemy.phase += dt;
                enemy.mesh.rotation.z += dt * (enemy.boss ? 0.8 : 1.7);
                enemy.mesh.position.y -= enemy.speed * dt;
                enemy.mesh.position.x += Math.sin(enemy.phase * (enemy.boss ? 1.4 : 2.2)) * dt * (enemy.boss ? 1.2 : 1.8);

                if (distance(enemy.mesh.position, player.position) < (enemy.boss ? 1.2 : 0.7)) {
                  state.health = clamp(state.health - (enemy.boss ? 22 : 12), 0, 100);
                  scene.remove(enemy.mesh);
                  enemies.splice(i, 1);
                  continue;
                }

                if (enemy.mesh.position.y < -bounds.y - 1.2) {
                  state.health = clamp(state.health - (enemy.boss ? 16 : 5), 0, 100);
                  scene.remove(enemy.mesh);
                  enemies.splice(i, 1);
                }
              }
              state.bossActive = enemies.some((enemy) => enemy.boss);
            }

            function updateBullets(dt) {
              for (let i = bullets.length - 1; i >= 0; i -= 1) {
                const bullet = bullets[i];
                bullet.life -= dt;
                bullet.mesh.position.x += bullet.vx * dt;
                bullet.mesh.position.y += bullet.vy * dt;

                let spent = bullet.life <= 0 || bullet.mesh.position.y > bounds.y + 1.3;
                for (let j = enemies.length - 1; j >= 0 && !spent; j -= 1) {
                  const enemy = enemies[j];
                  if (distance(bullet.mesh.position, enemy.mesh.position) < (enemy.boss ? 0.95 : 0.45)) {
                    enemy.hp -= bullet.damage;
                    spent = true;
                    if (enemy.hp <= 0) {
                      state.score += enemy.boss ? 900 + state.wave * 75 : 120 + state.wave * 12;
                      state.enemiesDestroyed += 1;
                      if (Math.random() < (enemy.boss ? 0.9 : 0.18)) spawnPowerup(enemy.mesh.position.x, enemy.mesh.position.y);
                      scene.remove(enemy.mesh);
                      enemies.splice(j, 1);
                    }
                  }
                }

                if (spent) {
                  scene.remove(bullet.mesh);
                  bullets.splice(i, 1);
                }
              }
            }

            function updatePowerups(dt) {
              for (let i = powerups.length - 1; i >= 0; i -= 1) {
                const item = powerups[i];
                item.life -= dt;
                item.mesh.rotation.z += dt * 2.5;
                item.mesh.position.y += item.vy * dt;
                if (distance(item.mesh.position, player.position) < 0.78) {
                  state.power = clamp(state.power + 1, 0, 5);
                  state.health = clamp(state.health + 5, 0, 100);
                  state.score += 75;
                  scene.remove(item.mesh);
                  powerups.splice(i, 1);
                } else if (item.life <= 0 || item.mesh.position.y < -bounds.y - 1) {
                  scene.remove(item.mesh);
                  powerups.splice(i, 1);
                }
              }
            }

            function updateWave(dt) {
              spawnTimer -= dt;
              if (enemies.length === 0 && spawnTimer <= 0) {
                if (state.ageTicks > 20) state.wave += 1;
                spawnTimer = 2.1;
                spawnEnemyWave();
              }
            }

            function updateHUD() {
              hud.score.textContent = String(Math.floor(state.score));
              hud.wave.textContent = String(state.wave);
              hud.health.textContent = String(Math.ceil(state.health));
              hud.power.textContent = String(state.power);
              hud.mode.textContent = state.autopilot ? "AUTO" : "MANUAL";
              if (state.health <= 0) {
                hud.banner.textContent = "Hull rebuilt";
              } else if (state.bossActive) {
                hud.banner.textContent = "Boss active";
              }
            }

            function resetIfNeeded() {
              if (state.health > 0) return;
              state.score = Math.max(0, Math.floor(state.score * 0.45));
              state.wave = 1;
              state.health = 100;
              state.power = 0;
              for (const enemy of enemies.splice(0)) scene.remove(enemy.mesh);
              for (const bullet of bullets.splice(0)) scene.remove(bullet.mesh);
              for (const item of powerups.splice(0)) scene.remove(item.mesh);
              player.position.set(0, -4.7, 1);
              spawnTimer = 0;
            }

            function resize() {
              const width = Math.max(320, container.clientWidth);
              const height = Math.max(420, container.clientHeight);
              renderer.setSize(width, height, false);
              const aspect = width / height;
              camera.left = -8.2 * aspect;
              camera.right = 8.2 * aspect;
              camera.top = 7;
              camera.bottom = -7;
              camera.updateProjectionMatrix();
            }

            function screenToWorld(event) {
              const rect = renderer.domElement.getBoundingClientRect();
              const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
              const y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
              return {
                x: clamp(x * (camera.right - camera.left) / 2, -bounds.x, bounds.x),
                y: clamp(y * (camera.top - camera.bottom) / 2, -bounds.y, bounds.y),
              };
            }

            function animate() {
              const dt = Math.min(clock.getDelta(), 0.033);
              state.ageTicks += 1;
              stars.position.y -= dt * 0.38;
              if (stars.position.y < -1) stars.position.y = 0;
              fireCooldown -= dt;
              updateWave(dt);
              updatePlayer(dt);
              if ((state.autopilot || keys.has("Space")) && fireCooldown <= 0) {
                shootPattern();
                fireCooldown = state.power >= 2 ? 0.14 : 0.22;
              }
              updateEnemies(dt);
              updateBullets(dt);
              updatePowerups(dt);
              resetIfNeeded();
              updateHUD();
              renderer.render(scene, camera);
              requestAnimationFrame(animate);
            }

            window.addEventListener("resize", resize);
            window.addEventListener("keydown", (event) => {
              keys.add(event.code);
              if (event.code === "Space") event.preventDefault();
              noteInput();
            });
            window.addEventListener("keyup", (event) => {
              keys.delete(event.code);
            });
            renderer.domElement.addEventListener("pointerdown", (event) => {
              renderer.domElement.setPointerCapture(event.pointerId);
              pointerTarget = screenToWorld(event);
              noteInput();
            });
            renderer.domElement.addEventListener("pointermove", (event) => {
              if (event.buttons || event.pointerType === "touch") pointerTarget = screenToWorld(event);
            });
            renderer.domElement.addEventListener("pointerup", () => {
              pointerTarget = null;
              lastInputAt = performance.now();
            });

            window.NovaSkyShooter = {
              getState() {
                return {
                  score: state.score,
                  wave: state.wave,
                  health: state.health,
                  power: state.power,
                  ageTicks: state.ageTicks,
                  autopilot: state.autopilot,
                  enemies: enemies.length,
                  bullets: bullets.length,
                  powerups: powerups.length,
                  bossActive: state.bossActive,
                  renderer: renderer.domElement.dataset.engine,
                };
              },
            };

            resize();
            spawnEnemyWave();
            animate();
          </script>
        </body>
        </html>
        """
    ).strip() + "\n"


def _game_html() -> str:
    return dedent(
        r"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <link rel="icon" href="data:," />
          <title>Nova Pac Runner</title>
          <style>
            :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
            *, *::before, *::after { box-sizing: border-box; }
            body {
              margin: 0;
              min-height: 100vh;
              padding: 12px;
              display: grid;
              place-items: center;
              background: radial-gradient(circle at top, #172047 0, #070912 56%, #02030a 100%);
              color: #f7f7ff;
            }
            .shell {
              width: min(calc(100vw - 24px), 760px);
              max-height: calc(100vh - 24px);
              overflow: auto;
              border: 1px solid #263174;
              border-radius: 22px;
              padding: 18px;
              background: rgba(7, 10, 28, 0.9);
              box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
            }
            h1 { margin: 0 0 8px; font-size: clamp(24px, 5vw, 38px); }
            p { margin: 0 0 14px; color: #bfc7ff; }
            .hud { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
            .stat { border: 1px solid #303c90; border-radius: 12px; padding: 10px; background: #101743; }
            .stat span { display: block; color: #8fa0ff; font-size: 12px; text-transform: uppercase; }
            .stat strong { font-size: 22px; }
            #game {
              position: relative;
              width: min(100%, 58vh);
              aspect-ratio: 19 / 21;
              margin: 0 auto;
              overflow: hidden;
              border: 2px solid #3146d9;
              border-radius: 16px;
              background: #050817;
            }
            #game canvas {
              display: block;
              width: 100%;
              height: 100%;
            }
            .notes { margin-top: 12px; font-size: 14px; color: #cbd1ff; }
            kbd { background: #20295f; border-radius: 6px; padding: 2px 6px; border: 1px solid #3d4bb0; }
            @media (max-width: 520px) {
              body { padding: 8px; align-items: start; }
              .shell { width: min(calc(100vw - 16px), 760px); padding: 12px; border-radius: 16px; }
              h1 { font-size: 28px; }
              .hud { grid-template-columns: repeat(2, minmax(0, 1fr)); }
              #game { width: min(100%, 52vh); }
            }
          </style>
        </head>
        <body>
          <main class="shell">
            <h1>Nova Pac Runner</h1>
            <p>Autopilot is on. The runner uses a Three.js/WebGL scene, moves on its own, chases pellets, avoids ghosts, and keeps score.</p>
            <section class="hud" aria-label="Game stats">
              <div class="stat"><span>Score</span><strong id="score">0</strong></div>
              <div class="stat"><span>Pellets</span><strong id="pellets">0</strong></div>
              <div class="stat"><span>Age</span><strong id="age">0</strong></div>
              <div class="stat"><span>Smart</span><strong id="smart">0</strong></div>
            </section>
            <section id="game" data-renderer="three-webgl" aria-label="Nova Pac Runner Three.js playfield"></section>
            <p class="notes">Use <kbd>Arrow Keys</kbd> to take over. Stop pressing keys and Nova autopilot resumes.</p>
          </main>
          <script type="module">
            import * as THREE from "https://unpkg.com/three@0.165.0/build/three.module.js";

            const gameHost = document.getElementById("game");
            const boardTileSize = 1;
            const maze = [
              "###################",
              "#........#........#",
              "#.###.##.#.##.###.#",
              "#.................#",
              "#.###.#.###.#.###.#",
              "#.....#..#..#.....#",
              "#####.## # ##.#####",
              "    #.#     #.#    ",
              "#####.# ##  #.#####",
              "#.........G.......#",
              "#####.#  ## #.#####",
              "    #.#     #.#    ",
              "#####.#.###.#.#####",
              "#........#........#",
              "#.###.##.#.##.###.#",
              "#...#.........#...#",
              "###.#.#.###.#.#.###",
              "#.....#..#..#.....#",
              "#.#######.#######.#",
              "#........P........#",
              "###################"
            ];

            const boardWidth = maze[0].length;
            const boardHeight = maze.length;
            const dirs = [
              { x: 1, y: 0, name: "right" },
              { x: -1, y: 0, name: "left" },
              { x: 0, y: 1, name: "down" },
              { x: 0, y: -1, name: "up" }
            ];
            const state = {
              pac: { x: 9, y: 19, dir: { x: 1, y: 0, name: "right" } },
              ghosts: [{ x: 9, y: 9, dir: { x: 1, y: 0, name: "right" } }],
              pellets: new Set(),
              score: 0,
              ageTicks: 0,
              smartScore: 0,
              autopilot: true,
              running: true,
              lastManualAt: 0
            };

            for (let y = 0; y < maze.length; y++) {
              for (let x = 0; x < maze[y].length; x++) {
                if (maze[y][x] === ".") state.pellets.add(`${x},${y}`);
              }
            }

            const scene = new THREE.Scene();
            scene.background = new THREE.Color("#050817");

            const camera = new THREE.OrthographicCamera(
              -boardWidth / 2,
              boardWidth / 2,
              boardHeight / 2,
              -boardHeight / 2,
              0.1,
              100
            );
            camera.position.set(0, 0, 30);
            camera.lookAt(0, 0, 0);

            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            renderer.setClearColor(0x050817, 1);
            renderer.outputColorSpace = THREE.SRGBColorSpace;
            renderer.domElement.dataset.engine = "three-webgl";
            renderer.domElement.dataset.threeRevision = THREE.REVISION;
            renderer.domElement.setAttribute("aria-label", "Three.js WebGL Pac Runner scene");
            gameHost.appendChild(renderer.domElement);

            document.body.dataset.renderer = "three-webgl";
            document.body.dataset.threeRevision = THREE.REVISION;

            scene.add(new THREE.AmbientLight(0x93a5ff, 0.62));
            const keyLight = new THREE.DirectionalLight(0xffffff, 1.3);
            keyLight.position.set(3, 5, 8);
            scene.add(keyLight);
            const rimLight = new THREE.DirectionalLight(0x47f6ff, 0.5);
            rimLight.position.set(-4, -3, 6);
            scene.add(rimLight);

            const floor = new THREE.Mesh(
              new THREE.PlaneGeometry(boardWidth, boardHeight),
              new THREE.MeshBasicMaterial({ color: "#060a1e" })
            );
            floor.position.set(0, 0, -0.16);
            scene.add(floor);

            const wallGeometry = new THREE.BoxGeometry(0.96, 0.96, 0.28);
            const pelletGeometry = new THREE.SphereGeometry(0.105, 12, 8);
            const pacGeometry = new THREE.SphereGeometry(0.38, 32, 16);
            const ghostGeometry = new THREE.SphereGeometry(0.4, 24, 14);
            const ghostBaseGeometry = new THREE.BoxGeometry(0.68, 0.22, 0.26);
            const wallMaterial = new THREE.MeshStandardMaterial({ color: "#2148ff", emissive: "#071a8d", roughness: 0.44 });
            const pelletMaterial = new THREE.MeshStandardMaterial({ color: "#f7d66b", emissive: "#4b3000", roughness: 0.25 });
            const pacMaterial = new THREE.MeshStandardMaterial({ color: "#ffeb3b", emissive: "#8a7100", roughness: 0.28 });
            const ghostMaterial = new THREE.MeshStandardMaterial({ color: "#ff4b6e", emissive: "#771128", roughness: 0.36 });

            const boardGroup = new THREE.Group();
            const pelletMeshes = new Map();
            scene.add(boardGroup);

            function worldPosition(x, y, z = 0) {
              return {
                x: (x - boardWidth / 2 + 0.5) * boardTileSize,
                y: (boardHeight / 2 - y - 0.5) * boardTileSize,
                z
              };
            }

            function placeAtTile(object, x, y, z = 0) {
              const pos = worldPosition(x, y, z);
              object.position.set(pos.x, pos.y, pos.z);
            }

            for (let y = 0; y < maze.length; y++) {
              for (let x = 0; x < maze[y].length; x++) {
                if (maze[y][x] === "#") {
                  const wall = new THREE.Mesh(wallGeometry, wallMaterial);
                  placeAtTile(wall, x, y, 0.02);
                  boardGroup.add(wall);
                } else if (state.pellets.has(`${x},${y}`)) {
                  const pellet = new THREE.Mesh(pelletGeometry, pelletMaterial);
                  placeAtTile(pellet, x, y, 0.24);
                  pelletMeshes.set(`${x},${y}`, pellet);
                  boardGroup.add(pellet);
                }
              }
            }

            const pacMesh = new THREE.Mesh(pacGeometry, pacMaterial);
            scene.add(pacMesh);

            function createGhostMesh() {
              const ghost = new THREE.Group();
              const head = new THREE.Mesh(ghostGeometry, ghostMaterial);
              const base = new THREE.Mesh(ghostBaseGeometry, ghostMaterial);
              base.position.set(0, -0.27, -0.02);
              ghost.add(head, base);
              scene.add(ghost);
              return ghost;
            }

            const ghostMeshes = state.ghosts.map(createGhostMesh);

            function isWall(x, y) {
              return y < 0 || y >= maze.length || x < 0 || x >= maze[y].length || maze[y][x] === "#";
            }

            function neighbors(pos) {
              return dirs.map(dir => ({ x: pos.x + dir.x, y: pos.y + dir.y, dir })).filter(next => !isWall(next.x, next.y));
            }

            function nearestPelletDistance(x, y) {
              let best = Infinity;
              for (const key of state.pellets) {
                const [px, py] = key.split(",").map(Number);
                best = Math.min(best, Math.abs(px - x) + Math.abs(py - y));
              }
              return best;
            }

            function ghostDanger(x, y) {
              return state.ghosts.reduce((danger, ghost) => {
                const d = Math.abs(ghost.x - x) + Math.abs(ghost.y - y);
                return danger + (d <= 1 ? 60 : d <= 3 ? 15 : 0);
              }, 0);
            }

            function chooseAutoDirection() {
              const choices = neighbors(state.pac);
              choices.sort((a, b) => {
                const scoreA = nearestPelletDistance(a.x, a.y) + ghostDanger(a.x, a.y);
                const scoreB = nearestPelletDistance(b.x, b.y) + ghostDanger(b.x, b.y);
                return scoreA - scoreB;
              });
              return choices[0]?.dir || state.pac.dir;
            }

            function moveEntity(entity, dir) {
              const nx = entity.x + dir.x;
              const ny = entity.y + dir.y;
              if (!isWall(nx, ny)) {
                entity.x = nx;
                entity.y = ny;
                entity.dir = dir;
              }
            }

            function moveGhosts() {
              for (const ghost of state.ghosts) {
                const choices = neighbors(ghost);
                choices.sort((a, b) => {
                  const da = Math.abs(a.x - state.pac.x) + Math.abs(a.y - state.pac.y);
                  const db = Math.abs(b.x - state.pac.x) + Math.abs(b.y - state.pac.y);
                  return da - db;
                });
                moveEntity(ghost, choices[0]?.dir || ghost.dir);
              }
            }

            function eatPellet() {
              const key = `${state.pac.x},${state.pac.y}`;
              if (state.pellets.delete(key)) {
                state.score += 10;
                const pellet = pelletMeshes.get(key);
                if (pellet) {
                  boardGroup.remove(pellet);
                  pelletMeshes.delete(key);
                }
              }
            }

            function resetIfCaught() {
              if (state.ghosts.some(g => g.x === state.pac.x && g.y === state.pac.y)) {
                state.score = Math.max(0, state.score - 25);
                state.pac.x = 9;
                state.pac.y = 19;
              }
            }

            function updateHud() {
              document.body.dataset.pacX = String(state.pac.x);
              document.body.dataset.pacY = String(state.pac.y);
              document.body.dataset.autopilot = String(state.autopilot);
              document.getElementById("score").textContent = String(state.score);
              document.getElementById("pellets").textContent = String(state.pellets.size);
              document.getElementById("age").textContent = String(state.ageTicks);
              document.getElementById("smart").textContent = String(state.smartScore);
            }

            function directionAngle(dir) {
              if (dir.name === "left") return Math.PI;
              if (dir.name === "up") return Math.PI / 2;
              if (dir.name === "down") return -Math.PI / 2;
              return 0;
            }

            function syncScene() {
              placeAtTile(pacMesh, state.pac.x, state.pac.y, 0.38);
              pacMesh.rotation.z = directionAngle(state.pac.dir);
              state.ghosts.forEach((ghost, index) => {
                placeAtTile(ghostMeshes[index], ghost.x, ghost.y, 0.38);
              });
            }

            function tick() {
              if (!state.running) return;
              state.ageTicks += 1;
              if (Date.now() - state.lastManualAt > 1400) {
                state.autopilot = true;
                state.pac.dir = chooseAutoDirection();
              }
              moveEntity(state.pac, state.pac.dir);
              eatPellet();
              if (state.ageTicks % 2 === 0) moveGhosts();
              resetIfCaught();
              if (state.pellets.size === 0) state.running = false;
              state.smartScore = Math.min(100, Math.round((state.score / 6) + state.ageTicks / 8));
              syncScene();
              updateHud();
            }

            function resizeRenderer() {
              const bounds = gameHost.getBoundingClientRect();
              const width = Math.max(320, Math.floor(bounds.width));
              const height = Math.max(320, Math.floor(bounds.height || width * boardHeight / boardWidth));
              renderer.setSize(width, height, false);
            }

            function animateScene() {
              const pulse = 1 + Math.sin(performance.now() / 80) * 0.045;
              pacMesh.scale.set(pulse, pulse, pulse);
              ghostMeshes.forEach((ghost, index) => {
                ghost.position.z = 0.38 + Math.sin(performance.now() / 190 + index) * 0.035;
              });
              renderer.render(scene, camera);
              requestAnimationFrame(animateScene);
            }

            const keyMap = { ArrowRight: dirs[0], ArrowLeft: dirs[1], ArrowDown: dirs[2], ArrowUp: dirs[3] };
            addEventListener("keydown", event => {
              if (keyMap[event.key]) {
                state.pac.dir = keyMap[event.key];
                state.autopilot = false;
                state.lastManualAt = Date.now();
                event.preventDefault();
              }
            });

            renderer.domElement.addEventListener("webglcontextlost", event => {
              event.preventDefault();
              state.running = false;
              updateHud();
            });

            addEventListener("resize", resizeRenderer);

            window.NovaPacGame = {
              renderer: "three-webgl",
              getState() {
                return {
                  pac: { ...state.pac },
                  score: state.score,
                  ageTicks: state.ageTicks,
                  smartScore: state.smartScore,
                  pelletsRemaining: state.pellets.size,
                  autopilot: state.autopilot,
                  running: state.running,
                  renderer: "three-webgl"
                };
              },
              forceTick: tick,
              isRunning() { return state.running; }
            };

            resizeRenderer();
            syncScene();
            updateHud();
            setInterval(tick, 130);
            requestAnimationFrame(animateScene);
          </script>
        </body>
        </html>
        """
    ).strip() + "\n"


def _temple_run_html() -> str:
    return dedent(
        r"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>Nova Temple Runner</title>
          <style>
            :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
            body {
              margin: 0;
              min-height: 100vh;
              overflow: hidden;
              background: radial-gradient(circle at top, #26366f 0, #090b17 56%, #02030a 100%);
              color: #f7f7ff;
            }
            #game {
              position: fixed;
              inset: 0;
              width: 100vw;
              height: 100vh;
              background: #070914;
            }
            #game canvas { display: block; width: 100%; height: 100%; }
            .hud {
              position: fixed;
              top: 16px;
              left: 16px;
              right: 16px;
              z-index: 2;
              display: flex;
              gap: 10px;
              flex-wrap: wrap;
              pointer-events: none;
            }
            .chip {
              min-width: 94px;
              border: 1px solid rgba(139, 154, 255, 0.42);
              border-radius: 14px;
              padding: 9px 12px;
              background: rgba(7, 10, 30, 0.76);
              box-shadow: 0 12px 40px rgba(0, 0, 0, 0.26);
              backdrop-filter: blur(10px);
            }
            .chip span {
              display: block;
              color: #9eabff;
              font-size: 11px;
              letter-spacing: 0.08em;
              text-transform: uppercase;
            }
            .chip strong { display: block; font-size: 22px; }
            .hint {
              position: fixed;
              left: 16px;
              bottom: 16px;
              z-index: 2;
              max-width: min(620px, calc(100vw - 32px));
              border: 1px solid rgba(139, 154, 255, 0.32);
              border-radius: 16px;
              padding: 12px 14px;
              background: rgba(7, 10, 30, 0.66);
              color: #cad2ff;
              font-size: 14px;
              pointer-events: none;
            }
            kbd { background: #20295f; border-radius: 6px; padding: 2px 6px; border: 1px solid #3d4bb0; }
          </style>
        </head>
        <body data-renderer="three-webgl">
          <section class="hud" aria-label="Runner stats">
            <div class="chip"><span>Score</span><strong id="score">0</strong></div>
            <div class="chip"><span>Distance</span><strong id="distance">0</strong></div>
            <div class="chip"><span>Coins</span><strong id="coins">0</strong></div>
            <div class="chip"><span>Level</span><strong id="level">1</strong></div>
            <div class="chip"><span>Stage</span><strong id="levelName">Dawn Gate</strong></div>
            <div class="chip"><span>Age</span><strong id="age">0</strong></div>
            <div class="chip"><span>Mode</span><strong id="mode">AUTO</strong></div>
          </section>
          <section id="game" data-renderer="three-webgl" aria-label="Nova Temple Runner Three.js playfield"></section>
          <p class="hint">Nova autopilot runs by itself. Use <kbd>←</kbd>/<kbd>→</kbd> to change lanes, <kbd>Space</kbd> to jump, <kbd>↓</kbd> to slide. Stop pressing keys and autopilot resumes.</p>
          <script type="module">
            import * as THREE from "https://unpkg.com/three@0.165.0/build/three.module.js";

            const host = document.getElementById("game");
            const lanes = [-2.8, 0, 2.8];
            const LEVELS = [
              { name: "Dawn Gate", goal: 0, maxSpeed: 0.58, acceleration: 0.00072, obstacleEvery: 12, obstacleJitter: 7, coinEvery: 12, fogFar: 58, roadColor: "#47321d" },
              { name: "Sunken Steps", goal: 180, maxSpeed: 0.64, acceleration: 0.00082, obstacleEvery: 10, obstacleJitter: 6, coinEvery: 11, fogFar: 52, roadColor: "#4c3b29" },
              { name: "Moonlit Bridge", goal: 380, maxSpeed: 0.70, acceleration: 0.00092, obstacleEvery: 8.8, obstacleJitter: 5, coinEvery: 10, fogFar: 48, roadColor: "#374057" },
              { name: "Storm Vault", goal: 650, maxSpeed: 0.78, acceleration: 0.00102, obstacleEvery: 7.6, obstacleJitter: 4.5, coinEvery: 9, fogFar: 44, roadColor: "#53323a" },
              { name: "Solar Crown", goal: 1000, maxSpeed: 0.86, acceleration: 0.00112, obstacleEvery: 6.6, obstacleJitter: 4, coinEvery: 8, fogFar: 40, roadColor: "#5d4826" }
            ];
            const state = {
              lane: 1,
              targetLane: 1,
              y: 0,
              yVelocity: 0,
              sliding: false,
              slideTicks: 0,
              score: 0,
              distance: 0,
              coins: 0,
              levelIndex: 0,
              level: 1,
              levelName: LEVELS[0].name,
              levelGoal: LEVELS[1].goal,
              ageTicks: 0,
              speed: 0.38,
              autopilot: true,
              running: true,
              lastManualAt: 0,
              obstacles: [],
              coinsList: [],
              nextObstacleAt: 12,
              nextCoinAt: 7
            };

            const scene = new THREE.Scene();
            scene.background = new THREE.Color("#090b17");
            scene.fog = new THREE.Fog("#090b17", 18, 58);

            const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 160);
            camera.position.set(0, 6.2, 10.5);
            camera.lookAt(0, 1.2, -12);

            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            renderer.outputColorSpace = THREE.SRGBColorSpace;
            renderer.domElement.dataset.engine = "three-webgl";
            renderer.domElement.dataset.threeRevision = THREE.REVISION;
            host.appendChild(renderer.domElement);

            scene.add(new THREE.HemisphereLight(0x9db5ff, 0x120815, 1.2));
            const sun = new THREE.DirectionalLight(0xfff0ce, 1.8);
            sun.position.set(-5, 10, 4);
            scene.add(sun);

            const roadMaterial = new THREE.MeshStandardMaterial({ color: LEVELS[0].roadColor, roughness: 0.88 });
            const road = new THREE.Mesh(new THREE.BoxGeometry(9.4, 0.26, 180), roadMaterial);
            road.position.set(0, -0.14, -54);
            scene.add(road);

            const laneMaterial = new THREE.MeshBasicMaterial({ color: "#d8b36b", transparent: true, opacity: 0.45 });
            for (const x of [-1.4, 1.4]) {
              const line = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.03, 180), laneMaterial);
              line.position.set(x, 0.04, -54);
              scene.add(line);
            }

            const templeMaterial = new THREE.MeshStandardMaterial({ color: "#786247", roughness: 0.7 });
            for (let i = 0; i < 18; i++) {
              for (const side of [-1, 1]) {
                const pillar = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.42, 4, 12), templeMaterial);
                pillar.position.set(side * 5.6, 1.8, -i * 10 - 5);
                scene.add(pillar);
              }
            }

            const runner = new THREE.Group();
            const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.45, 1.0, 6, 12), new THREE.MeshStandardMaterial({ color: "#5efcff", emissive: "#064b5b", roughness: 0.32 }));
            const face = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.42, 0.08), new THREE.MeshStandardMaterial({ color: "#0c1028", emissive: "#00e5ff", roughness: 0.15 }));
            face.position.set(0, 0.42, 0.37);
            runner.add(body, face);
            scene.add(runner);

            const obstacleMaterial = new THREE.MeshStandardMaterial({ color: "#ff475e", emissive: "#4a0710", roughness: 0.45 });
            const coinMaterial = new THREE.MeshStandardMaterial({ color: "#ffd65a", emissive: "#7c5300", roughness: 0.22 });

            function currentLevel() {
              return LEVELS[state.levelIndex];
            }

            function updateLevel() {
              while (state.levelIndex < LEVELS.length - 1 && state.distance >= LEVELS[state.levelIndex + 1].goal) {
                state.levelIndex += 1;
                const level = currentLevel();
                state.level = state.levelIndex + 1;
                state.levelName = level.name;
                state.levelGoal = LEVELS[state.levelIndex + 1]?.goal || level.goal;
                scene.fog.far = level.fogFar;
                roadMaterial.color.set(level.roadColor);
                state.score += 100;
              }
            }

            function spawnObstacle() {
              const lane = Math.floor(Math.random() * lanes.length);
              const obstacle = new THREE.Mesh(new THREE.BoxGeometry(1.28, 1.4, 1.0), obstacleMaterial);
              obstacle.position.set(lanes[lane], 0.7, -62);
              scene.add(obstacle);
              state.obstacles.push({ lane, z: -62, mesh: obstacle, type: "obstacle" });
            }

            function spawnCoinRow() {
              const lane = Math.floor(Math.random() * lanes.length);
              for (let i = 0; i < 4; i++) {
                const coin = new THREE.Mesh(new THREE.TorusGeometry(0.28, 0.08, 10, 18), coinMaterial);
                coin.position.set(lanes[lane], 1.05, -48 - i * 2.1);
                coin.rotation.x = Math.PI / 2;
                scene.add(coin);
                state.coinsList.push({ lane, z: -48 - i * 2.1, mesh: coin, type: "coin" });
              }
            }

            function nearestThreat() {
              return state.obstacles
                .filter(item => item.z > -18 && item.z < -4)
                .sort((a, b) => b.z - a.z)[0];
            }

            function chooseAutoLane() {
              const threat = nearestThreat();
              if (!threat || threat.lane !== state.targetLane) return;
              const options = [0, 1, 2].filter(lane => lane !== threat.lane);
              options.sort((a, b) => Math.abs(a - state.targetLane) - Math.abs(b - state.targetLane));
              state.targetLane = options[0];
            }

            function moveLane(delta) {
              state.targetLane = Math.max(0, Math.min(lanes.length - 1, state.targetLane + delta));
            }

            function laneX(index) {
              const lower = Math.floor(index);
              const upper = Math.ceil(index);
              const blend = index - lower;
              return THREE.MathUtils.lerp(lanes[lower], lanes[upper], blend);
            }

            function jump() {
              if (state.y <= 0.02) state.yVelocity = 0.34;
            }

            function slide() {
              state.sliding = true;
              state.slideTicks = 18;
            }

            function resetRunner() {
              state.score = Math.max(0, state.score - 75);
              state.distance = Math.max(0, state.distance - 20);
              state.targetLane = 1;
              state.lane = 1;
              state.y = 0;
              state.yVelocity = 0;
              state.obstacles.forEach(item => scene.remove(item.mesh));
              state.coinsList.forEach(item => scene.remove(item.mesh));
              state.obstacles = [];
              state.coinsList = [];
              state.nextObstacleAt = state.distance + 16;
              state.nextCoinAt = state.distance + 7;
            }

            function tick() {
              if (!state.running) return;
              state.ageTicks += 1;
              state.distance += state.speed;
              state.score += 1;
              updateLevel();
              const level = currentLevel();
              state.speed = Math.min(level.maxSpeed, state.speed + level.acceleration);

              if (Date.now() - state.lastManualAt > 1200) {
                state.autopilot = true;
                chooseAutoLane();
              }

              state.yVelocity -= 0.026;
              state.y = Math.max(0, state.y + state.yVelocity);
              if (state.y === 0 && state.yVelocity < 0) state.yVelocity = 0;
              if (state.slideTicks > 0) state.slideTicks -= 1;
              else state.sliding = false;

              if (state.distance > state.nextObstacleAt) {
                spawnObstacle();
                state.nextObstacleAt += level.obstacleEvery + Math.random() * level.obstacleJitter;
              }
              if (state.distance > state.nextCoinAt) {
                spawnCoinRow();
                state.nextCoinAt += level.coinEvery + Math.random() * 7;
              }

              for (const item of [...state.obstacles]) {
                item.z += state.speed;
                item.mesh.position.z = item.z;
                item.mesh.rotation.y += 0.015;
                if (item.z > 5) {
                  scene.remove(item.mesh);
                  state.obstacles.splice(state.obstacles.indexOf(item), 1);
                  continue;
                }
                if (item.lane === Math.round(state.lane) && item.z > -1.2 && item.z < 0.8 && state.y < 0.6 && !state.sliding) {
                  resetRunner();
                  break;
                }
              }

              for (const item of [...state.coinsList]) {
                item.z += state.speed;
                item.mesh.position.z = item.z;
                item.mesh.rotation.z += 0.12;
                if (item.z > 5) {
                  scene.remove(item.mesh);
                  state.coinsList.splice(state.coinsList.indexOf(item), 1);
                  continue;
                }
                if (item.lane === Math.round(state.lane) && item.z > -1 && item.z < 1 && state.y < 1.3) {
                  state.coins += 1;
                  state.score += 25;
                  scene.remove(item.mesh);
                  state.coinsList.splice(state.coinsList.indexOf(item), 1);
                }
              }

              state.lane += (state.targetLane - state.lane) * 0.22;
              runner.position.set(laneX(state.lane), 0.95 + state.y, 0);
              runner.scale.y = state.sliding ? 0.58 : 1;
              runner.rotation.z = (state.targetLane - state.lane) * -0.16;
              updateHud();
            }

            function updateHud() {
              document.body.dataset.runnerLane = String(Math.round(state.lane));
              document.body.dataset.autopilot = String(state.autopilot);
              document.body.dataset.ageTicks = String(state.ageTicks);
              document.getElementById("score").textContent = String(Math.floor(state.score));
              document.getElementById("distance").textContent = String(Math.floor(state.distance));
              document.getElementById("coins").textContent = String(state.coins);
              document.getElementById("level").textContent = String(state.level);
              document.getElementById("levelName").textContent = state.levelName;
              document.getElementById("age").textContent = String(state.ageTicks);
              document.getElementById("mode").textContent = state.autopilot ? "AUTO" : "YOU";
            }

            function resize() {
              const width = Math.max(320, window.innerWidth);
              const height = Math.max(320, window.innerHeight);
              camera.aspect = width / height;
              camera.updateProjectionMatrix();
              renderer.setSize(width, height, false);
            }

            function animate() {
              road.position.z = -54 + (state.distance % 8);
              for (let i = 0; i < scene.children.length; i++) {
                const object = scene.children[i];
                if (object.geometry && object.geometry.type === "CylinderGeometry") {
                  object.position.z += state.speed * 0.16;
                  if (object.position.z > 10) object.position.z -= 180;
                }
              }
              renderer.render(scene, camera);
              requestAnimationFrame(animate);
            }

            const keyActions = {
              ArrowLeft: () => moveLane(-1),
              ArrowRight: () => moveLane(1),
              ArrowDown: slide,
              " ": jump,
              Spacebar: jump
            };
            addEventListener("keydown", event => {
              const action = keyActions[event.key];
              if (action) {
                state.autopilot = false;
                state.lastManualAt = Date.now();
                action();
                event.preventDefault();
              }
            });

            addEventListener("resize", resize);
            renderer.domElement.addEventListener("webglcontextlost", event => {
              event.preventDefault();
              state.running = false;
              updateHud();
            });

            window.NovaTempleRunner = {
              renderer: "three-webgl",
              getState() {
                return {
                  lane: Math.round(state.lane),
                  targetLane: state.targetLane,
                  score: Math.floor(state.score),
                  distance: Math.floor(state.distance),
                  coins: state.coins,
                  level: state.level,
                  levelName: state.levelName,
                  levelGoal: state.levelGoal,
                  ageTicks: state.ageTicks,
                  autopilot: state.autopilot,
                  obstacles: state.obstacles.length,
                  coinsVisible: state.coinsList.length,
                  running: state.running,
                  renderer: "three-webgl"
                };
              },
              forceTick: tick,
              moveLane,
              jump,
              slide
            };

            spawnCoinRow();
            resize();
            updateHud();
            setInterval(tick, 70);
            requestAnimationFrame(animate);
          </script>
        </body>
        </html>
        """
    ).strip() + "\n"
