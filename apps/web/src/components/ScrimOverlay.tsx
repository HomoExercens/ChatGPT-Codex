import React from 'react';
import { cn } from '../lib/cn';

export function ScrimOverlay(props: {
  top?: boolean;
  bottom?: boolean;
  strength?: 'soft' | 'medium' | 'strong';
  className?: string;
}) {
  const { top = true, bottom = true, strength = 'medium', className } = props;

  const topCls =
    strength === 'strong'
      ? 'from-black/75 via-black/35'
      : strength === 'soft'
        ? 'from-black/55 via-black/22'
        : 'from-black/65 via-black/28';

  const bottomCls =
    strength === 'strong'
      ? 'from-black/85 via-black/40'
      : strength === 'soft'
        ? 'from-black/70 via-black/28'
        : 'from-black/78 via-black/32';

  return (
    <div className={cn('absolute inset-0 pointer-events-none', className)} aria-hidden="true">
      {top ? (
        <div
          className={cn('absolute top-0 inset-x-0 h-[140px] bg-gradient-to-b to-transparent', topCls)}
        />
      ) : null}
      {bottom ? (
        <div
          className={cn('absolute bottom-0 inset-x-0 h-[320px] bg-gradient-to-t to-transparent', bottomCls)}
        />
      ) : null}
    </div>
  );
}

