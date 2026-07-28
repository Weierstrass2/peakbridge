import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children?: ReactNode;
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
    <div className={`rounded-md border border-[#222933] bg-[#0E1116] ${className}`}>
      {(title || action) && (
        <div className={`flex items-start justify-between ${padding ? 'px-5 pt-5' : ''}`}>
          <div>
            {title && <h2 className="text-base font-semibold text-white">{title}</h2>}
            {subtitle && <p className="text-sm text-[#98A2B3] mt-1">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={padding ? 'p-5' : ''}>{children}</div>
    </div>
  );
}
