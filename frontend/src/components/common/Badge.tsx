import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'peak' | 'success' | 'warning' | 'info' | 'danger';

interface BadgeProps {
  variant?: BadgeVariant;
  pulse?: boolean;
  children: ReactNode;
}

const styles: Record<BadgeVariant, string> = {
  default: 'border-[#334155] bg-[#1E293B] text-[#94A3B8]',
  peak: 'border-[#F97316]/40 bg-[#F97316]/10 text-[#F97316]',
  success: 'border-[#10B981]/40 bg-[#10B981]/10 text-[#10B981]',
  warning: 'border-[#FBBF24]/40 bg-[#FBBF24]/10 text-[#FBBF24]',
  info: 'border-[#3B82F6]/40 bg-[#3B82F6]/10 text-[#3B82F6]',
  danger: 'border-[#EF4444]/40 bg-[#EF4444]/10 text-[#EF4444]',
};

export default function Badge({ variant = 'default', pulse, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${styles[variant]}`}
    >
      {pulse && <span className="animate-pulse-dot h-2 w-2 rounded-full bg-[#F97316]" />}
      {children}
    </span>
  );
}
