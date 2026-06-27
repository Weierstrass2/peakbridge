from __future__ import annotations

from pathlib import Path

import pandas as pd


TEMP_PATH = Path("data/ta_20260628130624.csv")
KPX_PROCESSED_PATH = Path("data/kpx_processed.csv")
KPX_DEMAND_PATH = Path("data/kpx_demand.csv")
PRICE_OUTPUT = Path("data/ev2gym_prices.csv")
LOAD_OUTPUT = Path("data/ev2gym_loads.csv")
TEMP_OUTPUT = Path("data/ev2gym_temps.csv")


def get_temp_weight(temp: float) -> float:
    if temp >= 33:
        return 1.4
    if temp >= 28:
        return 1.2
    if temp <= -10:
        return 1.35
    if temp <= 0:
        return 1.2
    return 1.0


def get_price(hour: int, weekday: int, month: int) -> float:
    if month in [7, 8]:
        peak, mid, off = 147.0, 84.5, 42.5
    elif month in [11, 12, 1, 2]:
        peak, mid, off = 107.2, 78.8, 42.5
    else:
        peak, mid, off = 85.6, 62.9, 42.5

    if weekday == 6:
        return off / 1000

    if weekday == 5:
        if 11 <= hour <= 13 or 17 <= hour <= 21:
            return mid / 1000
        if 23 <= hour or hour < 9:
            return off / 1000
        return mid / 1000

    if 11 <= hour <= 13 or 17 <= hour <= 21:
        return peak / 1000
    if 9 <= hour <= 11 or 13 <= hour <= 17 or 21 <= hour <= 23:
        return mid / 1000
    return off / 1000


def load_temperature_daily() -> pd.DataFrame:
    df_temp = pd.read_csv(
        TEMP_PATH,
        encoding="euc-kr",
        skiprows=7,
        skipinitialspace=True,
    )
    df_temp["날짜"] = df_temp["날짜"].str.strip()
    df_temp["날짜"] = pd.to_datetime(df_temp["날짜"])
    df_temp = df_temp.set_index("날짜")

    df_temp = df_temp[["평균기온(℃)", "최저기온(℃)", "최고기온(℃)"]].copy()
    df_temp.columns = ["temperature", "min_temp", "max_temp"]

    for col in df_temp.columns:
        df_temp[col] = pd.to_numeric(df_temp[col], errors="coerce")

    return df_temp.sort_index().dropna(subset=["temperature"])


def expand_temp_to_5min(df_temp_daily: pd.DataFrame) -> pd.DataFrame:
    hourly_rows: list[dict[str, object]] = []

    for day, row in df_temp_daily.iterrows():
        for hour in range(24):
            ts = pd.Timestamp(day) + pd.Timedelta(hours=hour)
            hourly_rows.append(
                {
                    "timestamp": ts,
                    "temperature": float(row["temperature"]),
                    "max_temp": float(row["max_temp"]),
                    "min_temp": float(row["min_temp"]),
                }
            )

    hourly_df = pd.DataFrame(hourly_rows).set_index("timestamp").sort_index()
    full_index = pd.date_range(
        start=hourly_df.index.min(),
        end=hourly_df.index.max() + pd.Timedelta(minutes=55),
        freq="5min",
    )

    temp_5min = hourly_df.reindex(full_index).ffill()
    temp_5min.index.name = "timestamp"
    return temp_5min


def load_kpx_processed_hourly() -> pd.DataFrame:
    df_kpx = pd.read_csv(KPX_PROCESSED_PATH, parse_dates=["ds"]).sort_values("ds")
    if "kpx_demand_mwh" not in df_kpx.columns:
        raise ValueError("kpx_processed.csv에 kpx_demand_mwh 컬럼이 없습니다.")
    return (
        df_kpx[["ds", "kpx_demand_mwh"]]
        .rename(columns={"ds": "timestamp", "kpx_demand_mwh": "kpx_demand"})
        .set_index("timestamp")
        .sort_index()
    )


def load_kpx_demand_hourly() -> pd.DataFrame:
    df = pd.read_csv(KPX_DEMAND_PATH)
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col].astype(str).str.strip(), errors="coerce")
    df = df.dropna(subset=[date_col]).copy()

    hour_cols = [
        col for col in df.columns if str(col).endswith("시") and str(col)[:-1].isdigit()
    ]
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        base_date = pd.Timestamp(row[date_col])
        for hour_col in hour_cols:
            hour_num = int(str(hour_col).replace("시", ""))
            ts = base_date + pd.Timedelta(hours=hour_num - 1)
            rows.append(
                {
                    "timestamp": ts,
                    "kpx_demand": pd.to_numeric(row[hour_col], errors="coerce"),
                }
            )

    return pd.DataFrame(rows).dropna().set_index("timestamp").sort_index()


