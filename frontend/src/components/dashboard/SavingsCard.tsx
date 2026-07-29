import Card from '../common/Card';
import { formatCo2Kg } from '../../utils/format';

interface SavingsCardProps {
  todaySaved: number;
  monthSaved: number;
  co2Reduced: number;
}

export default function SavingsCard({ todaySaved, monthSaved, co2Reduced }: SavingsCardProps) {
  return (
    <Card title="절감 성과" subtitle="비용 및 환경 영향">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-md bg-[#0A0C10] p-5 border border-[#222933]">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">오늘 절감</p>
          <p className="text-2xl font-bold text-[#E8A33D]">{(todaySaved ?? 0).toLocaleString()}원</p>
        </div>
        <div className="rounded-md bg-[#0A0C10] p-5 border border-[#222933]">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">이번 달 절감</p>
          <p className="text-2xl font-bold text-[#4C8DFF]">{(monthSaved ?? 0).toLocaleString()}원</p>
        </div>
        <div className="rounded-md bg-[#0A0C10] p-5 border border-[#222933]">
          <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3] mb-2">CO₂ 절감</p>
          <p className="text-2xl font-bold text-[#2EBD85]">{formatCo2Kg(co2Reduced)}</p>
        </div>
      </div>
    </Card>
  );
}
