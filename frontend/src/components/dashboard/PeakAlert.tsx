import { useState, useEffect } from 'react';
import Badge from '../common/Badge';
import { usePeakAlert } from '../../hooks/usePeakAlert';

export default function PeakAlert() {
  const { isActive } = usePeakAlert();

  if (!isActive) {
    return (
      <Badge variant="success">
        <span className="h-2 w-2 rounded-full bg-[#10B981]" />
        정상
      </Badge>
    );
  }

  return (
    <Badge variant="peak" pulse>
      피크 활성
    </Badge>
  );
}

interface PeakAlertBannerProps {
  currentPower: number;
  peakThreshold: number;
  status: boolean;
}

export function PeakAlertBanner({ currentPower, peakThreshold, status }: PeakAlertBannerProps) {
  const [showOverlay, setShowOverlay] = useState(false);
  const [gaugeProgress, setGaugeProgress] = useState(0);
  const [savingsCounter, setSavingsCounter] = useState(0);

  useEffect(() => {
    if (status) {
      setShowOverlay(true);
      // Animate gauge
      const timer1 = setTimeout(() => setGaugeProgress(43), 100);
      // Animate savings counter
      const target = 34720;
      let count = 0;
      const step = target / 50;
      const timer2 = setInterval(() => {
        count += step;
        if (count >= target) {
          setSavingsCounter(target);
          clearInterval(timer2);
        } else {
          setSavingsCounter(Math.floor(count));
        }
      }, 30);
      return () => {
        clearTimeout(timer1);
        clearInterval(timer2);
      };
    } else {
      setShowOverlay(false);
      setGaugeProgress(0);
    }
  }, [status]);

  if (!status) return null;

  const overBy = currentPower - peakThreshold;

  return (
    <>
      {/* Top Banner */}
      <div className="animate-slide-in w-full bg-[#F97316] px-6 py-4 text-center shadow-[0_0_30px_rgba(249,115,22,0.4)]">
        <div className="flex items-center justify-center gap-3">
          <div className="flex items-center gap-2">
            <span className="animate-pulse-dot h-3 w-3 rounded-full bg-white" />
            <span className="text-lg font-bold text-white">⚡ 피크쉐이빙 발동 중</span>
          </div>
          <div className="h-6 w-px bg-white/30" />
          <span className="text-white/90">그리드 과부하 감지 — ESS 자동 방전 시작</span>
        </div>
      </div>

      {/* Overlay Card */}
      {showOverlay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-slide-in">
          <div className="w-full max-w-4xl rounded-2xl border border-[#F97316]/30 bg-[#1E293B] p-8 shadow-[0_0_60px_rgba(249,115,22,0.3)]">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Gauge Section */}
              <div className="flex flex-col items-center justify-center">
                <p className="mb-4 text-lg font-semibold text-[#94A3B8]">그리드 부하 감소</p>
                <div className="relative">
                  <svg width="180" height="180" viewBox="0 0 180 180">
                    <circle cx="90" cy="90" r="75" fill="none" stroke="#334155" strokeWidth="12" strokeLinecap="round" />
                    <circle
                      cx="90"
                      cy="90"
                      r="75"
                      fill="none"
                      stroke="#F97316"
                      strokeWidth="12"
                      strokeLinecap="round"
                      strokeDasharray={`${(gaugeProgress / 100) * 2 * Math.PI * 75} ${2 * Math.PI * 75}`}
                      strokeDashoffset="0"
                      transform="rotate(-90 90 90)"
                      style={{
                        transition: 'stroke-dasharray 1.5s ease-out',
                      }}
                    />
                    <text x="90" y="100" textAnchor="middle" fill="#F1F5F9" fontSize="42" fontWeight="800">{`${gaugeProgress}%`}</text>
                  </svg>
                </div>
              </div>

              {/* Right Section */}
              <div className="flex flex-col gap-6">
                {/* Savings Counter */}
                <div className="rounded-xl bg-[#0F172A] p-5 border border-[#334155]">
                  <p className="text-sm text-[#94A3B8] mb-2">절감액 실시간 카운트</p>
                  <p className="text-4xl font-bold text-[#FBBF24]">{savingsCounter.toLocaleString()}원</p>
                </div>

                {/* Timeline Log */}
                <div className="flex-1 rounded-xl bg-[#0F172A] p-5 border border-[#334155]">
                  <p className="text-sm font-semibold text-[#94A3B8] mb-4">실시간 타임라인</p>
                  <div className="space-y-4">
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2 w-2 rounded-full bg-[#EF4444]" />
                      <div>
                        <p className="text-xs text-[#94A3B8]">19:02:34</p>
                        <p className="text-sm text-[#F1F5F9]">피크 감지 ({currentPower.toFixed(1)}A)</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2 w-2 rounded-full bg-[#34D399]" />
                      <div>
                        <p className="text-xs text-[#94A3B8]">19:02:34</p>
                        <p className="text-sm text-[#F1F5F9]">ESS 방전 시작</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2 w-2 rounded-full bg-[#F97316] animate-pulse" />
                      <div>
                        <p className="text-xs text-[#94A3B8]">19:02:35</p>
                        <p className="text-sm text-[#F1F5F9]">그리드 부하 감소 중...</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Close Button */}
                <button
                  onClick={() => setShowOverlay(false)}
                  className="w-full rounded-lg bg-[#334155] px-4 py-3 text-sm font-medium text-white hover:bg-[#475569] transition-colors"
                >
                  닫기
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
