interface LoadingSkeletonProps {
  className?: string;
  rows?: number;
}

export default function LoadingSkeleton({ className = '', rows = 1 }: LoadingSkeletonProps) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 rounded bg-panel-border/60" style={{ width: `${90 - i * 10}%` }} />
      ))}
    </div>
  );
}

export function MetricSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-panel-border bg-panel p-4">
      <div className="h-3 w-20 rounded bg-panel-border/60" />
      <div className="mt-3 h-8 w-28 rounded bg-panel-border/60" />
      <div className="mt-2 h-3 w-32 rounded bg-panel-border/60" />
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-panel-border bg-panel p-4">
      <div className="mb-4 h-4 w-40 rounded bg-panel-border/60" />
      <div className="h-64 rounded-lg bg-panel-border/30" />
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-panel-border bg-panel p-4">
      <div className="h-4 w-24 rounded bg-panel-border/60" />
      <div className="mt-4 h-20 rounded bg-panel-border/30" />
    </div>
  );
}
