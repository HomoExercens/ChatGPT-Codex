import { useEffect } from 'react';

import { useSettingsStore } from '../stores/settings';

export function useApplyA11ySettings(): void {
  const fontScale = useSettingsStore((s) => s.fontScale);
  const contrast = useSettingsStore((s) => s.contrast);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const colorblind = useSettingsStore((s) => s.colorblind);

  useEffect(() => {
    const root = document.documentElement;

    root.style.setProperty('--nl-font-scale', String(fontScale));
    root.style.setProperty('--nl-contrast', String(contrast));

    root.dataset.reduceMotion = reduceMotion ? 'true' : 'false';

    if (colorblind) {
      root.dataset.colorblind = 'true';
      root.style.setProperty('--nl-accent-200', '253 230 138'); // amber-200
      root.style.setProperty('--nl-accent-500', '245 158 11'); // amber-500
      root.style.setProperty('--nl-accent-700', '180 83 9'); // amber-700
    } else {
      delete root.dataset.colorblind;
      root.style.setProperty('--nl-accent-200', '221 214 254'); // violet-200
      root.style.setProperty('--nl-accent-500', '139 92 246');
      root.style.setProperty('--nl-accent-700', '109 40 217'); // violet-700
    }
  }, [colorblind, contrast, fontScale, reduceMotion]);
}
