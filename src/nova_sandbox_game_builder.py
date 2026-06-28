from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


PROJECT_SLUG = "Nova_Pac_Runner"
PROJECT_NAME = "Nova Pac Runner"
STEM_PROJECT_SLUG = "Nova_Stem_Player"
STEM_PROJECT_NAME = "Nova Stem Player"
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


def is_stem_music_player_request(text: str) -> bool:
    normalized = _normalize(text)
    has_build_verb = re.search(r"\b(?:make|create|build|generate)\b", normalized) is not None
    names_music_player = re.search(
        r"\b(?:music\s+player|audio\s+player|dj\s+player|stem\s+mixer|audio\s+workstation|music\s+app)\b",
        normalized,
    ) is not None
    asks_for_stems = re.search(
        r"\b(?:stem|stems|vocals?|drums?|bass|melody|instrumental|separat(?:e|ion)|mixer)\b",
        normalized,
    ) is not None
    asks_question = normalized.startswith(("what ", "why ", "when ", "where ", "who ", "how "))
    names_game = re.search(r"\b(?:game|pac[\s-]?man|temple\s+run|runner)\b", normalized) is not None
    return has_build_verb and names_music_player and asks_for_stems and not asks_question and not names_game


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


def build_stem_music_player(projects_root: str | Path | None = None) -> GameBuildResult:
    root = Path(projects_root) if projects_root is not None else _default_projects_root()
    project_dir = root / STEM_PROJECT_SLUG
    project_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "index.html": _stem_index_html(),
        "package.json": _stem_package_json(),
        "tsconfig.json": _stem_tsconfig_json(),
        "tsconfig.node.json": _stem_tsconfig_node_json(),
        "vite.config.ts": _stem_vite_config(),
        "src/main.tsx": _stem_main_tsx(),
        "src/App.tsx": _stem_app_tsx(),
        "src/App.test.tsx": _stem_app_test_tsx(),
        "src/vite-env.d.ts": _stem_vite_env_d_ts(),
        "src/styles.css": _stem_styles_css(),
        "src/audio/stemEngine.ts": _stem_engine_ts(),
        "src/data/demoLibrary.ts": _stem_demo_library_ts(),
        "README.md": _stem_readme(),
        "manifest.json": json.dumps(
            {
                "name": STEM_PROJECT_NAME,
                "kind": "react_audio_workstation",
                "entry": "index.html",
                "engine": "React + Vite",
                "audio": "Web Audio API",
                "stem_controls": ["vocals", "drums", "bass", "other"],
                "true_stem_mode": True,
                "single_file_mode": "simulated stem shaping",
                "safe_sandbox": True,
            },
            indent=2,
        )
        + "\n",
        "test_spec.json": json.dumps(
            {
                "checks": [
                    "renders Nova Stem Player workstation",
                    "supports drag and drop local audio loading",
                    "shows vocals drums bass and other stem controls",
                    "uses Web Audio API helper with BiquadFilterNode",
                    "labels true stem mode and simulated stem shaping honestly",
                    "includes Vite build and Vitest test scripts",
                    "exposes media key metadata through MediaSession when available",
                ]
            },
            indent=2,
        )
        + "\n",
    }

    written: list[Path] = []
    for name, content in files.items():
        path = project_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return GameBuildResult(
        project_name=STEM_PROJECT_NAME,
        project_dir=project_dir,
        entry_file=project_dir / "index.html",
        url_path=f"{SANDBOX_URL_PREFIX}/{STEM_PROJECT_SLUG}/index.html",
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


def _stem_readme() -> str:
    return dedent(
        f"""
        # {STEM_PROJECT_NAME}

        A React + Vite local music-player workstation generated by Nova.

        ## Run

        ```powershell
        npm.cmd install
        npm.cmd run dev -- --host 127.0.0.1
        ```

        ## Features

        - Drag and drop local audio files.
        - Play, pause, seek, volume, speed, pitch, and loop controls.
        - Vocals, drums, bass, and other stem mixer lanes.
        - Mute, solo, gain, pan, and meter-style UI per stem.
        - True stem mode when separate stem files are loaded.
        - Simulated stem shaping when only one mixed file is loaded.
        - Web Audio API helper with gain, EQ, analyzer, and Media Session hooks.
        """
    ).strip() + "\n"


def _stem_package_json() -> str:
    return json.dumps(
        {
            "name": "nova-stem-player",
            "private": True,
            "version": "1.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build",
                "test": "vitest",
                "preview": "vite preview --host 127.0.0.1",
            },
            "dependencies": {
                "@vitejs/plugin-react": "^6.0.3",
                "lucide-react": "^1.21.0",
                "react": "^19.2.7",
                "react-dom": "^19.2.7",
                "vite": "^8.1.0",
            },
            "devDependencies": {
                "@testing-library/jest-dom": "^6.6.3",
                "@testing-library/react": "^16.1.0",
                "@testing-library/user-event": "^14.5.2",
                "@types/react": "^19.2.17",
                "@types/react-dom": "^19.2.3",
                "jsdom": "^29.1.1",
                "typescript": "^6.0.3",
                "vitest": "^4.1.9",
            },
        },
        indent=2,
    ) + "\n"


