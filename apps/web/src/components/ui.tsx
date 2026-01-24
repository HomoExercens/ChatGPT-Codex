import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'destructive' | 'outline';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = [
    'inline-flex items-center justify-center gap-2 select-none whitespace-nowrap font-semibold',
    'transition-[transform,background-color,border-color,box-shadow,opacity] duration-[var(--nl-dur-fast)] ease-[var(--nl-ease-out)]',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 focus-visible:ring-offset-0',
    'disabled:opacity-40 disabled:pointer-events-none',
    'active:scale-[0.985]',
    'rounded-2xl',
  ].join(' ');

  const variants = {
    primary:
      'text-black bg-gradient-to-r from-brand-500 to-accent-500 shadow-glow-brand hover:shadow-[0_0_28px_rgb(var(--nl-brand-500)_/_0.28)]',
    secondary:
      'text-fg bg-surface-1/70 backdrop-blur border border-border/12 shadow-glass hover:bg-surface-1/80 hover:border-border/18',
    ghost: 'text-fg/80 bg-transparent hover:bg-surface-1/35 hover:text-fg',
    destructive: 'text-black bg-danger-500 hover:bg-danger-500/90 shadow-[0_12px_30px_rgba(0,0,0,0.55)]',
    outline: 'text-fg bg-transparent border border-border/18 hover:bg-surface-1/30 hover:border-border/24',
  } as const;

  const sizes = {
    sm: 'h-11 px-3 text-xs',
    md: 'h-12 px-4 text-sm',
    lg: 'h-14 px-5 text-base',
    icon: 'h-11 w-11 p-0',
  } as const;

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-current" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          ></path>
        </svg>
      ) : null}
      {children}
    </button>
  );
};

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  isActive?: boolean;
}

export const Card: React.FC<CardProps> = ({ children, className = '', isActive, ...props }) => {
  return (
    <div
      className={`bg-surface-1/70 backdrop-blur rounded-3xl border ${
        isActive ? 'border-brand-500/50 ring-2 ring-brand-500/20' : 'border-border/12'
      } shadow-glass ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => (
  <div className={`px-5 py-4 border-b border-border/10 flex items-center justify-between ${className}`} {...props}>
    {children}
  </div>
);

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  children,
  className = '',
  ...props
}) => (
  <h3 className={`font-extrabold text-fg text-lg tracking-tight ${className}`} {...props}>
    {children}
  </h3>
);

export const CardContent: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => (
  <div className={`p-5 ${className}`} {...props}>
    {children}
  </div>
);

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'brand';
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'neutral', children, className = '', ...props }) => {
  const styles = {
    success: 'bg-success-500/15 text-success-500 border-success-500/25',
    warning: 'bg-warning-500/15 text-warning-500 border-warning-500/25',
    error: 'bg-danger-500/15 text-danger-500 border-danger-500/25',
    info: 'bg-brand-500/12 text-brand-200 border-brand-500/20',
    neutral: 'bg-surface-2/70 text-fg/75 border-border/10',
    brand: 'bg-brand-500/15 text-brand-100 border-brand-500/25',
  } as const;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${styles[variant]} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
};

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input: React.FC<InputProps> = ({ label, error, className = '', id, ...props }) => {
  const autoId = React.useId().replace(/:/g, '');
  const inputId = id ?? (label ? `nl_${autoId}` : undefined);

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-xs font-bold text-muted uppercase tracking-wider mb-1.5">
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full h-12 px-4 rounded-2xl border bg-surface-2/70 text-fg placeholder:text-muted/60 outline-none transition-[background-color,border-color,box-shadow] duration-[var(--nl-dur-fast)] ease-[var(--nl-ease-out)] focus:ring-2 focus:ring-ring/35 ${
          error ? 'border-danger-500/40 focus:border-danger-500/70' : 'border-border/12 focus:border-border/22'
        } ${className}`}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
};

export const Slider: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input
    type="range"
    className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-brand-500"
    {...props}
  />
);

export const Skeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`animate-pulse bg-white/8 rounded-xl ${className}`}></div>
);

export const Chip: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <span
    className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-extrabold tracking-wide bg-surface-1/55 text-fg border border-border/10 ${className}`}
  >
    {children}
  </span>
);

export const ProgressBar: React.FC<{ value: number; max?: number; className?: string }> = ({
  value,
  max = 100,
  className = '',
}) => {
  const pct = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  return (
    <div className={`w-full h-2 rounded-full bg-white/10 overflow-hidden ${className}`}>
      <div className="h-full bg-gradient-to-r from-brand-500 to-accent-500" style={{ width: `${pct * 100}%` }} />
    </div>
  );
};

export const IconButton: React.FC<ButtonProps & { label: string }> = ({ label, children, ...props }) => (
  <Button size="icon" aria-label={label} {...props}>
    {children}
  </Button>
);

export const BottomSheet: React.FC<{
  open: boolean;
  title?: string;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ open, title, onClose, children }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[120] bg-black/80 flex items-end justify-center" onClick={onClose}>
      <div
        className="w-full max-w-md bg-surface-1/95 backdrop-blur-xl rounded-t-3xl border border-border/12 shadow-depth overflow-hidden pb-safe text-fg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative px-4 pt-3 pb-3 border-b border-border/10 flex items-center justify-between">
          <div className="w-10 h-1.5 rounded-full bg-white/15 mx-auto absolute left-1/2 -translate-x-1/2 top-2" />
          <div className="font-extrabold tracking-tight text-fg">{title ?? ''}</div>
          <button
            type="button"
            className="text-xs font-bold text-muted hover:text-fg px-3 py-2 rounded-xl bg-surface-2/40 hover:bg-surface-2/60 transition-colors"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        <div className="px-4 py-4">{children}</div>
      </div>
    </div>
  );
};

interface SwitchProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onChange'> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
}

export const Switch: React.FC<SwitchProps> = ({ checked, onCheckedChange, label, className = '', disabled, onClick, ...props }) => (
  <button
    type="button"
    role="switch"
    aria-label={label}
    aria-checked={checked}
    disabled={disabled}
    className={[
      'h-11 w-[64px] rounded-full border px-1.5 inline-flex items-center transition-[background-color,border-color,box-shadow,opacity] duration-[var(--nl-dur-fast)] ease-[var(--nl-ease-out)]',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35',
      'disabled:opacity-40 disabled:pointer-events-none',
      checked ? 'bg-brand-500/20 border-brand-500/30' : 'bg-surface-2/45 border-border/14',
      className,
    ].join(' ')}
    onClick={(e) => {
      onClick?.(e);
      if (e.defaultPrevented) return;
      onCheckedChange(!checked);
    }}
    {...props}
  >
    <span
      className={[
        'h-7 w-7 rounded-full shadow-[0_10px_20px_rgba(0,0,0,0.45)] transition-transform duration-[var(--nl-dur-fast)] ease-[var(--nl-ease-out)]',
        checked ? 'translate-x-[22px] bg-gradient-to-br from-brand-400 to-accent-500' : 'translate-x-0 bg-fg/90',
      ].join(' ')}
    />
  </button>
);
