"""
Blood Sugar Level Analyser
===========================
Reads blood glucose readings from a CSV file, calculates key metrics,
identifies abnormal values, and produces a multi-panel summary plot.

CSV expected columns:
  patient_id, timestamp, blood_sugar_mg_dl, measurement_type, notes

Clinical reference ranges (mg/dL) used in this programme:
  Fasting     : Normal  70–99  |  Pre-diabetic 100–125  |  Diabetic ≥126
  Post-meal   : Normal  <140   |  Pre-diabetic 140–199  |  Diabetic ≥200
  Hypoglycaemia threshold : <70  (dangerously low)
  Critical high           : >300 (medical emergency)

DISCLAIMER: Educational model only. Not for real clinical decisions.
"""

import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')           # non-interactive backend for file output
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from datetime import datetime


# ─── Clinical Thresholds (mg/dL) ─────────────────────────────────────────────

THRESHOLDS = {
    "hypo_critical":   60,    # Critical hypoglycaemia
    "hypo_warning":    70,    # Hypoglycaemia
    "fasting_normal":  99,    # Upper normal fasting
    "fasting_pre":    125,    # Upper pre-diabetic fasting
    "post_normal":    140,    # Upper normal post-meal
    "post_pre":       199,    # Upper pre-diabetic post-meal
    "hyper_critical": 300,    # Critical hyperglycaemia
}


# ─── Step 1: Load & Validate CSV ─────────────────────────────────────────────

def load_csv(filepath: str) -> pd.DataFrame:
    """Load the CSV file and validate required columns."""
    required = {"patient_id", "timestamp", "blood_sugar_mg_dl"}
    try:
        df = pd.read_csv(filepath, parse_dates=["timestamp"])
    except FileNotFoundError:
        sys.exit(f"❌ File not found: {filepath}")
    except Exception as e:
        sys.exit(f"❌ Could not read CSV: {e}")

    missing = required - set(df.columns)
    if missing:
        sys.exit(f"❌ Missing required columns: {missing}")

    # Drop rows with missing blood sugar values
    before = len(df)
    df = df.dropna(subset=["blood_sugar_mg_dl"])
    dropped = before - len(df)
    if dropped:
        print(f"⚠  Dropped {dropped} row(s) with missing blood_sugar values.")

    df["blood_sugar_mg_dl"] = pd.to_numeric(df["blood_sugar_mg_dl"], errors="coerce")
    df = df.dropna(subset=["blood_sugar_mg_dl"])
    df = df.sort_values(["patient_id", "timestamp"]).reset_index(drop=True)

    print(f"✅ Loaded {len(df)} readings for {df['patient_id'].nunique()} patient(s).\n")
    return df


# ─── Step 2: Classify Each Reading ───────────────────────────────────────────

def classify_reading(row) -> str:
    """
    Classify a single blood sugar reading as:
    CRITICAL_LOW / LOW / NORMAL / ELEVATED / HIGH / CRITICAL_HIGH
    based on measurement type and clinical thresholds.
    """
    val  = row["blood_sugar_mg_dl"]
    mtype = str(row.get("measurement_type", "")).lower()

    if val < THRESHOLDS["hypo_critical"]:
        return "CRITICAL_LOW"
    if val < THRESHOLDS["hypo_warning"]:
        return "LOW"
    if val > THRESHOLDS["hyper_critical"]:
        return "CRITICAL_HIGH"

    if "fasting" in mtype or "pre" in mtype:
        if val <= THRESHOLDS["fasting_normal"]:
            return "NORMAL"
        if val <= THRESHOLDS["fasting_pre"]:
            return "ELEVATED"
        return "HIGH"
    else:
        # post-meal or unknown
        if val < THRESHOLDS["post_normal"]:
            return "NORMAL"
        if val < THRESHOLDS["post_pre"]:
            return "ELEVATED"
        return "HIGH"


STATUS_COLORS = {
    "CRITICAL_LOW":  "#d62728",
    "LOW":           "#ff7f0e",
    "NORMAL":        "#2ca02c",
    "ELEVATED":      "#bcbd22",
    "HIGH":          "#ff7f0e",
    "CRITICAL_HIGH": "#d62728",
}


# ─── Step 3: Compute Metrics ─────────────────────────────────────────────────

