import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padding?: boolean;
}

export default function Card({
  title,
  subtitle,
  action,
  children,
  className = '',
  padding = true,
}: CardProps) {
  return (
    <div className={`rounded-xl border border-panel-border bg-panel ${className}`}>
      {(title || action) && (
        <div className={`flex items-start justify-between ${padding ? 'px-4 pt-4' : ''}`}>
          <div>
            {title && <h2 className="text-sm font-semibold text-white">{title}</h2>}
            {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={padding ? 'p-4' : ''}>{children}</div>
    </div>
  );
}
