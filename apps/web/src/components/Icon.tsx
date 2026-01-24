import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '../lib/cn';

export type IconSize = 20 | 24 | 28;

const SIZE_MAP: Record<'sm' | 'md' | 'lg', IconSize> = {
  sm: 20,
  md: 24,
  lg: 28,
};

export function Icon(props: {
  icon: LucideIcon;
  size?: IconSize | 'sm' | 'md' | 'lg';
  strokeWidth?: number;
  filled?: boolean;
  className?: string;
  title?: string;
  'aria-hidden'?: boolean;
}) {
  const {
    icon: Lucide,
    size = 'sm',
    strokeWidth = 2,
    filled = false,
    className,
    title,
    ...rest
  } = props;

  const px: IconSize = typeof size === 'number' ? size : SIZE_MAP[size];

  return (
    <Lucide
      size={px}
      strokeWidth={strokeWidth}
      fill={filled ? 'currentColor' : 'none'}
      className={cn('shrink-0', className)}
      title={title}
      {...rest}
    />
  );
}