def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate per-patient summary statistics."""
    rows = []
    for pid, group in df.groupby("patient_id"):
        vals = group["blood_sugar_mg_dl"]
        rows.append({
            "Patient":        pid,
            "Readings":       len(vals),
            "Mean (mg/dL)":   round(vals.mean(), 1),
            "Median (mg/dL)": round(vals.median(), 1),
            "Std Dev":        round(vals.std(), 1),
            "Min (mg/dL)":    int(vals.min()),
            "Max (mg/dL)":    int(vals.max()),
            "% Normal":       round((group["status"] == "NORMAL").mean() * 100, 1),
            "% Elevated":     round((group["status"] == "ELEVATED").mean() * 100, 1),
            "% High":         round((group["status"] == "HIGH").mean() * 100, 1),
            "Abnormal Count": int((group["status"].isin(
                                   ["LOW","CRITICAL_LOW","HIGH","CRITICAL_HIGH"])).sum()),
        })
    return pd.DataFrame(rows)


# ─── Step 4: Identify Unusual Values ─────────────────────────────────────────

def find_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag unusual values using two complementary methods:
    1. Clinical thresholds (LOW / HIGH / CRITICAL)
    2. Statistical outliers: values beyond mean ± 2 SD per patient
    """
    anomalies = []

    for pid, group in df.groupby("patient_id"):
        mean = group["blood_sugar_mg_dl"].mean()
        std  = group["blood_sugar_mg_dl"].std()

        for _, row in group.iterrows():
            reasons = []
            val = row["blood_sugar_mg_dl"]

            # Clinical flags
            if row["status"] in ("CRITICAL_LOW", "CRITICAL_HIGH"):
                reasons.append(f"Clinical: {row['status']}")
            elif row["status"] in ("LOW", "HIGH"):
                reasons.append(f"Clinical: {row['status']}")

            # Statistical outlier
            if std > 0 and abs(val - mean) > 2 * std:
                z = (val - mean) / std
                reasons.append(f"Statistical outlier (z={z:.1f})")

            if reasons:
                anomalies.append({
                    "Patient":     pid,
                    "Timestamp":   row["timestamp"],
                    "Value":       val,
                    "Type":        row.get("measurement_type", ""),
                    "Status":      row["status"],
                    "Reason":      "; ".join(reasons),
                    "Notes":       row.get("notes", ""),
                })

    return pd.DataFrame(anomalies) if anomalies else pd.DataFrame()


# ─── Step 5: Print Console Report ────────────────────────────────────────────

def print_report(df: pd.DataFrame, metrics: pd.DataFrame, anomalies: pd.DataFrame):
    """Print a formatted text report to the console."""
    sep = "═" * 65

    print(sep)
    print("  🩸 BLOOD SUGAR ANALYSIS REPORT")
    print(f"  Generated: {datetime.now().strftime('%d %B %Y %H:%M')}")
    print(sep)

    # Per-patient metrics
    for _, row in metrics.iterrows():
        print(f"\n  Patient: {row['Patient']}  ({row['Readings']} readings)")
        print(f"  {'Mean':12} {row['Mean (mg/dL)']} mg/dL")
        print(f"  {'Median':12} {row['Median (mg/dL)']} mg/dL")
        print(f"  {'Std Dev':12} ±{row['Std Dev']} mg/dL")
        print(f"  {'Range':12} {row['Min (mg/dL)']} – {row['Max (mg/dL)']} mg/dL")
        print(f"  {'Normal':12} {row['% Normal']}%   "
              f"Elevated: {row['% Elevated']}%   "
              f"High: {row['% High']}%")
        print(f"  Abnormal readings: {row['Abnormal Count']}")

    # Anomaly table
    print(f"\n{sep}")
    print("  ⚠  UNUSUAL VALUES DETECTED")
    print(sep)
    if anomalies.empty:
        print("  No unusual values found.")
    else:
        for _, a in anomalies.iterrows():
            ts = a["Timestamp"].strftime("%d %b %H:%M") if pd.notna(a["Timestamp"]) else "?"
            print(f"  {a['Patient']}  |  {ts}  |  "
                  f"{int(a['Value'])} mg/dL  |  {a['Status']}")
            print(f"           Reason: {a['Reason']}")
            if pd.notna(a["Notes"]) and str(a["Notes"]).strip():
                print(f"           Note  : {a['Notes']}")
    print(sep)


# ─── Step 6: Generate Plot ────────────────────────────────────────────────────

