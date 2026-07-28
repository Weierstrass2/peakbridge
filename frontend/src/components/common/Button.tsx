import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  children: ReactNode;
}

const variants: Record<Variant, string> = {
  primary: 'bg-[#4C8DFF] hover:bg-[#3D75E0] text-white',
  secondary: 'bg-[#0E1116] border border-[#222933] hover:bg-[#222933] text-white',
  danger: 'bg-[#E5484D] hover:bg-[#C93B40] text-white',
  ghost: 'hover:bg-[#222933] text-[#98A2B3] hover:text-white',
};

export default function Button({
  variant = 'primary',
  loading,
  disabled,
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
      )}
      {children}
    </button>
  );
}
