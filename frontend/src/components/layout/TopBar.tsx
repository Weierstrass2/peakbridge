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
    <header className="flex h-14 items-center justify-between border-b border-[#222933] bg-[#0E1116] px-4 sm:px-6">
      <div className="md:hidden">
        <h1 className="text-base font-bold text-[#E8ECF1]">PeakBridge</h1>
      </div>
      <div className="hidden text-xs text-[#98A2B3] md:block">
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
          <span className="rounded-full bg-[#E8A33D]/15 px-3 py-1 text-[10px] font-medium text-[#E8A33D]">
            MOCK
          </span>
        ) : (
          <span
            className={`rounded-full px-3 py-1 text-[10px] font-medium ${
              wsConnected
                ? 'bg-[#2EBD85]/15 text-[#2EBD85]'
                : 'bg-[#E5484D]/15 text-[#E5484D]'
            }`}
          >
            {wsConnected ? 'LIVE' : '폴링 모드'}
          </span>
        )}
        <PeakAlert />
        {user && (
          <button
            onClick={logout}
            className="text-xs text-[#98A2B3] hover:text-[#E8ECF1]"
            type="button"
          >
            Logout
          </button>
        )}
      </div>
    </header>
  );
}
