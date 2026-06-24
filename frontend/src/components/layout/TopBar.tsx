import PeakAlert from '../dashboard/PeakAlert';
import { useDashboardStore } from '../../store/dashboardStore';
import { useAuthStore } from '../../store/authStore';
import { isMockMode } from '../../config/env';

export default function TopBar() {
  const wsConnected = useDashboardStore((s) => s.wsConnected);
  const lastUpdated = useDashboardStore((s) => s.lastUpdated);
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);

  return (
    <header className="flex h-14 items-center justify-between border-b border-panel-border bg-panel px-4 sm:px-6">
      <div className="md:hidden">
        <h1 className="text-base font-bold text-white">PeakBridge</h1>
      </div>
      <div className="hidden text-xs text-muted md:block">
        {new Date().toLocaleDateString('ko-KR', {
          weekday: 'short',
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        })}
        {lastUpdated && (
          <span className="ml-3">
            Updated {new Date(lastUpdated).toLocaleTimeString('ko-KR')}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {isMockMode() ? (
          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">
            MOCK
          </span>
        ) : (
          <span
            className={`rounded px-2 py-0.5 text-[10px] font-medium ${
              wsConnected
                ? 'bg-emerald-500/15 text-emerald-400'
                : 'bg-red-500/15 text-red-400'
            }`}
          >
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        )}
        <PeakAlert />
        {user && (
          <button
            onClick={logout}
            className="text-xs text-muted hover:text-white"
            type="button"
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
}
