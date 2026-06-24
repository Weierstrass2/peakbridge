import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import ChargerGrid from '../components/dashboard/ChargerGrid';
import Card from '../components/common/Card';
import { CardSkeleton } from '../components/common/LoadingSkeleton';
import { useDashboard } from '../hooks/useDashboard';

// Mock chart data for a charger
const mockChargerChart = Array.from({ length: 24 }, (_, i) => ({
  time: `${i.toString().padStart(2, '0')}:00`,
  current: 5 + Math.random() * 5,
}));

// Brand distribution data
const brandData = [
  { name: '차지비', value: 45, color: '#3B82F6' },
  { name: '에버온', value: 30, color: '#A78BFA' },
  { name: '파워큐브', value: 25, color: '#34D399' },
];

const mockChargerDetails = [
  { id: 'CH-01', brand: '차지비', current: 7.2, voltage: 220, status: 'charging', todayUsage: 12.4 },
  { id: 'CH-02', brand: '에버온', current: 6.8, voltage: 220, status: 'charging', todayUsage: 11.8 },
  { id: 'CH-03', brand: '파워큐브', current: 0, voltage: null, status: 'idle', todayUsage: 8.2 },
  { id: 'CH-04', brand: '차지비', current: 4.1, voltage: 220, status: 'charging', todayUsage: 9.6 },
];

export default function ChargersPage() {
  const { dashboard, isLoading, isError } = useDashboard();
  const [selectedBuilding, setSelectedBuilding] = useState('A단지');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedCharger, setSelectedCharger] = useState<string | null>(null);

  if (isError) {
    return <Card title="오류" subtitle="충전기 데이터를 불러올 수 없습니다" />;
  }

  if (isLoading || !dashboard) {
    return <CardSkeleton />;
  }

  const selectedChargerData = mockChargerDetails.find(c => c.id === selectedCharger);

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <label className="text-xs text-[#94A3B8] mb-1 block">단지 선택</label>
          <select
            value={selectedBuilding}
            onChange={(e) => setSelectedBuilding(e.target.value)}
            className="rounded-lg border border-[#334155] bg-[#1E293B] px-4 py-2 text-sm text-[#F1F5F9] outline-none focus:border-[#3B82F6]"
          >
            <option value="A단지">A단지</option>
            <option value="B단지">B단지</option>
            <option value="C단지">C단지</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-[#94A3B8] mb-1 block">상태 필터</label>
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="rounded-lg border border-[#334155] bg-[#1E293B] px-4 py-2 text-sm text-[#F1F5F9] outline-none focus:border-[#3B82F6]"
          >
            <option value="all">전체</option>
            <option value="charging">충전 중</option>
            <option value="idle">대기</option>
            <option value="error">오류</option>
          </select>
        </div>
      </div>

      {/* Charger Grid */}
      <ChargerGrid chargers={dashboard.chargers} />

      {/* Table + Side Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Charger Table */}
        <div className="lg:col-span-2">
          <Card title="충전기 목록">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-[#334155]">
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">충전기 ID</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">브랜드</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">전류</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">전압</th>
                    <th className="pb-4 pr-4 text-xs font-semibold text-[#94A3B8]">상태</th>
                    <th className="pb-4 text-xs font-semibold text-[#94A3B8]">오늘 사용량</th>
                  </tr>
                </thead>
                <tbody>
                  {mockChargerDetails.map((c) => (
                    <tr
                      key={c.id}
                      onClick={() => setSelectedCharger(c.id)}
                      className={`border-b border-[#334155]/50 cursor-pointer transition-all hover:bg-[#334155]/20 ${
                        selectedCharger === c.id ? 'bg-[#334155]/30' : ''
                      }`}
                    >
                      <td className="py-4 pr-4 font-medium text-[#F1F5F9]">{c.id}</td>
                      <td className="py-4 pr-4 text-[#94A3B8]">{c.brand}</td>
                      <td className="py-4 pr-4 tabular-nums">{c.current.toFixed(1)}A</td>
                      <td className="py-4 pr-4 text-[#94A3B8]">{c.voltage ? `${c.voltage}V` : '-'}</td>
                      <td className="py-4 pr-4">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                            c.status === 'charging'
                              ? 'bg-[#10B981]/10 text-[#10B981]'
                              : c.status === 'idle'
                              ? 'bg-[#334155]/50 text-[#94A3B8]'
                              : 'bg-[#EF4444]/10 text-[#EF4444]'
                          }`}
                        >
                          {c.status === 'charging' ? '🟢 충전 중' : c.status === 'idle' ? '⚫ 대기' : '🔴 오류'}
                        </span>
                      </td>
                      <td className="py-4 text-[#FBBF24] font-semibold">{c.todayUsage.toFixed(1)}kWh</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Side Panel */}
        <div className="space-y-6">
          {selectedChargerData ? (
            <>
              <Card title={`${selectedChargerData.id} 상세 정보`}>
                <div className="space-y-4">
                  <div className="rounded-xl bg-[#0F172A] p-4 border border-[#334155]">
                    <p className="text-xs text-[#94A3B8] mb-1">24시간 전류</p>
                    <div className="h-40">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={mockChargerChart}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                          <XAxis dataKey="time" hide />
                          <YAxis hide domain={[0, 15]} />
                          <Line
                            type="monotone"
                            dataKey="current"
                            stroke="#A78BFA"
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl bg-[#0F172A] p-4 border border-[#334155]">
                      <p className="text-xs text-[#94A3B8] mb-1">총 충전량</p>
                      <p className="text-xl font-bold text-[#F1F5F9]">{selectedChargerData.todayUsage.toFixed(1)}kWh</p>
                    </div>
                    <div className="rounded-xl bg-[#0F172A] p-4 border border-[#334155]">
                      <p className="text-xs text-[#94A3B8] mb-1">피크쉐이빙 기여</p>
                      <p className="text-xl font-bold text-[#34D399]">23%</p>
                    </div>
                  </div>
                </div>
              </Card>
            </>
          ) : (
            <Card title="충전기 선택">
              <p className="text-sm text-[#94A3B8]">충전기를 선택하면 상세 정보가 표시됩니다.</p>
            </Card>
          )}

          {/* Brand Distribution */}
          <Card title="브랜드별 분포">
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={brandData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {brandData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1E293B',
                      border: '1px solid #334155',
                      borderRadius: 12,
                    }}
                  />
                  <Legend verticalAlign="bottom" height={36} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
