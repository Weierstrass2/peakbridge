import type { RelayEvent } from '../lib/api';
import { formatTime } from '../lib/api';

export function EventLog({ events }: { events: RelayEvent[] }) {
  if (events.length === 0) {
    return <div className="empty">아직 절체 이력이 없습니다.</div>;
  }

  return (
    <div className="events">
      {events.map((e) => (
        <div key={e.id} className={`event ${e.to_state === 'NO' ? 'to-no' : 'to-nc'}`}>
          <span className="time">{formatTime(e.received_at)}</span>
          <span className="arrow">
            {e.from_state} → {e.to_state}
          </span>
          <span>{e.grid_current_a.toFixed(3)}A</span>
          <span style={{ color: 'var(--muted)' }}>
            {e.to_state === 'NO' ? '절체 (ESS 공급)' : '복귀 (한전 공급)'}
          </span>
        </div>
      ))}
    </div>
  );
}
