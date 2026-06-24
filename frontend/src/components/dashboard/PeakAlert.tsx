import Badge from '../common/Badge';
import { usePeakAlert } from '../../hooks/usePeakAlert';

export default function PeakAlert() {
  const { isActive } = usePeakAlert();

  if (!isActive) {
    return (
      <Badge variant="success">
        <span className="h-2 w-2 rounded-full bg-emerald-400" />
        Normal
      </Badge>
    );
  }

  return (
    <Badge variant="peak" pulse>
      PEAK ACTIVE
    </Badge>
  );
}

export function PeakAlertBanner() {
  const { isActive, message, overBy } = usePeakAlert();

  if (!isActive) return null;

  return (
    <div className="border-b border-peak/30 bg-peak/10 px-4 py-2 text-center text-sm text-peak-glow">
      {message}
      {overBy > 0 && ` (+${overBy.toFixed(1)}A over threshold)`}
    </div>
  );
}
