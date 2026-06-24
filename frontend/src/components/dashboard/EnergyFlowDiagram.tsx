import type { DashboardData } from '../types';
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
        <svg viewBox="0 0 800 350" className="w-full max-w-4xl">
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
              <path d="M0,0 L0,6 L9,3 z" fill="#3B82F6"/>
            </marker>
            <marker id="arrow-orange" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L9,3 z" fill="#F97316"/>
            </marker>
          </defs>

          {/* Grid Node */}
          <g className="cursor-pointer" filter={!isPeakActive ? "url(#glow-blue)" : ""}>
            <rect x="50" y="80" width="120" height="90" rx="16" fill="#1E293B" stroke={isPeakActive ? "#334155" : "#3B82F6"} strokeWidth="2" />
            <text x="110" y="125" textAnchor="middle" fill={isPeakActive ? "#94A3B8" : "#F1F5F9"} fontSize="14" fontWeight="600">그리드</text>
            <text x="110" y="150" textAnchor="middle" fill={isPeakActive ? "#94A3B8" : "#3B82F6"} fontSize="20" fontWeight="700">{data.grid_current.toFixed(1)}A</text>
          </g>

          {/* Grid to Transformer Line */}
          <g>
            <line x1="170" y1="125" x2="250" y2="125" stroke={isPeakActive ? "#334155" : "#3B82F6"} strokeWidth="3" strokeDasharray={isPeakActive ? "5,5" : "0"} />
            {!isPeakActive && (
              <g>
                {[0,1,2,3,4].map(i => (
                  <circle key={i} r="4" fill="#3B82F6" opacity="0.8">
                    <animate attributeName="cx" from="175" to="245" dur="1.5s" repeatCount="indefinite" begin={`${i*0.3}s`} />
                    <animate attributeName="cy" values="125;125;125" dur="1.5s" />
                    <animate attributeName="opacity" values="0;1;0" dur="1.5s" repeatCount="indefinite" begin={`${i*0.3}s`} />
                  </circle>
                ))}
              </g>
            )}
          </g>

          {/* Transformer Node */}
          <g className="cursor-pointer">
            <rect x="250" y="80" width="100" height="90" rx="16" fill="#1E293B" stroke="#334155" strokeWidth="2" />
            <text x="300" y="125" textAnchor="middle" fill="#F1F5F9" fontSize="14" fontWeight="600">변압기</text>
            <text x="300" y="150" textAnchor="middle" fill="#94A3B8" fontSize="14" fontWeight="500">22kVA</text>
          </g>

          {/* Transformer to Chargers Line */}
          <g>
            <line x1="350" y1="125" x2="430" y2="125" stroke={isPeakActive ? "#F97316" : "#3B82F6"} strokeWidth="3" />
            <g>
              {[0,1,2,3,4].map(i => (
                <circle key={i} r="4" fill={isPeakActive ? "#F97316" : "#3B82F6"} opacity="0.9">
                  <animate attributeName="cx" from="355" to="425" dur="1.3s" repeatCount="indefinite" begin={`${i*0.26}s`} />
                  <animate attributeName="cy" values="125;125;125" dur="1.3s" />
                  <animate attributeName="opacity" values="0;1;0" dur="1.3s" repeatCount="indefinite" begin={`${i*0.26}s`} />
                </circle>
              ))}
            </g>
          </g>

          {/* Chargers Node */}
          <g className="cursor-pointer">
            <rect x="430" y="80" width="120" height="90" rx="16" fill="#1E293B" stroke="#A78BFA" strokeWidth="2" />
            <text x="490" y="125" textAnchor="middle" fill="#F1F5F9" fontSize="14" fontWeight="600">충전기</text>
            <text x="490" y="150" textAnchor="middle" fill="#A78BFA" fontSize="20" fontWeight="700">{chargerTotal.toFixed(1)}A</text>
            <text x="490" y="170" textAnchor="middle" fill="#94A3B8" fontSize="12">{activeCount}/{data.chargers.length} 활성</text>
          </g>

          {/* ESS Node */}
          <g className="cursor-pointer" filter={isPeakActive ? "url(#glow-orange)" : ""}>
            <rect x="300" y="220" width="100" height="90" rx="16" fill="#1E293B" stroke={isPeakActive ? "#F97316" : "#34D399"} strokeWidth="2" />
            <text x="350" y="260" textAnchor="middle" fill="#F1F5F9" fontSize="14" fontWeight="600">ESS 배터리</text>
            <text x="350" y="285" textAnchor="middle" fill={isPeakActive ? "#F97316" : "#34D399"} fontSize="20" fontWeight="700">{data.ess_soc}%</text>
            {isPeakActive && <text x="350" y="305" textAnchor="middle" fill="#F97316" fontSize="12">방전 중 {data.ess_discharge.toFixed(1)}A</text>}
          </g>

          {/* ESS to Transformer Line */}
          <g>
            <line x1="350" y1="220" x2="350" y2="170" stroke={isPeakActive ? "#F97316" : "#34D399"} strokeWidth="3" />
            {isPeakActive && (
              <g>
                {[0,1,2].map(i => (
                  <circle key={i} r="4" fill="#F97316" opacity="0.9">
                    <animate attributeName="cy" from="215" to="175" dur="1s" repeatCount="indefinite" begin={`${i*0.33}s`} />
                    <animate attributeName="cx" values="350;350;350" dur="1s" />
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
