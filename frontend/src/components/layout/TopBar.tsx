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
    <header className="flex h-14 items-center justify-between border-b border-[#334155] bg-[#1E293B] px-4 sm:px-6">
      <div className="md:hidden">
        <h1 className="text-base font-bold text-[#F1F5F9]">PeakBridge</h1>
      </div>
      <div className="hidden text-xs text-[#94A3B8] md:block">
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
          <span className="rounded-full bg-[#FBBF24]/15 px-3 py-1 text-[10px] font-medium text-[#FBBF24]">
            MOCK
          </span>
        ) : (
          <span
            className={`rounded-full px-3 py-1 text-[10px] font-medium ${
              wsConnected
                ? 'bg-[#10B981]/15 text-[#10B981]'
                : 'bg-[#EF4444]/15 text-[#EF4444]'
            }`}
          >
            {wsConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        )}
        <PeakAlert />
        {user && (
          <button
            onClick={logout}
            className="text-xs text-[#94A3B8] hover:text-[#F1F5F9]"
            type="button"
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
}
