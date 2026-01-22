import { create } from 'zustand';

import type { Language } from '../lib/translations';

type SettingsState = {
  language: Language;
  fontScale: number;
  contrast: number;
  reduceMotion: boolean;
  colorblind: boolean;

  setLanguage: (language: Language) => void;
  setFontScale: (fontScale: number) => void;
  setContrast: (contrast: number) => void;
  setReduceMotion: (reduceMotion: boolean) => void;
  setColorblind: (colorblind: boolean) => void;
};

const STORAGE_KEY = 'neuroleague.settings';

function loadInitial(): Omit<
  SettingsState,
  | 'setLanguage'
  | 'setFontScale'
  | 'setContrast'
  | 'setReduceMotion'
  | 'setColorblind'
> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore
  }
  return {
    language: 'ko',
    fontScale: 1,
    contrast: 1,
    reduceMotion: false,
    colorblind: false,
  };
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  ...loadInitial(),
  setLanguage: (language) => {
    set({ language });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...get(), language }));
  },
  setFontScale: (fontScale) => {
    set({ fontScale });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...get(), fontScale }));
  },
  setContrast: (contrast) => {
    set({ contrast });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...get(), contrast }));
  },
  setReduceMotion: (reduceMotion) => {
    set({ reduceMotion });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...get(), reduceMotion }));
  },
  setColorblind: (colorblind) => {
    set({ colorblind });
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...get(), colorblind }));
  },
}));

