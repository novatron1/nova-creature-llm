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
