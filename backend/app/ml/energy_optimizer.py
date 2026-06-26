#!/usr/bin/env python3
"""
에너지 최적화 모듈
한전 일반용(을) 고압A 선택Ⅰ 계시별 요금 기반으로 최적 충방전 스케줄을 생성합니다.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional


class EnergyOptimizer:
    """에너지 최적화 클래스"""

    # 요금표 정의 (원/kWh)
    RATES = {
        "여름철": {
            "경부하": 42.50,
            "중간부하": 84.50,
            "최대부하": 147.00
        },
        "봄가을철": {
            "경부하": 42.50,
            "중간부하": 62.90,
            "최대부하": 85.60
        },
        "겨울철": {
            "경부하": 42.50,
            "중간부하": 78.80,
            "최대부하": 107.20
        }
    }

    # 한국 공휴일 목록 (2025년 기준, 간단한 예시)
    HOLIDAYS_2025 = {
        "2025-01-01", "2025-01-30", "2025-01-31",
        "2025-03-01", "2025-05-05", "2025-05-15",
        "2025-06-06", "2025-08-15", "2025-09-20",
        "2025-10-03", "2025-10-09", "2025-12-25"
    }

    def _get_season(self, dt: datetime) -> str:
        """계절 구분"""
        month = dt.month
        if 7 <= month <= 8:
            return "여름철"
        elif 3 <= month <= 6 or 9 <= month <= 10:
            return "봄가을철"
        else:
            return "겨울철"

    def _get_period(self, dt: datetime) -> str:
        """시간대 구분"""
        hour = dt.hour
        if 23 <= hour or hour < 9:
            return "경부하"
        elif (9 <= hour < 11) or (13 <= hour < 17) or (21 <= hour < 23):
            return "중간부하"
        else:
            return "최대부하"

    def _is_holiday(self, dt: datetime) -> bool:
        """공휴일 여부 확인"""
        date_str = dt.strftime("%Y-%m-%d")
        return date_str in self.HOLIDAYS_2025

    def _is_saturday(self, dt: datetime) -> bool:
        """토요일 여부 확인"""
        return dt.weekday() == 5

    def get_current_rate(self, dt: Optional[datetime] = None) -> Dict:
        """
        현재 날짜/시간/요일/공휴일 여부 반영해서 실제 적용 요금 반환
        """
        if dt is None:
            dt = datetime.now()

        season = self._get_season(dt)
        base_period = self._get_period(dt)
        is_holiday = self._is_holiday(dt)
        is_saturday = self._is_saturday(dt)

        # 특이사항 적용
        period = base_period
        if is_holiday:
            period = "경부하"
        elif is_saturday and base_period == "최대부하":
            period = "중간부하"

        rate = self.RATES[season][period]

        # 다음 시간대 계산
        next_period, next_minutes = self._get_next_period(dt)

        return {
            "rate": rate,
            "period": period,
            "season": season,
            "next_period": next_period,
            "next_period_in_minutes": next_minutes
        }

    def _get_next_period(self, dt: datetime) -> tuple:
        """다음 시간대와 남은 분 계산"""
        hour = dt.hour
        minute = dt.minute
        current_total = hour * 60 + minute

        # 시간대 경계 (분 단위)
        boundaries = [
            9 * 60,    # 09:00
            11 * 60,   # 11:00
            13 * 60,   # 13:00
            17 * 60,   # 17:00
            21 * 60,   # 21:00
            23 * 60,   # 23:00
            24 * 60    # 24:00
        ]

        # 다음 경계 찾기
        for boundary in boundaries:
            if current_total < boundary:
                next_boundary = boundary
                break
        else:
            next_boundary = 24 * 60

        next_minutes = next_boundary - current_total

        # 다음 시간대 구하기
        next_dt = dt + timedelta(minutes=next_minutes)
        next_period = self._get_period(next_dt)

        return next_period, next_minutes

    def get_24h_schedule(self, start_dt: Optional[datetime] = None) -> List[Dict]:
        """
        향후 24시간 시간대별 요금 스케줄
        """
        if start_dt is None:
            start_dt = datetime.now()

        schedule = []
        current_dt = start_dt.replace(minute=0, second=0, microsecond=0)

        for _ in range(48):  # 24시간을 30분 단위로
            rate_info = self.get_current_rate(current_dt)
            period = rate_info["period"]

            # action 결정
            if period == "경부하":
                action = "charge"
            elif period == "중간부하":
                action = "standby"
            else:
                action = "discharge"

            schedule.append({
                "time": current_dt.isoformat(),
                "rate": rate_info["rate"],
                "period": period,
                "season": rate_info["season"],
                "action": action
            })

            current_dt += timedelta(minutes=30)

        return schedule

    def calculate_optimal_schedule(
        self,
        ess_soc: float,
        ess_capacity: float,
        forecast: List[Dict]
    ) -> Dict:
        """
        ESS SOC 20~90% 범위 유지하면서 최적 충방전 스케줄 계산
        """
        schedule = self.get_24h_schedule()
        current_soc = ess_soc
        total_savings = 0.0
        total_arbitrage = 0.0
        optimal_schedule = []

        min_soc = 20.0
        max_soc = 90.0
        max_charge_rate = ess_capacity * 0.5  # 30분에 50% 충전
        max_discharge_rate = ess_capacity * 0.5

        for slot in schedule:
            action = slot["action"]
            rate = slot["rate"]
            executed_action = "standby"
            delta_soc = 0.0

            if action == "charge" and current_soc < max_soc:
                # 경부하에 충전
                possible_charge = min(
                    max_charge_rate,
                    max_soc - current_soc
                )
                if possible_charge > 0:
                    delta_soc = possible_charge
                    current_soc += possible_charge
                    executed_action = "charge"

            elif action == "discharge" and current_soc > min_soc:
                # 최대부하에 방전
                possible_discharge = min(
                    max_discharge_rate,
                    current_soc - min_soc
                )
                if possible_discharge > 0:
                    delta_soc = -possible_discharge
                    current_soc -= possible_discharge
                    executed_action = "discharge"

            optimal_schedule.append({
                **slot,
                "executed_action": executed_action,
                "soc": round(current_soc, 2),
                "delta_soc": round(delta_soc, 2)
            })

            # 차익 계산
            if executed_action == "discharge":
                # 경부하 요금으로 충전했다고 가정
                charge_rate = self.RATES["여름철"]["경부하"]
                discharge_kwh = (abs(delta_soc) / 100) * ess_capacity
                total_savings += discharge_kwh * rate
                total_arbitrage += discharge_kwh * (rate - charge_rate)

        return {
            "schedule": optimal_schedule,
            "expected_savings": round(total_savings, 2),
            "expected_arbitrage": round(total_arbitrage, 2)
        }

    def calculate_arbitrage(
        self,
        charged_kwh: float,
        discharged_kwh: float,
        charge_period: str,
        discharge_period: str,
        season: Optional[str] = None
    ) -> Dict:
        """실제 요금 기반 차익 계산"""
        if season is None:
            season = self._get_season(datetime.now())

        charge_rate = self.RATES[season][charge_period]
        discharge_rate = self.RATES[season][discharge_period]

        charge_cost = charged_kwh * charge_rate
        discharge_savings = discharged_kwh * discharge_rate
        arbitrage = discharge_savings - charge_cost
        roi = (arbitrage / charge_cost * 100) if charge_cost > 0 else 0.0

        return {
            "charge_cost": round(charge_cost, 2),
            "discharge_savings": round(discharge_savings, 2),
            "arbitrage": round(arbitrage, 2),
            "roi": round(roi, 2)
        }

    def get_realtime_recommendation(
        self,
        ess_soc: float,
        grid_current: float,
        threshold: float
    ) -> Dict:
        """현재 요금 + SOC + 그리드 상태 종합 판단"""
        rate_info = self.get_current_rate()
        period = rate_info["period"]
        rate = rate_info["rate"]
        season = rate_info["season"]

        max_rate = self.RATES[season]["최대부하"]
        min_rate = self.RATES[season]["경부하"]
        max_arbitrage = max_rate - min_rate

        # 기본 action 결정
        action = "standby"
        reason = "대기 상태"
        urgency = "normal"
        expected_benefit = "대기 중"

        if period == "경부하":
            if ess_soc < 85:
                action = "charge"
                reason = f"경부하 시간대 ({rate:.2f}원), 충전 권장"
                urgency = "normal"
                expected_benefit = f"kWh당 {max_arbitrage:.2f}원 차익 예상"
        elif period == "최대부하":
            if ess_soc > 25 and grid_current > threshold:
                action = "discharge"
                reason = f"최대부하 시간대 ({rate:.2f}원), 방전 권장"
                urgency = "high" if grid_current > threshold * 1.1 else "normal"
                expected_benefit = f"kWh당 {max_arbitrage:.2f}원 차익 예상"
        else:
            if ess_soc < 30:
                action = "charge"
                reason = "ESS SOC가 낮아 충전 권장"
                urgency = "normal"
                expected_benefit = "ESS SOC 유지"
            elif ess_soc > 80 and grid_current > threshold * 0.9:
                action = "discharge"
                reason = "ESS SOC가 높고 그리드 부하가 높아 방전 권장"
                urgency = "normal"
                expected_benefit = "그리드 부하 감소"

        if grid_current > threshold * 1.2:
            urgency = "critical"

        return {
            "action": action,
            "reason": reason,
            "urgency": urgency,
            "expected_benefit": expected_benefit,
            **rate_info
        }
