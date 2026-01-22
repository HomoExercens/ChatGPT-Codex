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
  const baseStyles =
    'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl';

  const variants = {
    primary:
      'bg-brand-600 hover:bg-brand-700 text-white shadow-lg shadow-brand-500/30 focus:ring-brand-500 border border-transparent',
    secondary:
      'bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 shadow-sm focus:ring-slate-400',
    ghost: 'bg-transparent hover:bg-slate-100 text-slate-600 focus:ring-slate-400',
    destructive: 'bg-red-500 hover:bg-red-600 text-white shadow-md focus:ring-red-500',
    outline: 'border-2 border-brand-600 text-brand-600 hover:bg-brand-50',
  } as const;

  const sizes = {
    sm: 'text-xs px-3 py-1.5 h-8',
    md: 'text-sm px-4 py-2.5 h-10',
    lg: 'text-base px-6 py-3 h-12',
    icon: 'h-10 w-10 p-2',
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
      className={`bg-white rounded-2xl border ${isActive ? 'border-brand-500 ring-2 ring-brand-100' : 'border-slate-200'} shadow-sm hover:shadow-md transition-shadow duration-300 ${className}`}
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
  <div className={`px-5 py-4 border-b border-slate-100 flex items-center justify-between ${className}`} {...props}>
    {children}
  </div>
);

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  children,
  className = '',
  ...props
}) => (
  <h3 className={`font-bold text-slate-800 text-lg tracking-tight ${className}`} {...props}>
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

interface BadgeProps {
  variant?: 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'brand';
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ variant = 'neutral', children, className = '' }) => {
  const styles = {
    success: 'bg-green-100 text-green-700 border-green-200',
    warning: 'bg-amber-100 text-amber-700 border-amber-200',
    error: 'bg-red-100 text-red-700 border-red-200',
    info: 'bg-blue-100 text-blue-700 border-blue-200',
    neutral: 'bg-slate-100 text-slate-600 border-slate-200',
    brand: 'bg-brand-100 text-brand-700 border-brand-200',
  } as const;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${styles[variant]} ${className}`}
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
        <label htmlFor={inputId} className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full px-4 py-2 rounded-xl border bg-slate-50 focus:bg-white transition-colors outline-none focus:ring-2 focus:ring-brand-200 ${error ? 'border-red-300 focus:border-red-500' : 'border-slate-200 focus:border-brand-500'} ${className}`}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
};

export const Slider: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input type="range" className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-brand-600" {...props} />
);

export const Skeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`animate-pulse bg-slate-200 rounded-lg ${className}`}></div>
);