def generate_plot(df: pd.DataFrame, metrics: pd.DataFrame, output_path: str):
    """
    Produce a 4-panel summary figure:
      Panel 1: Time-series line chart per patient
      Panel 2: Box plot of distribution per patient
      Panel 3: Status breakdown bar chart
      Panel 4: Summary metrics table
    """
    patients = df["patient_id"].unique()
    colors   = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    pat_colors = {p: colors[i % len(colors)] for i, p in enumerate(patients)}

    fig = plt.figure(figsize=(16, 12), facecolor="#f8f9fa")
    fig.suptitle("Blood Sugar Level Analysis Report",
                 fontsize=18, fontweight="bold", y=0.98, color="#1a1a2e")

    gs = GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35,
                  left=0.08, right=0.96, top=0.92, bottom=0.08)

    ax1 = fig.add_subplot(gs[0, :])   # top full-width
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    # ── Panel 1: Time series ───────────────────────────────────────────────
    for pid in patients:
        g = df[df["patient_id"] == pid].sort_values("timestamp")
        ax1.plot(g["timestamp"], g["blood_sugar_mg_dl"],
                 marker='o', markersize=4, linewidth=1.5,
                 label=pid, color=pat_colors[pid])

        # Mark anomalies
        anom = g[g["status"].isin(["CRITICAL_LOW","CRITICAL_HIGH","LOW","HIGH"])]
        ax1.scatter(anom["timestamp"], anom["blood_sugar_mg_dl"],
                    s=120, zorder=5, edgecolors='black', linewidths=0.8,
                    color=[STATUS_COLORS[s] for s in anom["status"]])

    # Clinical threshold bands
    ax1.axhspan(0,   70,  alpha=0.08, color="#d62728", label="_nolegend_")
    ax1.axhspan(70,  99,  alpha=0.06, color="#2ca02c", label="_nolegend_")
    ax1.axhspan(300, 450, alpha=0.08, color="#d62728", label="_nolegend_")
    ax1.axhline(70,  color="#d62728", linestyle="--", linewidth=0.9, alpha=0.7)
    ax1.axhline(140, color="#ff7f0e", linestyle="--", linewidth=0.9, alpha=0.7)
    ax1.axhline(200, color="#d62728", linestyle="--", linewidth=0.9, alpha=0.7)

    ax1.set_title("Blood Sugar Levels Over Time", fontweight="bold", pad=10)
    ax1.set_ylabel("Blood Sugar (mg/dL)")
    ax1.set_xlabel("Date / Time")
    ax1.legend(loc="upper right", framealpha=0.9)
    ax1.tick_params(axis='x', rotation=30)
    ax1.set_facecolor("#ffffff")
    ax1.grid(True, linestyle=":", alpha=0.5)

    # Threshold labels
    for y, label in [(70, "Hypo threshold"), (140, "Post-meal limit"), (200, "Diabetic high")]:
        ax1.text(df["timestamp"].max(), y + 3, label,
                 fontsize=7, color="gray", ha="right")

    # ── Panel 2: Box plot ─────────────────────────────────────────────────
    data_by_patient = [df[df["patient_id"] == p]["blood_sugar_mg_dl"].values
                       for p in patients]
    bp = ax2.boxplot(data_by_patient, patch_artist=True, notch=False,
                     medianprops=dict(color="black", linewidth=2))
    for patch, pid in zip(bp["boxes"], patients):
        patch.set_facecolor(pat_colors[pid])
        patch.set_alpha(0.75)

    ax2.set_xticklabels(patients, rotation=15)
    ax2.axhline(140, color="#ff7f0e", linestyle="--", linewidth=1, alpha=0.7)
    ax2.axhline(70,  color="#d62728", linestyle="--", linewidth=1, alpha=0.7)
    ax2.set_title("Distribution per Patient", fontweight="bold")
    ax2.set_ylabel("Blood Sugar (mg/dL)")
    ax2.set_facecolor("#ffffff")
    ax2.grid(True, axis='y', linestyle=":", alpha=0.5)

    # ── Panel 3: Status breakdown stacked bar ─────────────────────────────
    status_order = ["CRITICAL_LOW","LOW","NORMAL","ELEVATED","HIGH","CRITICAL_HIGH"]
    status_colors_list = ["#8B0000","#ff7f0e","#2ca02c","#bcbd22","#d95f02","#d62728"]

    status_counts = (df.groupby(["patient_id", "status"])
                       .size()
                       .unstack(fill_value=0)
                       .reindex(columns=[s for s in status_order if s in df["status"].unique()],
                                fill_value=0))

    status_counts.plot(kind="bar", stacked=True, ax=ax3,
                       color=[STATUS_COLORS[s] for s in status_counts.columns],
                       edgecolor="white", linewidth=0.5)

    ax3.set_title("Reading Status Breakdown", fontweight="bold")
    ax3.set_ylabel("Number of Readings")
    ax3.set_xlabel("")
    ax3.tick_params(axis='x', rotation=15)
    ax3.legend(title="Status", fontsize=8, title_fontsize=8,
               loc="upper left", framealpha=0.9)
    ax3.set_facecolor("#ffffff")
    ax3.grid(True, axis='y', linestyle=":", alpha=0.5)

    # ── Footer disclaimer ─────────────────────────────────────────────────
    fig.text(0.5, 0.01,
             "⚠ Educational model only — not for clinical use. "
             "Reference ranges: fasting normal 70–99 mg/dL, post-meal normal <140 mg/dL.",
             ha="center", fontsize=8, color="gray", style="italic")

    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"\n  📊 Plot saved to: {output_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(csv_path: str = "blood_sugar.csv", plot_path: str = "blood_sugar_report.png"):
    print("\n🩸 Blood Sugar Analyser — starting...\n")

    # 1. Load
    df = load_csv(csv_path)

    # 2. Classify every reading
    df["status"] = df.apply(classify_reading, axis=1)

    # 3. Compute metrics
    metrics = compute_metrics(df)

    # 4. Find anomalies
    anomalies = find_anomalies(df)

    # 5. Print report
    print_report(df, metrics, anomalies)

    # 6. Plot
    generate_plot(df, metrics, plot_path)

    print("\n✅ Analysis complete.\n")
    return df, metrics, anomalies


if __name__ == "__main__":
    csv_file  = sys.argv[1] if len(sys.argv) > 1 else "blood_sugar.csv"
    plot_file = sys.argv[2] if len(sys.argv) > 2 else "blood_sugar_report.png"
    main(csv_file, plot_file)