def _stem_tsconfig_json() -> str:
    return dedent(
        """
        {
          "compilerOptions": {
            "target": "ES2020",
            "useDefineForClassFields": true,
            "lib": ["DOM", "DOM.Iterable", "ES2020"],
            "allowJs": false,
            "skipLibCheck": true,
            "esModuleInterop": true,
            "allowSyntheticDefaultImports": true,
            "strict": true,
            "forceConsistentCasingInFileNames": true,
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "resolveJsonModule": true,
            "isolatedModules": true,
            "noEmit": true,
            "jsx": "react-jsx"
          },
          "include": ["src"],
          "exclude": ["src/**/*.test.ts", "src/**/*.test.tsx"],
          "references": [{ "path": "./tsconfig.node.json" }]
        }
        """
    ).strip() + "\n"


def _stem_tsconfig_node_json() -> str:
    return dedent(
        """
        {
          "compilerOptions": {
            "composite": true,
            "skipLibCheck": true,
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "allowSyntheticDefaultImports": true
          },
          "include": ["vite.config.ts"]
        }
        """
    ).strip() + "\n"


def _stem_vite_config() -> str:
    return dedent(
        """
        import { defineConfig } from 'vite';
        import react from '@vitejs/plugin-react';

        export default defineConfig({
          plugins: [react()],
          test: {
            environment: 'jsdom',
            globals: true,
            setupFiles: [],
          },
        });
        """
    ).strip() + "\n"


