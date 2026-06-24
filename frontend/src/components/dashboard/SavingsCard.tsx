import Card from '../common/Card';

interface SavingsCardProps {
  todaySaved: number;
  monthSaved: number;
  co2Reduced: number;
}

export default function SavingsCard({ todaySaved, monthSaved, co2Reduced }: SavingsCardProps) {
  return (
    <Card title="절감 성과" subtitle="비용 및 환경 영향">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl bg-[#0F172A] p-5 border border-[#334155]">
          <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">오늘 절감</p>
          <p className="text-2xl font-bold text-[#FBBF24]">{todaySaved.toLocaleString()}원</p>
        </div>
        <div className="rounded-xl bg-[#0F172A] p-5 border border-[#334155]">
          <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">이번 달 절감</p>
          <p className="text-2xl font-bold text-[#3B82F6]">{monthSaved.toLocaleString()}원</p>
        </div>
        <div className="rounded-xl bg-[#0F172A] p-5 border border-[#334155]">
          <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-2">CO₂ 절감</p>
          <p className="text-2xl font-bold text-[#34D399]">{co2Reduced.toFixed(1)}kg</p>
        </div>
      </div>
    </Card>
  );
}
