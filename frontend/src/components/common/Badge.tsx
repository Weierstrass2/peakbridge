import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'peak' | 'success' | 'warning' | 'info' | 'danger';

interface BadgeProps {
  variant?: BadgeVariant;
  pulse?: boolean;
  children: ReactNode;
}

const styles: Record<BadgeVariant, string> = {
  default: 'border-[#222933] bg-[#0E1116] text-[#98A2B3]',
  peak: 'border-[#E8A33D]/40 bg-[#E8A33D]/10 text-[#E8A33D]',
  success: 'border-[#2EBD85]/40 bg-[#2EBD85]/10 text-[#2EBD85]',
  warning: 'border-[#E8A33D]/40 bg-[#E8A33D]/10 text-[#E8A33D]',
  info: 'border-[#4C8DFF]/40 bg-[#4C8DFF]/10 text-[#4C8DFF]',
  danger: 'border-[#E5484D]/40 bg-[#E5484D]/10 text-[#E5484D]',
};

export default function Badge({ variant = 'default', pulse, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${styles[variant]}`}
    >
      {pulse && <span className="animate-pulse-dot h-2 w-2 rounded-full bg-[#E8A33D]" />}
      {children}
    </span>
  );
}
