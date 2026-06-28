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
