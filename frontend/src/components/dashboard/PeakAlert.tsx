import { useState, useEffect } from 'react';
import Badge from '../common/Badge';
import { usePeakAlert } from '../../hooks/usePeakAlert';

export default function PeakAlert() {
  const { isActive } = usePeakAlert();

  if (!isActive) {
    return (
      <Badge variant="success">
        <span className="h-2 w-2 rounded-full bg-[#2EBD85]" />
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

export function PeakAlertBanner({ currentPower, status }: PeakAlertBannerProps) {
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

  return (
    <>
      {/* Top Banner */}
      <div className="animate-slide-in w-full border-y border-l-2 border-[#E8A33D] border-l-[#E8A33D] bg-[#E8A33D]/[0.10] px-6 py-3 text-center">
        <div className="flex items-center justify-center gap-3">
          <div className="flex items-center gap-2">
            <span className="animate-pulse-dot h-2 w-2 rounded-full bg-[#E8A33D]" />
            <span className="text-sm font-semibold tracking-tight text-[#E8A33D]">피크쉐이빙 발동 중</span>
          </div>
          <div className="h-4 w-px bg-[#303947]" />
          <span className="text-xs text-[#98A2B3]">그리드 과부하 감지 — ESS 자동 방전 시작</span>
        </div>
      </div>

      {/* Overlay Card */}
      {showOverlay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-slide-in">
          <div className="w-full max-w-4xl rounded-md border border-[#E8A33D]/30 bg-[#0E1116] p-8">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Gauge Section */}
              <div className="flex flex-col items-center justify-center">
                <p className="mb-4 text-lg font-semibold text-[#98A2B3]">그리드 부하 감소</p>
                <div className="relative">
                  <svg width="180" height="180" viewBox="0 0 180 180">
                    <circle cx="90" cy="90" r="75" fill="none" stroke="#222933" strokeWidth="12" strokeLinecap="round" />
                    <circle
                      cx="90"
                      cy="90"
                      r="75"
                      fill="none"
                      stroke="#E8A33D"
                      strokeWidth="12"
                      strokeLinecap="round"
                      strokeDasharray={`${(gaugeProgress / 100) * 2 * Math.PI * 75} ${2 * Math.PI * 75}`}
                      strokeDashoffset="0"
                      transform="rotate(-90 90 90)"
                      style={{
                        transition: 'stroke-dasharray 1.5s ease-out',
                      }}
                    />
                    <text x="90" y="100" textAnchor="middle" fill="#E8ECF1" fontSize="42" fontWeight="800">{`${gaugeProgress}%`}</text>
                  </svg>
                </div>
              </div>

              {/* Right Section */}
              <div className="flex flex-col gap-6">
                {/* Savings Counter */}
                <div className="rounded-md bg-[#0A0C10] p-5 border border-[#222933]">
                  <p className="text-sm text-[#98A2B3] mb-2">절감액 실시간 카운트</p>
                  <p className="text-2xl font-bold text-[#E8A33D]">{savingsCounter.toLocaleString()}원</p>
                </div>

                {/* Timeline Log */}
                <div className="flex-1 rounded-md bg-[#0A0C10] p-5 border border-[#222933]">
                  <p className="text-sm font-semibold text-[#98A2B3] mb-4">실시간 타임라인</p>
                  <div className="space-y-4">
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2 w-2 rounded-full bg-[#E5484D]" />
                      <div>
                        <p className="text-xs text-[#98A2B3]">19:02:34</p>
                        <p className="text-sm text-[#E8ECF1]">피크 감지 ({(currentPower ?? 0).toFixed(3)}A)</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2 w-2 rounded-full bg-[#2EBD85]" />
                      <div>
                        <p className="text-xs text-[#98A2B3]">19:02:34</p>
                        <p className="text-sm text-[#E8ECF1]">ESS 방전 시작</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <div className="mt-1 h-2 w-2 rounded-full bg-[#E8A33D] animate-pulse" />
                      <div>
                        <p className="text-xs text-[#98A2B3]">19:02:35</p>
                        <p className="text-sm text-[#E8ECF1]">그리드 부하 감소 중...</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Close Button */}
                <button
                  onClick={() => setShowOverlay(false)}
                  className="w-full rounded-md bg-[#222933] px-4 py-3 text-sm font-medium text-white hover:bg-[#303947] transition-colors"
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
