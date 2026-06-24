import type { EventLogEntry } from '../../types';
import Card from '../common/Card';
import LoadingSkeleton from '../common/LoadingSkeleton';

interface EventLogProps {
  events?: EventLogEntry[];
  loading?: boolean;
}

const levelStyles: Record<EventLogEntry['level'], { dot: string; text: string }> = {
  info: { dot: 'bg-blue-400', text: 'text-blue-400' },
  warning: { dot: 'bg-peak', text: 'text-peak-glow' },
  success: { dot: 'bg-emerald-400', text: 'text-emerald-400' },
};

export default function EventLogPanel({ events, loading }: EventLogProps) {
  return (
    <Card title="Event Log">
      {loading || !events ? (
        <LoadingSkeleton rows={4} />
      ) : (
        <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
          {events.map((event) => {
            const style = levelStyles[event.level];
            return (
              <div
                key={event.id}
                className="flex items-start gap-3 rounded-lg border border-panel-border/60 bg-surface px-3 py-2"
              >
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-muted">{event.timestamp}</span>
                    <span className={`text-[10px] font-semibold uppercase ${style.text}`}>
                      {event.level}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-300">{event.message}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
