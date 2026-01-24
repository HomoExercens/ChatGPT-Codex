import { create } from 'zustand';

type ChromeState = {
  playChromeHidden: boolean;
  setPlayChromeHidden: (hidden: boolean) => void;
};

export const useChromeStore = create<ChromeState>((set) => ({
  playChromeHidden: false,
  setPlayChromeHidden: (hidden) => set({ playChromeHidden: hidden }),
}));

