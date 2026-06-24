import type { EventLogEntry } from '../../types';
import Card from '../common/Card';
import LoadingSkeleton from '../common/LoadingSkeleton';

interface EventLogProps {
  events?: EventLogEntry[];
  loading?: boolean;
}

const levelStyles: Record<EventLogEntry['level'], { dot: string; text: string }> = {
  info: { dot: 'bg-[#3B82F6]', text: 'text-[#3B82F6]' },
  warning: { dot: 'bg-[#F97316]', text: 'text-[#F97316]' },
  success: { dot: 'bg-[#10B981]', text: 'text-[#10B981]' },
};

export default function EventLogPanel({ events, loading }: EventLogProps) {
  return (
    <Card title="이벤트 로그">
      {loading || !events ? (
        <LoadingSkeleton rows={4} />
      ) : (
        <div className="max-h-64 space-y-3 overflow-y-auto pr-2">
          {events.map((event) => {
            const style = levelStyles[event.level];
            return (
              <div
                key={event.id}
                className="flex items-start gap-3 rounded-xl border border-[#334155] bg-[#0F172A] px-4 py-3"
              >
                <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${style.dot}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-[#94A3B8]">{event.timestamp}</span>
                    <span className={`text-[10px] font-semibold uppercase ${style.text}`}>{event.level}</span>
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-[#F1F5F9]">{event.message}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
