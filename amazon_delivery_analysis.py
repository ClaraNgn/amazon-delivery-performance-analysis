"""Clean and analyze the Amazon delivery operations dataset from Kaggle.

Dataset source:
https://www.kaggle.com/datasets/vikramxd/amazon-business-research-analyst-dataset

The script produces a Tableau-ready CSV, QA summary, aggregated tables, and
portfolio figures. The 30-minute "on-time" threshold is an analytical
benchmark created for this project; it is not an Amazon service-level target.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


WEATHER_MAP = {
    0: "Cloudy",
    1: "Fog",
    2: "Sandstorms",
    3: "Stormy",
    4: "Sunny",
    6: "Windy",
    7: "Unknown",
}

TRAFFIC_MAP = {0: "High", 1: "Jam", 2: "Low", 3: "Medium", 5: "Unknown"}
ORDER_MAP = {0: "Buffet", 1: "Drinks", 2: "Meal", 3: "Snack"}
VEHICLE_MAP = {1: "Electric Scooter", 2: "Motorcycle", 3: "Scooter", 4: "Bicycle"}
FESTIVAL_MAP = {1: "No", 2: "Yes", 3: "Unknown"}

CITY_PREFIX_MAP = {
    "INDO": "Indore",
    "BANG": "Bengaluru",
    "BHP": "Bhopal",
    "JAP": "Jaipur",
    "COIMB": "Coimbatore",
    "CHEN": "Chennai",
    "GOA": "Goa",
    "KOL": "Kolkata",
    "MYS": "Mysuru",
    "HYD": "Hyderabad",
    "RANCHI": "Ranchi",
    "KOC": "Kochi",
    "KNP": "Kanpur",
    "VAD": "Vadodara",
    "PUNE": "Pune",
    "LUDH": "Ludhiana",
    "SUR": "Surat",
    "AGR": "Agra",
    "ALH": "Allahabad",
    "AURG": "Aurangabad",
    "DEH": "Dehradun",
    "MUM": "Mumbai",
}


def city_from_delivery_id(value: object) -> str:
    text = str(value).upper()
    prefix = text.split("RES", maxsplit=1)[0]
    return CITY_PREFIX_MAP.get(prefix, prefix.title() if prefix else "Unknown")


def time_to_minutes(value: object) -> float:
    """Convert H:MM text to minutes after midnight, normalizing minute=60."""
    if pd.isna(value):
        return np.nan
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{1,2})\s*", str(value))
    if not match:
        return np.nan
    hour, minute = map(int, match.groups())
    total = hour * 60 + minute
    return float(total % (24 * 60))


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    radius = 6371.0088
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2), np.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return pd.Series(2 * radius * np.arcsin(np.sqrt(a)), index=lat1.index)


def clean_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    df = raw.copy()
    rows_raw = len(df)
    duplicate_rows = int(df.duplicated(subset=["ID"]).sum())
    df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")], errors="ignore")
    df = df.drop_duplicates(subset=["ID"], keep="first").copy()

    # Replace invalid numeric values, then use transparent median/mode imputations.
    invalid_age = ~df["Delivery_person_Age"].between(18, 45)
    df.loc[invalid_age, "Delivery_person_Age"] = np.nan
    invalid_rating = ~df["Delivery_person_Ratings"].between(1, 5)
    df.loc[invalid_rating, "Delivery_person_Ratings"] = np.nan

    age_median = float(df["Delivery_person_Age"].median())
    rating_median = float(df["Delivery_person_Ratings"].median())
    multiple_mode = float(df["multiple_deliveries"].mode().iloc[0])

    df["Delivery_person_Age"] = df["Delivery_person_Age"].fillna(age_median)
    df["Delivery_person_Ratings"] = df["Delivery_person_Ratings"].fillna(rating_median)
    df["multiple_deliveries"] = df["multiple_deliveries"].fillna(multiple_mode)

    df["Weather"] = df["Weatherconditions"].map(WEATHER_MAP).fillna("Unknown")
    df["Traffic"] = df["Road_traffic_density"].map(TRAFFIC_MAP).fillna("Unknown")
    df["Order_Type"] = df["Type_of_order"].map(ORDER_MAP).fillna("Unknown")
    df["Vehicle_Type"] = df["Type_of_vehicle"].map(VEHICLE_MAP).fillna("Unknown")
    df["Festival_Flag"] = df["Festival"].map(FESTIVAL_MAP).fillna("Unknown")
    df["City_Name"] = df["Delivery_person_ID"].apply(city_from_delivery_id)

    df["Order_Minute"] = df["Time_Orderd"].apply(time_to_minutes)
    df["Pickup_Minute"] = df["Time_Order_picked"].apply(time_to_minutes)
    pickup_delay = df["Pickup_Minute"] - df["Order_Minute"]
    df["Pickup_Delay_Min"] = pickup_delay.where(pickup_delay >= 0, pickup_delay + 24 * 60)
    df.loc[df["Pickup_Delay_Min"] > 120, "Pickup_Delay_Min"] = np.nan
    df["Order_Hour"] = np.floor(df["Order_Minute"] / 60)

    df["Order_Period"] = pd.cut(
        df["Order_Hour"],
        bins=[-1, 11, 16, 20, 24],
        labels=["Morning", "Afternoon", "Evening", "Late Night"],
    ).astype("object").fillna("Unknown")

    # Coordinates in this source sometimes have an incorrect negative sign.
    for col in [
        "Restaurant_latitude",
        "Restaurant_longitude",
        "Delivery_location_latitude",
        "Delivery_location_longitude",
    ]:
        df[col] = df[col].abs()

    valid_coords = (
        df["Restaurant_latitude"].between(8, 38)
        & df["Delivery_location_latitude"].between(8, 38)
        & df["Restaurant_longitude"].between(68, 98)
        & df["Delivery_location_longitude"].between(68, 98)
    )
    df["Distance_KM"] = np.nan
    df.loc[valid_coords, "Distance_KM"] = haversine_km(
        df.loc[valid_coords, "Restaurant_latitude"],
        df.loc[valid_coords, "Restaurant_longitude"],
        df.loc[valid_coords, "Delivery_location_latitude"],
        df.loc[valid_coords, "Delivery_location_longitude"],
    )

    df["Delivery_Count"] = 1
    df["On_Time_Flag"] = (df["Time_taken(min)"] <= 30).astype(int)
    df["On_Time_30m"] = np.where(df["On_Time_Flag"] == 1, "On Time", "Over 30 Min")
    df["Delivery_Speed_Band"] = pd.cut(
        df["Time_taken(min)"],
        bins=[0, 20, 30, math.inf],
        labels=["Fast (<=20m)", "Standard (21-30m)", "Slow (>30m)"],
    ).astype(str)
    df["Age_Group"] = pd.cut(
        df["Delivery_person_Age"],
        bins=[17, 24, 29, 34, 45],
        labels=["18-24", "25-29", "30-34", "35-45"],
    ).astype(str)
    df["Rating_Band"] = pd.cut(
        df["Delivery_person_Ratings"],
        bins=[0, 4.19, 4.69, 5.0],
        labels=["Below 4.2", "4.2-4.6", "4.7-5.0"],
        include_lowest=True,
    ).astype(str)

    keep = [
        "ID",
        "Delivery_person_ID",
        "City_Name",
        "Delivery_person_Age",
        "Age_Group",
        "Delivery_person_Ratings",
        "Rating_Band",
        "Weather",
        "Traffic",
        "Vehicle_condition",
        "Order_Type",
        "Vehicle_Type",
        "multiple_deliveries",
        "Festival_Flag",
        "Time_Orderd",
        "Time_Order_picked",
        "Order_Hour",
        "Order_Period",
        "Pickup_Delay_Min",
        "Restaurant_latitude",
        "Restaurant_longitude",
        "Delivery_location_latitude",
        "Delivery_location_longitude",
        "Distance_KM",
        "Time_taken(min)",
        "Delivery_Count",
        "On_Time_Flag",
        "Delivery_Speed_Band",
        "On_Time_30m",
    ]
    df = df[keep].sort_values("ID").reset_index(drop=True)

    qa = {
        "rows_raw": rows_raw,
        "duplicate_ids_removed": duplicate_rows,
        "rows_cleaned": len(df),
        "invalid_age_values_replaced": int(invalid_age.sum()),
        "invalid_rating_values_replaced": int(invalid_rating.sum()),
        "age_imputation_median": age_median,
        "rating_imputation_median": rating_median,
        "multiple_delivery_imputation_mode": multiple_mode,
        "rows_with_valid_coordinates": int(valid_coords.sum()),
        "rows_with_valid_pickup_delay": int(df["Pickup_Delay_Min"].notna().sum()),
        "remaining_missing_values": {
            k: int(v) for k, v in df.isna().sum().items() if int(v) > 0
        },
    }
    return df, qa


def build_summaries(df: pd.DataFrame, output_dir: Path) -> dict[str, object]:
    summary_dir = output_dir / "summary_tables"
    tableau_dir = output_dir / "tableau"
    summary_dir.mkdir(parents=True, exist_ok=True)
    tableau_dir.mkdir(parents=True, exist_ok=True)

    metrics = {
        "deliveries": int(len(df)),
        "average_delivery_minutes": round(float(df["Time_taken(min)"].mean()), 2),
        "median_delivery_minutes": round(float(df["Time_taken(min)"].median()), 2),
        "on_time_rate_30m_pct": round(float((df["Time_taken(min)"] <= 30).mean() * 100), 2),
        "average_rating": round(float(df["Delivery_person_Ratings"].mean()), 2),
        "average_distance_km": round(float(df["Distance_KM"].mean()), 2),
        "average_pickup_delay_min": round(float(df["Pickup_Delay_Min"].mean()), 2),
    }

    dimensions = {
        "traffic": "Traffic",
        "weather": "Weather",
        "vehicle": "Vehicle_Type",
        "city": "City_Name",
        "order_period": "Order_Period",
        "festival": "Festival_Flag",
    }
    summary_tables: dict[str, pd.DataFrame] = {}
    for filename, column in dimensions.items():
        table = (
            df.groupby(column, dropna=False, observed=True)
            .agg(
                Deliveries=("ID", "count"),
                Avg_Delivery_Min=("Time_taken(min)", "mean"),
                Median_Delivery_Min=("Time_taken(min)", "median"),
                On_Time_Rate=("On_Time_30m", lambda s: (s == "On Time").mean()),
                Avg_Rating=("Delivery_person_Ratings", "mean"),
                Avg_Distance_KM=("Distance_KM", "mean"),
            )
            .reset_index()
        )
        table["On_Time_Rate"] = (table["On_Time_Rate"] * 100).round(2)
        for col in ["Avg_Delivery_Min", "Median_Delivery_Min", "Avg_Rating", "Avg_Distance_KM"]:
            table[col] = table[col].round(2)
        table.to_csv(summary_dir / f"performance_by_{filename}.csv", index=False)
        summary_tables[filename] = table

    pd.DataFrame(
        [
            {"KPI": "Deliveries", "Value": f"{metrics['deliveries']:,}"},
            {"KPI": "Avg Delivery", "Value": f"{metrics['average_delivery_minutes']:.2f} min"},
            {"KPI": "Within 30 Minutes", "Value": f"{metrics['on_time_rate_30m_pct']:.2f}%"},
            {"KPI": "Avg Courier Rating", "Value": f"{metrics['average_rating']:.2f} / 5"},
        ]
    ).to_csv(tableau_dir / "kpi_summary.csv", index=False)

    summary_tables["traffic"].query("Traffic != 'Unknown'").sort_values(
        "Avg_Delivery_Min", ascending=False
    ).to_csv(tableau_dir / "traffic_summary.csv", index=False)
    summary_tables["weather"].query("Weather != 'Unknown'").sort_values(
        "Avg_Delivery_Min", ascending=False
    ).to_csv(tableau_dir / "weather_summary.csv", index=False)
    summary_tables["city"].query("Deliveries >= 30").sort_values(
        "On_Time_Rate", ascending=False
    ).to_csv(tableau_dir / "city_summary.csv", index=False)

    return metrics


def create_figures(df: pd.DataFrame, metrics: dict[str, object], output_dir: Path) -> None:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", font_scale=0.95)
    blue, orange, navy = "#2A6FDB", "#FF9900", "#183B56"

    traffic = (
        df[df["Traffic"] != "Unknown"]
        .groupby("Traffic", observed=True)["Time_taken(min)"]
        .mean()
        .sort_values()
    )
    fig, ax = plt.subplots(figsize=(8, 4.5))
    traffic.plot(kind="barh", color=blue, ax=ax)
    ax.set(title="Average Delivery Time by Traffic Level", xlabel="Average minutes", ylabel="")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f", padding=4)
    fig.tight_layout()
    fig.savefig(figure_dir / "delivery_time_by_traffic.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    city = (
        df.groupby("City_Name")
        .agg(Deliveries=("ID", "count"), Avg_Time=("Time_taken(min)", "mean"), On_Time=("On_Time_30m", lambda s: (s == "On Time").mean()))
        .query("Deliveries >= 30")
        .sort_values("On_Time", ascending=False)
    )
    fig, ax = plt.subplots(figsize=(9, 5.5))
    city["On_Time"].mul(100).plot(kind="bar", color=orange, ax=ax)
    ax.set(title="30-Minute On-Time Rate by City", xlabel="", ylabel="On-time rate (%)", ylim=(0, 100))
    ax.tick_params(axis="x", rotation=40)
    fig.tight_layout()
    fig.savefig(figure_dir / "on_time_rate_by_city.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    scatter = df.dropna(subset=["Distance_KM", "Time_taken(min)"]).copy()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(scatter["Distance_KM"], scatter["Time_taken(min)"], s=18, alpha=0.35, color=blue)
    if len(scatter) > 1:
        slope, intercept = np.polyfit(scatter["Distance_KM"], scatter["Time_taken(min)"], 1)
        x = np.linspace(scatter["Distance_KM"].min(), scatter["Distance_KM"].max(), 100)
        ax.plot(x, slope * x + intercept, color=orange, linewidth=2)
    ax.set(title="Delivery Distance vs. Delivery Time", xlabel="Distance (km)", ylabel="Delivery time (minutes)")
    fig.tight_layout()
    fig.savefig(figure_dir / "distance_vs_delivery_time.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig = plt.figure(figsize=(13, 8), facecolor="#F6F8FB")
    grid = fig.add_gridspec(3, 4, height_ratios=[0.9, 2, 2], hspace=0.65, wspace=0.6)
    kpis = [
        ("Deliveries", f"{metrics['deliveries']:,}"),
        ("Avg. Delivery", f"{metrics['average_delivery_minutes']:.1f} min"),
        ("On Time <=30m", f"{metrics['on_time_rate_30m_pct']:.1f}%"),
        ("Avg. Rating", f"{metrics['average_rating']:.2f}"),
    ]
    for i, (label, value) in enumerate(kpis):
        ax = fig.add_subplot(grid[0, i])
        ax.set_facecolor("white")
        ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=22, fontweight="bold", color=navy)
        ax.text(0.5, 0.23, label, ha="center", va="center", fontsize=10, color="#5B6573")
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values(): spine.set_visible(False)

    ax1 = fig.add_subplot(grid[1:, :2])
    traffic.plot(kind="barh", color=blue, ax=ax1)
    ax1.set(title="Average Delivery Time by Traffic", xlabel="Minutes", ylabel="")
    for container in ax1.containers: ax1.bar_label(container, fmt="%.1f", padding=3)

    ax2 = fig.add_subplot(grid[1, 2:])
    speed_order = ["Fast (<=20m)", "Standard (21-30m)", "Slow (>30m)"]
    speed_counts = df["Delivery_Speed_Band"].value_counts().reindex(speed_order).fillna(0)
    speed_counts.plot(kind="bar", color=["#2DBE8C", blue, "#E85D75"], ax=ax2)
    ax2.set(title="Delivery Speed Mix", xlabel="", ylabel="Deliveries")
    ax2.tick_params(axis="x", rotation=15)

    ax3 = fig.add_subplot(grid[2, 2:])
    city["On_Time"].mul(100).sort_values(ascending=False).head(8).plot(kind="bar", color=orange, ax=ax3)
    ax3.set(title="Top City On-Time Rates", xlabel="", ylabel="Percent", ylim=(0, 100))
    ax3.tick_params(axis="x", rotation=35)

    fig.suptitle("Amazon Delivery Operations Performance", fontsize=20, fontweight="bold", color=navy, y=0.99)
    fig.savefig(figure_dir / "dashboard_preview.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=Path("."), type=Path)
    args = parser.parse_args()

    output_dir = args.output.resolve()
    (output_dir / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (output_dir / "tableau").mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(args.input)
    cleaned, qa = clean_data(raw)
    cleaned.to_csv(output_dir / "data" / "processed" / "amazon_delivery_cleaned.csv", index=False)
    cleaned.to_csv(output_dir / "tableau" / "amazon_delivery_dashboard_data.csv", index=False)

    metrics = build_summaries(cleaned, output_dir)
    create_figures(cleaned, metrics, output_dir)

    with (output_dir / "data_quality_report.json").open("w", encoding="utf-8") as handle:
        json.dump(qa, handle, indent=2)
    with (output_dir / "business_metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    print(json.dumps({"qa": qa, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
