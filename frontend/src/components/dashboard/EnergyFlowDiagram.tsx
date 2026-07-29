import type { DashboardData } from '../../types';
import { activeChargerCount, totalChargerCurrent } from '../../mock/mockData';
import Card from '../common/Card';
import { CardSkeleton } from '../common/LoadingSkeleton';

interface EnergyFlowDiagramProps {
  data?: DashboardData;
  loading?: boolean;
}

export default function EnergyFlowDiagram({ data, loading }: EnergyFlowDiagramProps) {
  if (loading || !data) {
    return <CardSkeleton />;
  }

  const chargerTotal = totalChargerCurrent(data.chargers);
  const activeCount = activeChargerCount(data.chargers);
  const isPeakActive = data.peak_active;

  return (
    <Card title="에너지 흐름">
      <div className="flex flex-col items-center gap-6 py-4">
        {/* SVG Diagram */}
        <svg viewBox="10 35 540 295" className="w-full max-w-4xl">
          <defs>
            <filter id="glow-blue">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
            <filter id="glow-orange">
              <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
            <marker id="arrow-blue" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L9,3 z" fill="#4C8DFF"/>
            </marker>
            <marker id="arrow-orange" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L9,3 z" fill="#E8A33D"/>
            </marker>
          </defs>

          {/* Grid Node */}
          <g className="cursor-pointer" filter={!isPeakActive ? "url(#glow-blue)" : ""}>
            <rect x="20" y="45" width="150" height="105" rx="16" fill="#0E1116" stroke={isPeakActive ? "#222933" : "#4C8DFF"} strokeWidth="2.5" />
            <text x="95" y="90" textAnchor="middle" fill={isPeakActive ? "#98A2B3" : "#E8ECF1"} fontSize="17" fontWeight="600">그리드</text>
            <text x="95" y="124" textAnchor="middle" fill={isPeakActive ? "#98A2B3" : "#4C8DFF"} fontSize="26" fontWeight="700">{(data.grid_current ?? 0).toFixed(3)}A</text>
          </g>

          {/* Grid to Transformer Line */}
          <g>
            <line x1="170" y1="97" x2="230" y2="97" stroke={isPeakActive ? "#222933" : "#4C8DFF"} strokeWidth="3" strokeDasharray={isPeakActive ? "5,5" : "0"} />
            {!isPeakActive && (
              <g>
                {[0,1,2,3,4].map(i => (
                  <circle key={i} r="4" fill="#4C8DFF" opacity="0.8">
                    <animate attributeName="cx" from="175" to="225" dur="1.5s" repeatCount="indefinite" begin={`${i*0.3}s`} />
                    <animate attributeName="cy" values="97;97;97" dur="1.5s" />
                    <animate attributeName="opacity" values="0;1;0" dur="1.5s" repeatCount="indefinite" begin={`${i*0.3}s`} />
                  </circle>
                ))}
              </g>
            )}
          </g>

          {/* Transformer Node */}
          <g className="cursor-pointer">
            <rect x="230" y="45" width="100" height="105" rx="16" fill="#0E1116" stroke="#222933" strokeWidth="2.5" />
            <text x="280" y="90" textAnchor="middle" fill="#E8ECF1" fontSize="17" fontWeight="600">ATS</text>
            <text x="280" y="120" textAnchor="middle" fill="#98A2B3" fontSize="13" fontWeight="500">절체 릴레이</text>
          </g>

          {/* Transformer to Chargers Line */}
          <g>
            <line x1="330" y1="97" x2="390" y2="97" stroke={isPeakActive ? "#E8A33D" : "#4C8DFF"} strokeWidth="3" />
            <g>
              {[0,1,2,3,4].map(i => (
                <circle key={i} r="4" fill={isPeakActive ? "#E8A33D" : "#4C8DFF"} opacity="0.9">
                  <animate attributeName="cx" from="335" to="385" dur="1.3s" repeatCount="indefinite" begin={`${i*0.26}s`} />
                  <animate attributeName="cy" values="97;97;97" dur="1.3s" />
                  <animate attributeName="opacity" values="0;1;0" dur="1.3s" repeatCount="indefinite" begin={`${i*0.26}s`} />
                </circle>
              ))}
            </g>
          </g>

          {/* Chargers Node */}
          <g className="cursor-pointer">
            <rect x="390" y="45" width="150" height="105" rx="16" fill="#0E1116" stroke="#9B8AFB" strokeWidth="2.5" />
            <text x="465" y="80" textAnchor="middle" fill="#E8ECF1" fontSize="17" fontWeight="600">충전기</text>
            <text x="465" y="112" textAnchor="middle" fill="#9B8AFB" fontSize="26" fontWeight="700">{(chargerTotal ?? 0).toFixed(2)}A</text>
            <text x="465" y="138" textAnchor="middle" fill="#98A2B3" fontSize="13">{activeCount}/{(data.chargers ?? []).length} 활성</text>
          </g>

          {/* ESS Node */}
          <g className="cursor-pointer" filter={isPeakActive ? "url(#glow-orange)" : ""}>
            <rect x="205" y="215" width="150" height="100" rx="16" fill="#0E1116" stroke={isPeakActive ? "#E8A33D" : "#2EBD85"} strokeWidth="2.5" />
            <text x="280" y="252" textAnchor="middle" fill="#E8ECF1" fontSize="17" fontWeight="600">ESS 배터리</text>
            <text x="280" y="286" textAnchor="middle" fill={isPeakActive ? "#E8A33D" : "#2EBD85"} fontSize="26" fontWeight="700">{data.ess_soc ?? 0}%</text>
            {isPeakActive && <text x="280" y="306" textAnchor="middle" fill="#E8A33D" fontSize="13">방전 중 {(data.ess_discharge ?? 0).toFixed(2)}A</text>}
          </g>

          {/* ESS to Transformer Line */}
          <g>
            <line x1="280" y1="215" x2="280" y2="150" stroke={isPeakActive ? "#E8A33D" : "#2EBD85"} strokeWidth="3" />
            <text x="292" y="188" fill="#98A2B3" fontSize="12">인버터 220V</text>
            {isPeakActive && (
              <g>
                {[0,1,2].map(i => (
                  <circle key={i} r="4" fill="#E8A33D" opacity="0.9">
                    <animate attributeName="cy" from="210" to="155" dur="1s" repeatCount="indefinite" begin={`${i*0.33}s`} />
                    <animate attributeName="cx" values="280;280;280" dur="1s" />
                    <animate attributeName="opacity" values="0;1;0" dur="1s" repeatCount="indefinite" begin={`${i*0.33}s`} />
                  </circle>
                ))}
              </g>
            )}
          </g>
        </svg>
      </div>
    </Card>
  );
}
