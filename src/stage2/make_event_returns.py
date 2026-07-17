import argparse
from pathlib import Path
import pandas as pd
import numpy as np

def make_event_returns(input_csv, output_csv):
    # =========================
    # Load daily price data
    # =========================
    df = pd.read_csv(input_csv)

    required = {"symbol", "date", "adjClose"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"])

# =========================
# Compute daily log returns
# =========================
    df["log_return"] = np.log(df["adjClose"] / df.groupby("symbol")["adjClose"].shift(1))
    df = df.dropna(subset=["log_return"])

# =========================
# Confirmed event windows
#
# Returns are close-to-close event-window returns. Because each daily return is
# labeled by its ending date, a window from start_date to end_date includes
# returns with start_date < date <= end_date.
# =========================

# 1. Initial tariff-driven decline
    s1_decline = (
        df[(df["date"] > "2025-02-19") & (df["date"] <= "2025-03-13")]
        .groupby("symbol")["log_return"]
        .sum()
        .rename("S1_Decline")
    )

# 2. Escalation collapse
    s2_escalation = (
    df[(df["date"] > "2025-03-25") & (df["date"] <= "2025-04-08")]
    .groupby("symbol")["log_return"]
    .sum()
    .rename("S2_Escalation_Collapse")
    )

# 3. Policy shock jump
    s3_jump = (
    df[(df["date"] > "2025-04-08") & (df["date"] <= "2025-04-09")]
    .groupby("symbol")["log_return"]
    .sum()
    .rename("S3_Policy_Shock_Jump")
    )

# 4. Uncertainty-driven decline
    s4_uncertainty = (
    df[(df["date"] > "2025-04-09") & (df["date"] <= "2025-04-21")]
    .groupby("symbol")["log_return"]
    .sum()
    .rename("S4_Uncertainty_Decline")
    )

# 5. Long-term adjustment
    s5_long_term = (
    df[(df["date"] > "2025-02-19") & (df["date"] <= "2025-12-31")]
    .groupby("symbol")["log_return"]
    .sum()
    .rename("S5_Long_Term_Adjustment")
    )

# =========================
# Combine and save
# =========================
    event_returns = pd.concat(
        [
            s1_decline,
            s2_escalation,
            s3_jump,
            s4_uncertainty,
            s5_long_term,
        ],
        axis=1
    ).reset_index()

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    event_returns.to_csv(output_csv, index=False)

    print(f"✅ {output_csv} created")
    print("Columns:")
    print(event_returns.columns.tolist())
    print("\nPreview:")
    print(event_returns.head())
    return event_returns


def parse_args():
    parser = argparse.ArgumentParser(description="Compute five tariff event-window log returns.")
    parser.add_argument("--in", dest="input_csv", default="data/derived/sp500_daily_prices.csv")
    parser.add_argument("--out", dest="output_csv", default="data/derived/event_returns.csv")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    make_event_returns(args.input_csv, args.output_csv)
