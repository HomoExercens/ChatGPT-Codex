import { create } from 'zustand';

type AuthState = {
  token: string | null;
  setToken: (token: string | null) => void;
};

const STORAGE_KEY = 'neuroleague.token';

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem(STORAGE_KEY),
  setToken: (token) => {
    if (token) {
      localStorage.setItem(STORAGE_KEY, token);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    set({ token });
  },
}));

