import React, { useMemo } from 'react';

const PATHS = [
  'M12 2c2 0 3.5 1.6 3.5 3.4 0 1.1-.4 1.9-1 2.5 1.9.7 3.5 2.4 3.5 4.8V20H6v-4.3c0-2.4 1.6-4.1 3.5-4.8-.6-.6-1-1.4-1-2.5C8.5 3.6 10 2 12 2Z',
  'M8 20v-5.2c0-1.7 1.2-3.2 3-3.7V9.5L9.6 8.3C8.6 7.4 8 6.2 8 5c0-1.7 1.3-3 3-3h2c1.7 0 3 1.3 3 3 0 1.2-.6 2.4-1.6 3.3L13 9.5v1.6c1.8.5 3 2 3 3.7V20H8Z',
  'M5 20v-6c0-2 1.6-3.6 3.6-3.6h.3L8 8.8C7.4 8.2 7 7.3 7 6.3 7 4.5 8.5 3 10.3 3h3.4C15.5 3 17 4.5 17 6.3c0 1-.4 1.9-1 2.5l-.9 1.6h.3c2 0 3.6 1.6 3.6 3.6v6H5Z',
];

function hash32(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export const CreatureSilhouettes: React.FC<{
  seed: string;
  count: number;
  className?: string;
}> = ({ seed, count, className = '' }) => {
  const base = useMemo(() => hash32(seed), [seed]);
  const n = Math.max(0, Math.min(3, count));

  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      {Array.from({ length: n }).map((_, i) => {
        const idx = (base + i * 17) % PATHS.length;
        const tint = 0.5 + (((base >>> (i * 3)) & 0xff) / 255) * 0.5;
        return (
          <div
            key={i}
            className="w-8 h-8 rounded-xl bg-white/10 border border-white/10 flex items-center justify-center"
            style={{ opacity: tint }}
            aria-hidden="true"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" className="text-white/90" fill="currentColor">
              <path d={PATHS[idx]} />
            </svg>
          </div>
        );
      })}
    </div>
  );
};