def _stem_index_html() -> str:
    return dedent(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <meta name="theme-color" content="#0b1020" />
            <link rel="icon" href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="%230b1020"/><path d="M18 42V16h24v8H26v7h13v8H26v3z" fill="%2338bdf8"/><circle cx="43" cy="43" r="7" fill="%23f472b6"/></svg>' />
            <title>Nova Stem Player</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
          </body>
        </html>
        """
    ).strip() + "\n"


def _stem_main_tsx() -> str:
    return dedent(
        """
        import React from 'react';
        import ReactDOM from 'react-dom/client';
        import App from './App';
        import './styles.css';

        ReactDOM.createRoot(document.getElementById('root')!).render(
          <React.StrictMode>
            <App />
          </React.StrictMode>,
        );
        """
    ).strip() + "\n"


def _stem_vite_env_d_ts() -> str:
    return '/// <reference types="vite/client" />\n'


def _stem_demo_library_ts() -> str:
    return dedent(
        """
        import type { StemName } from '../audio/stemEngine';

        export type LibraryTrack = {
          id: string;
          title: string;
          artist: string;
          bpm: number;
          key: string;
          mode: 'mixed' | 'stems';
          stems: StemName[];
          duration: string;
        };

        export const demoLibrary: LibraryTrack[] = [
          {
            id: 'nova-night-drive',
            title: 'Night Drive Sketch',
            artist: 'Nova Local Session',
            bpm: 124,
            key: 'F minor',
            mode: 'mixed',
            stems: ['vocals', 'drums', 'bass', 'other'],
            duration: '03:42',
          },
          {
            id: 'studio-check',
            title: 'Studio Check Loop',
            artist: 'Stem Prep',
            bpm: 96,
            key: 'A minor',
            mode: 'stems',
            stems: ['vocals', 'drums', 'bass', 'other'],
            duration: '02:18',
          },
          {
            id: 'bounce-export',
            title: 'Bounce Export Test',
            artist: 'Nova Mix Lab',
            bpm: 138,
            key: 'C sharp minor',
            mode: 'mixed',
            stems: ['drums', 'bass', 'other'],
            duration: '04:05',
          },
        ];
        """
    ).strip() + "\n"


def _stem_engine_ts() -> str:
    return dedent(
        """
        export type StemName = 'vocals' | 'drums' | 'bass' | 'other';

        export type StemSettings = {
          gain: number;
          pan: number;
          muted: boolean;
          solo: boolean;
          color: string;
          meter: number;
          loaded: boolean;
        };

        export type StemState = Record<StemName, StemSettings>;

        export const stemLabels: Record<StemName, string> = {
          vocals: 'Vocals',
          drums: 'Drums',
          bass: 'Bass',
          other: 'Other',
        };

        export const stemOrder: StemName[] = ['vocals', 'drums', 'bass', 'other'];

        export function createDefaultStemState(): StemState {
          return {
            vocals: { gain: 0.82, pan: 0, muted: false, solo: false, color: '#f472b6', meter: 64, loaded: false },
            drums: { gain: 0.9, pan: 0, muted: false, solo: false, color: '#38bdf8', meter: 78, loaded: false },
            bass: { gain: 0.76, pan: 0, muted: false, solo: false, color: '#a3e635', meter: 54, loaded: false },
            other: { gain: 0.68, pan: 0, muted: false, solo: false, color: '#facc15', meter: 46, loaded: false },
          };
        }

        export function resolveSoloStemGains(stems: StemState): Record<StemName, number> {
          const anySolo = stemOrder.some((stem) => stems[stem].solo);
          return stemOrder.reduce((result, stem) => {
            const settings = stems[stem];
            result[stem] = settings.muted || (anySolo && !settings.solo) ? 0 : settings.gain;
            return result;
          }, {} as Record<StemName, number>);
        }

        export type StemEngine = {
          context: AudioContext;
          source: MediaElementAudioSourceNode;
          preamp: GainNode;
          lowShelf: BiquadFilterNode;
          midPeak: BiquadFilterNode;
          highShelf: BiquadFilterNode;
          analyser: AnalyserNode;
          connect(): void;
          setMasterGain(value: number): void;
          setEq(low: number, mid: number, high: number): void;
          setMediaSession(trackTitle: string, artist: string): void;
        };

        export function createStemEngine(audio: HTMLAudioElement, context = new AudioContext()): StemEngine {
          const source = context.createMediaElementSource(audio);
          const preamp = context.createGain();
          const lowShelf = context.createBiquadFilter();
          const midPeak = context.createBiquadFilter();
          const highShelf = context.createBiquadFilter();
          const analyser = context.createAnalyser();

          lowShelf.type = 'lowshelf';
          lowShelf.frequency.value = 160;
          midPeak.type = 'peaking';
          midPeak.frequency.value = 1200;
          midPeak.Q.value = 0.9;
          highShelf.type = 'highshelf';
          highShelf.frequency.value = 6200;
          analyser.fftSize = 2048;

          let connected = false;

          return {
            context,
            source,
            preamp,
            lowShelf,
            midPeak,
            highShelf,
            analyser,
            connect() {
              if (connected) return;
              source.connect(preamp);
              preamp.connect(lowShelf);
              lowShelf.connect(midPeak);
              midPeak.connect(highShelf);
              highShelf.connect(analyser);
              analyser.connect(context.destination);
              connected = true;
            },
            setMasterGain(value: number) {
              preamp.gain.value = Math.max(0, Math.min(1.4, value));
            },
            setEq(low: number, mid: number, high: number) {
              lowShelf.gain.value = low;
              midPeak.gain.value = mid;
              highShelf.gain.value = high;
            },
            setMediaSession(trackTitle: string, artist: string) {
              if ('mediaSession' in navigator) {
                navigator.mediaSession.metadata = new MediaMetadata({
                  title: trackTitle,
                  artist,
                  album: 'Nova Stem Player',
                });
                navigator.mediaSession.setActionHandler('play', () => void audio.play());
                navigator.mediaSession.setActionHandler('pause', () => audio.pause());
              }
            },
          };
        }
        """
    ).strip() + "\n"


def _stem_app_tsx() -> str:
    return dedent(
        """
        import { useMemo, useRef, useState } from 'react';
        import {
          AudioLines,
          Disc3,
          Download,
          FileAudio,
          ListMusic,
          Mic2,
          Pause,
          Play,
          RotateCcw,
          SlidersHorizontal,
          Upload,
          Volume2,
          Waves,
        } from 'lucide-react';
        import {
          createDefaultStemState,
          resolveSoloStemGains,
          stemOrder,
          type StemName,
          type StemState,
        } from './audio/stemEngine';
        import { demoLibrary, type LibraryTrack } from './data/demoLibrary';

        type LoadedFile = {
          id: string;
          name: string;
          url: string;
          stem?: StemName;
        };

        type EqState = {
          low: number;
          mid: number;
          high: number;
        };

        const stemDropLabels: Record<StemName, string> = {
          vocals: 'Vocal stem',
          drums: 'Drum stem',
          bass: 'Bass stem',
          other: 'Other stem',
        };

        const stemDisplayNames: Record<StemName, string> = {
          vocals: 'Vocals',
          drums: 'Drums',
          bass: 'Bass',
          other: 'Other',
        };

        function formatPercent(value: number) {
          return `${Math.round(value * 100)}%`;
        }

        function createLoadedFile(file: File, stem?: StemName): LoadedFile {
          return {
            id: `${file.name}-${file.lastModified}-${stem || 'mix'}`,
            name: file.name,
            url: URL.createObjectURL(file),
            stem,
          };
        }

        function updateStem(
          stems: StemState,
          stem: StemName,
          patch: Partial<StemState[StemName]>,
        ): StemState {
          return {
            ...stems,
            [stem]: {
              ...stems[stem],
              ...patch,
            },
          };
        }

        export default function App() {
          const audioRef = useRef<HTMLAudioElement | null>(null);
          const [tracks, setTracks] = useState<LibraryTrack[]>(demoLibrary);
          const [activeTrack, setActiveTrack] = useState<LibraryTrack>(demoLibrary[0]);
          const [loadedFiles, setLoadedFiles] = useState<LoadedFile[]>([]);
          const [activeFileUrl, setActiveFileUrl] = useState('');
          const [stems, setStems] = useState<StemState>(() => createDefaultStemState());
          const [eq, setEq] = useState<EqState>({ low: 0, mid: 0, high: 0 });
          const [volume, setVolume] = useState(0.82);
          const [speed, setSpeed] = useState(1);
          const [pitch, setPitch] = useState(0);
          const [progress, setProgress] = useState(0.34);
          const [playing, setPlaying] = useState(false);
          const [loopEnabled, setLoopEnabled] = useState(true);
          const [dropActive, setDropActive] = useState(false);

          const effectiveGains = useMemo(() => resolveSoloStemGains(stems), [stems]);
          const loadedStemCount = stemOrder.filter((stem) => stems[stem].loaded).length;
          const workstationMode =
            loadedStemCount >= 2 ? 'true stem mode' : 'simulated stem shaping';

          function handleFiles(files: FileList | File[], stem?: StemName) {
            const nextFiles = Array.from(files).filter((file) => file.type.startsWith('audio/') || file.name.match(/\\.(mp3|wav|m4a|ogg|flac)$/i));
            if (!nextFiles.length) return;

            const loaded = nextFiles.map((file) => createLoadedFile(file, stem));
            setLoadedFiles((current) => [...loaded, ...current].slice(0, 12));
            setActiveFileUrl(loaded[0].url);
            setActiveTrack({
              id: loaded[0].id,
              title: loaded[0].name.replace(/\\.[^.]+$/, ''),
              artist: 'Local file',
              bpm: activeTrack.bpm,
              key: activeTrack.key,
              mode: stem ? 'stems' : 'mixed',
              stems: stem ? [stem] : stemOrder,
              duration: '--:--',
            });
            if (stem) {
              setStems((current) => updateStem(current, stem, { loaded: true, meter: 82 }));
            }
          }

          async function togglePlayback() {
            const audio = audioRef.current;
            if (!audio) return;
            audio.volume = volume;
            audio.playbackRate = speed;
            try {
              if (playing) {
                audio.pause();
                setPlaying(false);
              } else {
                await audio.play();
                setPlaying(true);
              }
            } catch {
              setPlaying(false);
            }
          }

          function resetMix() {
            setStems(createDefaultStemState());
            setEq({ low: 0, mid: 0, high: 0 });
            setVolume(0.82);
            setSpeed(1);
            setPitch(0);
          }

          function handleDrop(event: React.DragEvent<HTMLElement>) {
            event.preventDefault();
            setDropActive(false);
            handleFiles(event.dataTransfer.files);
          }

          return (
            <main
              className={`app-shell ${dropActive ? 'drop-active' : ''}`}
              onDragOver={(event) => {
                event.preventDefault();
                setDropActive(true);
              }}
              onDragLeave={() => setDropActive(false)}
              onDrop={handleDrop}
            >
              <audio
                ref={audioRef}
                src={activeFileUrl || undefined}
                loop={loopEnabled}
                onTimeUpdate={(event) => {
                  const audio = event.currentTarget;
                  if (audio.duration) setProgress(audio.currentTime / audio.duration);
                }}
                onEnded={() => setPlaying(false)}
              />

              <aside className="library-panel" aria-label="Library">
                <div className="brand-lockup">
                  <div className="brand-mark"><Disc3 size={24} /></div>
                  <div>
                    <h1>Nova Stem Player</h1>
                    <p>Local mix workstation</p>
                  </div>
                </div>

                <label className="drop-zone">
                  <Upload size={22} />
                  <span>Load audio</span>
                  <input
                    type="file"
                    accept="audio/*"
                    multiple
                    onChange={(event) => event.target.files && handleFiles(event.target.files)}
                  />
                </label>

                <section className="track-list" aria-label="Session tracks">
                  <div className="panel-title"><ListMusic size={16} /> Library</div>
                  {[...loadedFiles.map((file) => ({
                    id: file.id,
                    title: file.name.replace(/\\.[^.]+$/, ''),
                    artist: file.stem ? stemDropLabels[file.stem] : 'Local mix',
                    bpm: activeTrack.bpm,
                    key: activeTrack.key,
                    mode: file.stem ? 'stems' as const : 'mixed' as const,
                    stems: file.stem ? [file.stem] : stemOrder,
                    duration: '--:--',
                  })), ...tracks].slice(0, 8).map((track) => (
                    <button
                      className={`track-row ${activeTrack.id === track.id ? 'selected' : ''}`}
                      key={track.id}
                      onClick={() => setActiveTrack(track)}
                    >
                      <span>{track.title}</span>
                      <small>{track.artist} / {track.bpm} BPM</small>
                    </button>
                  ))}
                </section>
              </aside>

              <section className="workspace">
                <header className="topbar">
                  <div>
                    <p className="eyeline">Now mixing</p>
                    <h2>{activeTrack.title}</h2>
                    <span>{activeTrack.artist} / {activeTrack.key} / {activeTrack.bpm} BPM</span>
                  </div>
                  <div className="status-cluster">
                    <span>{workstationMode}</span>
                    <span>{loadedStemCount}/4 stems loaded</span>
                  </div>
                </header>

                <section className="waveform-panel" aria-label="Waveform">
                  <div className="waveform">
                    {Array.from({ length: 96 }, (_, index) => (
                      <i
                        key={index}
                        style={{
                          height: `${22 + ((index * 19) % 74)}%`,
                          opacity: index / 96 <= progress ? 1 : 0.32,
                        }}
                      />
                    ))}
                    <div className="playhead" style={{ left: `${progress * 100}%` }} />
                  </div>
                  <input
                    aria-label="Track position"
                    className="seek"
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={progress}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      setProgress(next);
                      const audio = audioRef.current;
                      if (audio?.duration) audio.currentTime = audio.duration * next;
                    }}
                  />
                </section>

                <section className="stem-grid" aria-label="Stem mixer">
                  {stemOrder.map((stem) => {
                    const settings = stems[stem];
                    return (
                      <article className="stem-strip" key={stem}>
                        <div className="stem-head">
                          <span className="stem-dot" style={{ background: settings.color }} />
                          <div>
                            <h3>{stemDisplayNames[stem]}</h3>
                            <p>{settings.loaded ? 'separate file loaded' : 'zone control ready'}</p>
                          </div>
                        </div>
                        <label className="mini-loader">
                          <FileAudio size={15} />
                          <span>{stemDropLabels[stem]}</span>
                          <input
                            type="file"
                            accept="audio/*"
                            onChange={(event) => event.target.files && handleFiles(event.target.files, stem)}
                          />
                        </label>
                        <div className="meter"><span style={{ width: `${settings.meter}%`, background: settings.color }} /></div>
                        <label>
                          Gain {formatPercent(effectiveGains[stem])}
                          <input
                            type="range"
                            min="0"
                            max="1.25"
                            step="0.01"
                            value={settings.gain}
                            onChange={(event) => setStems((current) => updateStem(current, stem, { gain: Number(event.target.value) }))}
                          />
                        </label>
                        <label>
                          Pan {settings.pan > 0 ? 'R' : settings.pan < 0 ? 'L' : 'C'}
                          <input
                            type="range"
                            min="-1"
                            max="1"
                            step="0.01"
                            value={settings.pan}
                            onChange={(event) => setStems((current) => updateStem(current, stem, { pan: Number(event.target.value) }))}
                          />
                        </label>
                        <div className="toggle-row">
                          <button
                            className={settings.muted ? 'active danger' : ''}
                            onClick={() => setStems((current) => updateStem(current, stem, { muted: !settings.muted }))}
                          >
                            Mute
                          </button>
                          <button
                            className={settings.solo ? 'active' : ''}
                            onClick={() => setStems((current) => updateStem(current, stem, { solo: !settings.solo }))}
                          >
                            Solo
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </section>
              </section>

              <aside className="inspector" aria-label="Inspector">
                <section className="tool-panel">
                  <div className="panel-title"><SlidersHorizontal size={16} /> EQ</div>
                  {(['low', 'mid', 'high'] as const).map((band) => (
                    <label key={band}>
                      {band.toUpperCase()} {eq[band] > 0 ? '+' : ''}{eq[band]} dB
                      <input
                        type="range"
                        min="-12"
                        max="12"
                        step="1"
                        value={eq[band]}
                        onChange={(event) => setEq((current) => ({ ...current, [band]: Number(event.target.value) }))}
                      />
                    </label>
                  ))}
                </section>

                <section className="tool-panel">
                  <div className="panel-title"><AudioLines size={16} /> Performance</div>
                  <label>
                    Speed {speed.toFixed(2)}x
                    <input type="range" min="0.5" max="1.5" step="0.01" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} />
                  </label>
                  <label>
                    Pitch {pitch > 0 ? '+' : ''}{pitch} st
                    <input type="range" min="-12" max="12" step="1" value={pitch} onChange={(event) => setPitch(Number(event.target.value))} />
                  </label>
                  <button className={loopEnabled ? 'active wide' : 'wide'} onClick={() => setLoopEnabled((value) => !value)}>
                    <RotateCcw size={16} /> Loop
                  </button>
                </section>

                <section className="tool-panel">
                  <div className="panel-title"><Mic2 size={16} /> Stem status</div>
                  <p className="truth-note">
                    true stem mode activates when separate stem files are loaded. Single-file playback uses simulated stem shaping.
                  </p>
                  <button className="wide"><Download size={16} /> Export mix</button>
                </section>
              </aside>

              <footer className="transport">
                <button className="transport-button" onClick={togglePlayback} aria-label={playing ? 'Pause' : 'Play'}>
                  {playing ? <Pause size={22} /> : <Play size={22} />}
                </button>
                <div className="transport-meta">
                  <strong>{activeTrack.title}</strong>
                  <span>{Math.round(progress * 100)}% / {activeTrack.duration}</span>
                </div>
                <Waves size={20} />
                <label className="volume">
                  <Volume2 size={18} />
                  <input min="0" max="1" step="0.01" type="range" value={volume} onChange={(event) => setVolume(Number(event.target.value))} />
                </label>
                <button className="ghost-button" onClick={resetMix}>Reset</button>
              </footer>
            </main>
          );
        }
        """
    ).strip() + "\n"


def _stem_app_test_tsx() -> str:
    return dedent(
        """
        import '@testing-library/jest-dom/vitest';
        import { render, screen } from '@testing-library/react';
        import App from './App';

        test('renders the Nova Stem Player workstation surface', () => {
          render(<App />);

          expect(screen.getByRole('heading', { name: /Nova Stem Player/i })).toBeInTheDocument();
          expect(screen.getByText(/true stem mode/i)).toBeInTheDocument();
          expect(screen.getAllByText(/simulated stem shaping/i).length).toBeGreaterThan(0);
          expect(screen.getByRole('region', { name: /Stem mixer/i })).toBeInTheDocument();
          expect(screen.getByText('Vocals')).toBeInTheDocument();
          expect(screen.getByText('Drums')).toBeInTheDocument();
          expect(screen.getByText('Bass')).toBeInTheDocument();
          expect(screen.getByText('Other')).toBeInTheDocument();
        });
        """
    ).strip() + "\n"


def _stem_styles_css() -> str:
    return dedent(
        """
        :root {
          color-scheme: dark;
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #080c16;
          color: #eef4ff;
          font-synthesis: none;
          text-rendering: optimizeLegibility;
        }

        * { box-sizing: border-box; }
        body { margin: 0; min-width: 320px; min-height: 100vh; background: #080c16; }
        button, input { font: inherit; }
        button { cursor: pointer; }
        input[type="range"] { width: 100%; accent-color: #38bdf8; }
        input[type="file"] { display: none; }

        .app-shell {
          min-height: 100vh;
          display: grid;
          grid-template-columns: 248px minmax(0, 1fr) 304px;
          grid-template-rows: minmax(0, 1fr) 76px;
          gap: 1px;
          background:
            radial-gradient(circle at 30% 12%, rgba(56, 189, 248, 0.14), transparent 28%),
            radial-gradient(circle at 78% 4%, rgba(244, 114, 182, 0.12), transparent 28%),
            #080c16;
        }

        .drop-active { outline: 3px solid #38bdf8; outline-offset: -8px; }
        .library-panel, .inspector, .workspace, .transport {
          background: rgba(10, 15, 28, 0.92);
          border-color: rgba(148, 163, 184, 0.18);
        }

        .library-panel, .inspector {
          min-height: 0;
          padding: 18px;
          overflow: auto;
        }

        .library-panel { border-right: 1px solid rgba(148, 163, 184, 0.16); }
        .inspector { border-left: 1px solid rgba(148, 163, 184, 0.16); }
        .workspace {
          min-width: 0;
          padding: 20px;
          overflow: auto;
        }

        .brand-lockup { display: flex; gap: 12px; align-items: center; margin-bottom: 22px; }
        .brand-mark {
          width: 46px;
          height: 46px;
          display: grid;
          place-items: center;
          border-radius: 14px;
          background: linear-gradient(145deg, #7c3aed, #0ea5e9);
          box-shadow: 0 16px 40px rgba(14, 165, 233, 0.22);
        }
        h1, h2, h3, p { margin: 0; }
        h1 { font-size: 18px; line-height: 1.15; }
        h2 { font-size: clamp(28px, 5vw, 54px); line-height: 0.95; letter-spacing: 0; }
        h3 { font-size: 17px; line-height: 1.1; }
        p, span, small, label { color: #aab6cc; }

        .drop-zone, .mini-loader {
          border: 1px dashed rgba(148, 163, 184, 0.35);
          border-radius: 8px;
          background: rgba(15, 23, 42, 0.75);
          display: flex;
          align-items: center;
          gap: 10px;
          color: #e5edf9;
        }
        .drop-zone { min-height: 86px; justify-content: center; margin-bottom: 20px; }
        .mini-loader { min-height: 36px; justify-content: center; font-size: 13px; }

        .panel-title {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
          color: #d7e4f7;
          font-size: 13px;
          font-weight: 700;
          text-transform: uppercase;
        }

        .track-list { display: grid; gap: 8px; }
        .track-row {
          text-align: left;
          border: 1px solid rgba(148, 163, 184, 0.16);
          border-radius: 8px;
          padding: 11px 12px;
          background: rgba(15, 23, 42, 0.72);
          color: #eef4ff;
        }
        .track-row span { display: block; color: #eef4ff; font-weight: 700; }
        .track-row small { display: block; margin-top: 3px; font-size: 12px; }
        .track-row.selected { border-color: #38bdf8; background: rgba(14, 165, 233, 0.18); }

        .topbar {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 20px;
          margin-bottom: 18px;
        }
        .eyeline { color: #38bdf8; font-size: 12px; font-weight: 800; text-transform: uppercase; margin-bottom: 8px; }
        .status-cluster { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
        .status-cluster span {
          border: 1px solid rgba(148, 163, 184, 0.2);
          border-radius: 999px;
          padding: 8px 10px;
          background: rgba(15, 23, 42, 0.8);
          font-size: 12px;
          color: #dbeafe;
        }

        .waveform-panel {
          border: 1px solid rgba(148, 163, 184, 0.16);
          border-radius: 8px;
          background: linear-gradient(180deg, rgba(15, 23, 42, 0.88), rgba(8, 13, 27, 0.88));
          padding: 18px;
          margin-bottom: 16px;
        }
        .waveform {
          position: relative;
          height: 190px;
          display: flex;
          align-items: center;
          gap: 4px;
          overflow: hidden;
        }
        .waveform i {
          flex: 1;
          min-width: 3px;
          border-radius: 999px;
          background: linear-gradient(180deg, #f472b6, #38bdf8 48%, #a3e635);
        }
        .playhead { position: absolute; top: 0; bottom: 0; width: 2px; background: #f8fafc; box-shadow: 0 0 20px #38bdf8; }
        .seek { margin-top: 12px; }

        .stem-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(170px, 1fr));
          gap: 12px;
        }
        .stem-strip, .tool-panel {
          border: 1px solid rgba(148, 163, 184, 0.16);
          border-radius: 8px;
          background: rgba(15, 23, 42, 0.75);
          padding: 14px;
        }
        .stem-strip { display: grid; gap: 12px; }
        .stem-head { display: flex; gap: 10px; align-items: center; min-height: 46px; }
        .stem-head p { font-size: 12px; margin-top: 3px; }
        .stem-dot { width: 12px; height: 42px; border-radius: 999px; }
        .meter { height: 8px; background: #253047; border-radius: 999px; overflow: hidden; }
        .meter span { display: block; height: 100%; border-radius: inherit; }
        .stem-strip label, .tool-panel label {
          display: grid;
          gap: 7px;
          font-size: 12px;
          font-weight: 700;
          text-transform: uppercase;
          color: #cfdaeb;
        }
        .toggle-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .toggle-row button, .tool-panel button, .ghost-button {
          min-height: 38px;
          border: 1px solid rgba(148, 163, 184, 0.2);
          border-radius: 8px;
          background: #162033;
          color: #eef4ff;
          font-weight: 800;
        }
        button.active { border-color: #38bdf8; background: rgba(14, 165, 233, 0.2); color: #e0f2fe; }
        button.danger { border-color: #fb7185; background: rgba(244, 63, 94, 0.18); color: #ffe4e6; }

        .inspector { display: grid; align-content: start; gap: 12px; }
        .tool-panel { display: grid; gap: 14px; }
        .tool-panel .wide {
          width: 100%;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .truth-note {
          color: #c8d5e8;
          line-height: 1.5;
          font-size: 13px;
        }

        .transport {
          grid-column: 1 / -1;
          border-top: 1px solid rgba(148, 163, 184, 0.16);
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 12px 18px;
          min-width: 0;
        }
        .transport-button {
          width: 50px;
          height: 50px;
          border: 0;
          border-radius: 50%;
          background: #8b5cf6;
          color: #fff;
          display: grid;
          place-items: center;
          flex: 0 0 auto;
        }
        .transport-meta { min-width: 180px; }
        .transport-meta strong { display: block; }
        .transport-meta span { font-size: 12px; }
        .volume { display: flex; align-items: center; gap: 10px; width: min(280px, 32vw); }
        .ghost-button { padding: 0 16px; margin-left: auto; }

        @media (max-width: 1120px) {
          .app-shell { grid-template-columns: 220px minmax(0, 1fr); }
          .inspector { grid-column: 1 / -1; grid-template-columns: repeat(3, minmax(0, 1fr)); border-left: 0; border-top: 1px solid rgba(148, 163, 184, 0.16); }
          .stem-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); }
        }

        @media (max-width: 760px) {
          .app-shell { display: block; }
          .library-panel, .workspace, .inspector { border: 0; padding: 14px; }
          .topbar { display: grid; }
          .status-cluster { justify-content: flex-start; }
          .stem-grid, .inspector { grid-template-columns: 1fr; }
          .waveform { height: 136px; }
          .transport {
            position: static;
            flex-wrap: wrap;
            padding: 10px 14px;
          }
          .volume { width: 100%; }
          .ghost-button { margin-left: 0; }
        }
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
          <title>Nova Pac Runner</title>
          <style>
            :root { color-scheme: dark; font-family: Inter, system-ui, sans-serif; }
            body {
              margin: 0;
              min-height: 100vh;
              display: grid;
              place-items: center;
              background: radial-gradient(circle at top, #172047 0, #070912 56%, #02030a 100%);
              color: #f7f7ff;
            }
            .shell {
              width: min(94vw, 760px);
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
              width: 100%;
              aspect-ratio: 19 / 21;
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
