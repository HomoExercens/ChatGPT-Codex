import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

const STORAGE_KEY = 'neuroleague.labs_enabled';

function envEnabled(): boolean {
  const raw = String((import.meta as any)?.env?.VITE_ENABLE_LABS ?? '').trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on';
}

function loadStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function useLabsEnabled(): boolean {
  const location = useLocation();
  const [stored, setStored] = useState(loadStored);

  const queryEnabled = useMemo(() => {
    try {
      return new URLSearchParams(location.search).get('labs') === '1';
    } catch {
      return false;
    }
  }, [location.search]);

  useEffect(() => {
    if (!queryEnabled) return;
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      // ignore
    }
    setStored(true);
  }, [queryEnabled]);

  return envEnabled() || queryEnabled || stored;
}
