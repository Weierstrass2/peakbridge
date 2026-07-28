import type { DeviceInfo } from '../lib/api';

interface Props {
  devices: DeviceInfo[];
  selected: string | null; // null = 전체(최근 수신 우선)
  onSelect: (deviceId: string | null) => void;
}

/** 디바이스 선택기.
 *  구성 A(ess-demo-01, 로컬 폐쇄망 데모)와 구성 B(building-A, 3-노드)가 동시에
 *  들어올 수 있으므로 화면에서 전환할 수 있어야 한다. */
export function DevicePicker({ devices, selected, onSelect }: Props) {
  if (devices.length <= 1) return null;

  return (
    <div className="devices">
      <button className={`chip ${selected === null ? 'on' : ''}`} onClick={() => onSelect(null)} type="button">
        전체
      </button>
      {devices.map((d) => (
        <button
          key={d.device_id}
          type="button"
          className={`chip ${selected === d.device_id ? 'on' : ''}`}
          onClick={() => onSelect(d.device_id)}
        >
          {d.device_id}
          <span className="count">{d.samples}</span>
        </button>
      ))}
    </div>
  );
}
