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
    const nextFiles = Array.from(files).filter((file) => file.type.startsWith('audio/') || file.name.match(/\.(mp3|wav|m4a|ogg|flac)$/i));
    if (!nextFiles.length) return;

    const loaded = nextFiles.map((file) => createLoadedFile(file, stem));
    setLoadedFiles((current) => [...loaded, ...current].slice(0, 12));
    setActiveFileUrl(loaded[0].url);
    setActiveTrack({
      id: loaded[0].id,
      title: loaded[0].name.replace(/\.[^.]+$/, ''),
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
            title: file.name.replace(/\.[^.]+$/, ''),
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