def choose_kpx_hourly_source() -> tuple[pd.DataFrame, str]:
    processed = load_kpx_processed_hourly()
    demand = load_kpx_demand_hourly()

    processed_min, processed_max = processed.index.min(), processed.index.max()
    demand_min, demand_max = demand.index.min(), demand.index.max()

    if demand_min < processed_min or demand_max > processed_max:
        return demand, "kpx_demand.csv"
    return processed, "kpx_processed.csv"


def load_kpx_to_5min() -> tuple[pd.DataFrame, str]:
    kpx_hourly, source_name = choose_kpx_hourly_source()

    # 마지막 시각 뒤 1시간을 하나 더 붙여 마지막 55분 구간도 5분 단위로 보간 가능하게 한다.
    last_ts = kpx_hourly.index.max()
    last_val = float(kpx_hourly.iloc[-1]["kpx_demand"])
    kpx_hourly.loc[last_ts + pd.Timedelta(hours=1)] = last_val
    kpx_hourly = kpx_hourly.sort_index()

    full_index = pd.date_range(
        start=kpx_hourly.index.min(),
        end=kpx_hourly.index.max() - pd.Timedelta(minutes=5),
        freq="5min",
    )

    kpx_5min = kpx_hourly.reindex(kpx_hourly.index.union(full_index)).sort_index()
    kpx_5min["kpx_demand"] = kpx_5min["kpx_demand"].interpolate(method="time")
    kpx_5min = kpx_5min.reindex(full_index)
    kpx_5min.index.name = "timestamp"
    return kpx_5min, source_name


def build_outputs() -> pd.DataFrame:
    temp_5min = expand_temp_to_5min(load_temperature_daily())
    kpx_5min, source_name = load_kpx_to_5min()

    merged = kpx_5min.join(temp_5min, how="inner").reset_index()
    merged["timestamp"] = pd.to_datetime(merged["timestamp"])

    # 전국 평균 60,000MW 기준 / 200만 세대 * 300세대 -> 아파트 규모 부하(kW)
    merged["base_load"] = (merged["kpx_demand"] / 2_000_000.0) * 300.0 * 1000.0
    merged["temp_weight"] = merged["temperature"].apply(get_temp_weight)
    merged["load"] = merged["base_load"] * merged["temp_weight"]

    merged["price"] = merged.apply(
        lambda row: get_price(
            int(row["timestamp"].hour),
            int(row["timestamp"].weekday()),
            int(row["timestamp"].month),
        ),
        axis=1,
    )

    merged.attrs["kpx_source"] = source_name
    return merged


def save_outputs(df: pd.DataFrame) -> None:
    PRICE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    df.assign(timestamp=df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"))[
        ["timestamp", "price"]
    ].to_csv(PRICE_OUTPUT, index=False)

    df.assign(timestamp=df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"))[
        ["timestamp", "load"]
    ].to_csv(LOAD_OUTPUT, index=False)

    df.assign(timestamp=df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"))[
        ["timestamp", "temperature", "max_temp", "min_temp"]
    ].to_csv(TEMP_OUTPUT, index=False)


def print_stats(df: pd.DataFrame) -> None:
    start = df["timestamp"].min().strftime("%Y-%m-%d %H:%M")
    end = df["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    summer_avg = df[df["timestamp"].dt.month.isin([7, 8])]["load"].mean()
    winter_avg = df[df["timestamp"].dt.month.isin([11, 12, 1, 2])]["load"].mean()
    max_temp = df["max_temp"].max()
    min_temp = df["min_temp"].min()
    min_price = df["price"].min()
    max_price = df["price"].max()

    print(f"총 행 수: {len(df)}")
    print(f"기간: {start} ~ {end}")
    print(f"여름 평균 부하: {summer_avg:.2f}")
    print(f"겨울 평균 부하: {winter_avg:.2f}")
    print(f"최고 기온: {max_temp:.2f}")
    print(f"최저 기온: {min_temp:.2f}")
    print(f"가격 범위: {min_price:.4f} ~ {max_price:.4f}")


def main() -> None:
    if not TEMP_PATH.exists():
        raise FileNotFoundError(f"기온 파일이 없습니다: {TEMP_PATH}")
    if not KPX_PROCESSED_PATH.exists():
        raise FileNotFoundError(f"KPX 파일이 없습니다: {KPX_PROCESSED_PATH}")
    if not KPX_DEMAND_PATH.exists():
        raise FileNotFoundError(f"KPX 파일이 없습니다: {KPX_DEMAND_PATH}")

    df = build_outputs()
    save_outputs(df)

    print(f"KPX 소스 사용: {df.attrs.get('kpx_source', 'unknown')}")
    print(f"저장 완료: {PRICE_OUTPUT}")
    print(f"저장 완료: {LOAD_OUTPUT}")
    print(f"저장 완료: {TEMP_OUTPUT}")
    print(df[["timestamp", "price", "load", "temperature"]].head(3).to_string(index=False))
    print_stats(df)


if __name__ == "__main__":
    main()
