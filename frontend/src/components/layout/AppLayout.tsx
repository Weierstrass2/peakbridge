import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import { PeakAlertBanner } from '../dashboard/PeakAlert';
import { mockDashboardData } from '../../mock/mockData';

// 만약 프로젝트 내부에서 웹소켓 훅을 사용 중이시라면 아래 주석을 해제하여 사용하세요.
// import { useWebSocket } from '../../hooks/useWebSocket';

export const AppLayout: React.FC = () => {
  // 웹소켓 실시간 데이터가 연결되기 전이므로, 우선 mock 데이터를 기준으로 렌더링합니다.
  // 나중에 실서버 연결시 웹소켓 훅의 데이터로 교체하시면 됩니다.
  const data = mockDashboardData;

  return (
    <div className="min-h-screen bg-[#0F172A] text-[#F1F5F9] flex">
      {/* 1. 고정 사이드바 */}
      <Sidebar />

      {/* 2. 우측 메인 영역 (사이드바 너비인 pl-64만큼 여백 확보) */}
      <div className="flex-1 pl-64 flex flex-col min-h-screen">
        {/* 3. 상단 네비게이션 바 */}
        <TopBar />

        {/* 4. 메인 대시보드 콘텐츠 영역 (상단바 높이인 pt-24만큼 여백 확보) */}
        <main className="flex-1 p-8 pt-24 space-y-6 max-w-[1600px] w-full mx-auto">
          {/* 전력 피크 경고/제어 상태 알림 배너 */}
          <PeakAlertBanner
            currentPower={data.grid_current}
            peakThreshold={data.peak_threshold}
            status={data.peak_active}
          />

          {/* 대시보드 메인이나 충전기 관제 등 각 페이지 컴포넌트가 렌더링되는 슬롯 */}
          <div className="w-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};

// 라우터 파일(App.tsx 등)에서 어떻게 불러오든 에러가 나지 않도록 default export도 함께 제공합니다.
export default AppLayout;