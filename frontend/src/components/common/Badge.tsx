import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'peak' | 'success' | 'warning' | 'info';

interface BadgeProps {
  variant?: BadgeVariant;
  pulse?: boolean;
  children: ReactNode;
}

const styles: Record<BadgeVariant, string> = {
  default: 'border-panel-border bg-panel text-muted',
  peak: 'border-peak/40 bg-peak/10 text-peak-glow shadow-[0_0_12px_rgba(249,115,22,0.25)]',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
};

export default function Badge({ variant = 'default', pulse, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${styles[variant]}`}
    >
      {pulse && <span className="animate-pulse-dot h-2 w-2 rounded-full bg-peak" />}
      {children}
    </span>
  );
}
