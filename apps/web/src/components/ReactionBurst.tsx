import React from 'react';
import { cn } from '../lib/cn';

const REACTION_EMOJI: Record<'up' | 'lol' | 'wow', string> = {
  up: '👍',
  lol: '😂',
  wow: '🤯',
};

export function ReactionBurst(props: {
  reaction: 'up' | 'lol' | 'wow';
  burstKey: string;
  reduceMotion: boolean;
  className?: string;
}) {
  const { reaction, burstKey, reduceMotion, className } = props;
  const [visible, setVisible] = React.useState(true);

  React.useEffect(() => {
    setVisible(true);
    const ms = reduceMotion ? 240 : 520;
    const handle = window.setTimeout(() => setVisible(false), ms);
    return () => window.clearTimeout(handle);
  }, [burstKey, reduceMotion]);

  if (!visible) return null;

  return (
    <div
      data-testid="reaction-burst"
      data-reduced={reduceMotion ? '1' : '0'}
      className={cn(
        'pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 select-none',
        reduceMotion ? 'opacity-95' : 'nl-reaction-burst',
        className
      )}
      aria-hidden="true"
    >
      <span className="text-[76px] drop-shadow-[0_20px_40px_rgba(0,0,0,0.6)]">{REACTION_EMOJI[reaction]}</span>
    </div>
  );
}

