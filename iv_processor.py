#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Process special solar-cell IV CSV exported by instrument.

Outputs (saved in same folder as input CSV):
- summary_raw.csv
- summary_cleaned.csv
- outlier_report.csv
- best_pce_by_condition.csv
- boxplot_Voc.png
- boxplot_PCE.png
- boxplot_Jsc.png
- boxplot_FF.png
- boxplot_Rs.png
- boxplot_Rsh.png
- best_pce_iv_comparison.png
"""

from __future__ import annotations

import argparse
import csv
import re
import warnings
from io import StringIO
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# tkinter is optional in headless environments
try:
    import tkinter as tk
    from tkinter import filedialog
    from tkinter import messagebox
except Exception:
    tk = None
    filedialog = None
    messagebox = None


# -----------------------------
# Config
# -----------------------------
TARGET_PARAMS = {
    "Voc": "Voc (V)",
    "PCE": "Efficiency (%)",
    "Jsc": "Jsc (mA/cm^2)",
    "FF": "Fill Factor (%)",
    "Rs": "Rs (ohm)",
    "Rsh": "Rsh (ohm)",
}

SEP_PATTERN = re.compile(r"^\s*=+\s*(?:,.*)?$")
NAME_PATTERN = re.compile(r"^\s*([^\.]+)\..*$")


# -----------------------------
# Utility
# -----------------------------
def natural_key(s: str):
    """Natural sort key for condition labels."""
    parts = re.split(r"(\d+(?:\.\d+)?)", str(s))
    out = []
    for p in parts:
        if re.fullmatch(r"\d+(?:\.\d+)?", p):
            out.append(float(p))
        else:
            out.append(p.lower())
    return out


def choose_file_from_dialog() -> Path:
    if tk is None or filedialog is None:
        raise RuntimeError("tkinter is unavailable; please pass --input path/to/file.csv")
    root = tk.Tk()
    root.withdraw()
    f = filedialog.askopenfilename(
        title="Select instrument CSV file",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
    )
    root.destroy()
    if not f:
        raise FileNotFoundError("No file selected.")
    return Path(f)


def read_text_with_fallback(path: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "cp932", "gbk", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Failed to read file with common encodings: {last_err}")


def split_top_bottom(lines: List[str]) -> Tuple[List[str], List[str]]:
    sep_idx = None
    for i, line in enumerate(lines):
        if SEP_PATTERN.match(line.strip()):
            sep_idx = i
            break
    if sep_idx is None:
        raise ValueError("Cannot find separator line like '==========' in CSV.")
    return lines[:sep_idx], lines[sep_idx + 1:]


def find_summary_header_idx(lines: List[str]) -> int:
    for i, line in enumerate(lines):
        l = line.strip()
        if "Name" in l and "Voc" in l and "Efficiency" in l:
            return i
    raise ValueError("Cannot find summary header line (Name, Isc, Voc, ...).")


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df


def extract_condition(name: str) -> str:
    if pd.isna(name):
        return "UNKNOWN"
    name = str(name).strip()
    m = NAME_PATTERN.match(name)
    if m:
        return m.group(1).strip()
    return name


def normalize_name(raw_name: str) -> str:
    """
    Normalize name tokens from instrument exports.
    Examples:
    - "4-100.CH1(1)" -> "4-100.CH1(1)"
    - "4-100 (4-100.CH1(1))" -> "4-100.CH1(1)"
    """
    if raw_name is None:
        return ""
    s = str(raw_name).strip()
    if not s:
        return ""

    # Prefer content inside (...) if it looks like canonical channel name
    m = re.search(r"\(([^\)]*\.[^\)]*\([^\)]*\))\)", s)
    if m:
        return m.group(1).strip()

    return s


# -----------------------------
# Parsing summary (bottom section)
# -----------------------------
def parse_summary_table(bottom_lines: List[str]) -> pd.DataFrame:
    hdr_idx = find_summary_header_idx(bottom_lines)
    text = "\n".join(bottom_lines[hdr_idx:])
    df = pd.read_csv(StringIO(text), engine="python")
    df = clean_columns(df)

    # Remove fully empty rows
    df = df.dropna(how="all").copy()

    # Keep rows with valid Name
    if "Name" not in df.columns:
        raise ValueError("Summary table has no 'Name' column.")
    df["Name"] = df["Name"].astype(str).str.strip()
    df = df[df["Name"] != ""].copy()

    # Numeric conversion for all non-Name columns
    for c in df.columns:
        if c != "Name":
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Add Condition
    df["Condition"] = df["Name"].apply(extract_condition)
    return df


# -----------------------------
# Parsing IV curves (top section)
# -----------------------------
def parse_top_as_matrix(top_lines: List[str]) -> List[List[str]]:
    reader = csv.reader(top_lines)
    rows = [r for r in reader]
    if not rows:
        return []
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]
    return rows


def parse_iv_blocks(top_lines: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Parse horizontal blocks. Typical block:
    [info_label, info_value, Volt(V), Current(mA), J(mA/cm^2)]
    """
    rows = parse_top_as_matrix(top_lines)
    if not rows:
        return {}

    nrows = len(rows)
    ncols = len(rows[0])

    # Candidate block start: column where any row equals "Name"
    starts = []
    for c in range(max(0, ncols - 4)):
        col_vals = [str(rows[r][c]).strip() for r in range(nrows)]
        if any(v.lower() == "name" for v in col_vals):
            starts.append(c)

    starts = sorted(set(starts))
    iv_dict: Dict[str, pd.DataFrame] = {}

    for c in starts:
        # Need c+4 to exist
        if c + 4 >= ncols:
            continue

        # Find Name from label-value pair
        name_val = None
        for r in range(nrows):
            label = str(rows[r][c]).strip().lower()
            val = str(rows[r][c + 1]).strip()
            if label == "name" and val:
                name_val = val
                break

        # fallback: scan likely name-like value in info value col
        if not name_val:
            for r in range(nrows):
                val = str(rows[r][c + 1]).strip()
                if "." in val and "(" in val and ")" in val:
                    name_val = val
                    break

        if not name_val:
            continue
        name_val = normalize_name(name_val)
        if not name_val:
            continue

        # Extract Volt and J columns
        volt = pd.to_numeric([rows[r][c + 2] for r in range(nrows)], errors="coerce")
        jval = pd.to_numeric([rows[r][c + 4] for r in range(nrows)], errors="coerce")

        curve = pd.DataFrame({"Volt (V)": volt, "J (mA/cm^2)": jval}).dropna()
        if curve.empty:
            continue

        # Remove duplicated x/y pairs
        curve = curve.drop_duplicates().reset_index(drop=True)

        if name_val in iv_dict:
            warnings.warn(f"Duplicate IV block for Name '{name_val}', keeping first one.")
            continue
        iv_dict[name_val] = curve

    return iv_dict


# -----------------------------
# Outlier removal
# -----------------------------
def remove_outliers_iqr(
    df: pd.DataFrame,
    condition_col: str,
    params: List[str],
    min_n: int = 4,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Remove rows that are outlier in ANY target parameter (within its condition).
    Returns:
      cleaned_df
      outlier_report (Condition, Parameter, total, removed, skipped_small_n)
    """
    cleaned = df.copy()
    to_drop = pd.Series(False, index=cleaned.index)
    reports = []

    for cond, g in cleaned.groupby(condition_col):
        for p in params:
            valid_idx = g[p].dropna().index
            n = len(valid_idx)

            removed = 0
            skipped_small_n = False

            if n < min_n:
                skipped_small_n = True
            else:
                vals = cleaned.loc[valid_idx, p]
                q1 = vals.quantile(0.25)
                q3 = vals.quantile(0.75)
                iqr = q3 - q1

                if pd.isna(iqr) or iqr == 0:
                    # IQR zero/invalid: no stable outlier filtering
                    skipped_small_n = True
                else:
                    lower = q1 - 1.5 * iqr
                    upper = q3 + 1.5 * iqr
                    outlier_idx = vals[(vals < lower) | (vals > upper)].index
                    removed = len(outlier_idx)
                    if removed > 0:
                        to_drop.loc[outlier_idx] = True

            reports.append(
                {
                    "Condition": cond,
                    "Parameter": p,
                    "TotalValid": n,
                    "Removed": removed,
                    "SkippedSmallOrUnstable": int(skipped_small_n),
                }
            )

    cleaned = cleaned.loc[~to_drop].copy()
    report_df = pd.DataFrame(reports)
    return cleaned, report_df


# -----------------------------
# Plotting
# -----------------------------
def setup_plot_style():
    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams["figure.dpi"] = 120


def save_boxplot(
    df: pd.DataFrame,
    param_col: str,
    param_label: str,
    out_path: Path,
    order: List[str],
):
    plt.figure(figsize=(11, 6))
    ax = sns.boxplot(
        data=df,
        x="Condition",
        y=param_col,
        order=order,
        showfliers=False,  # outliers already cleaned
        width=0.6,
        color="#9ecae1",
    )
    sns.stripplot(
        data=df,
        x="Condition",
        y=param_col,
        order=order,
        color="#1f77b4",
        alpha=0.7,
        jitter=0.2,
        size=4,
    )
    ax.set_title(f"{param_label} by Condition (IQR-cleaned)", pad=12)
    ax.set_xlabel("Condition")
    ax.set_ylabel(param_label)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def save_best_iv_plot(best_df: pd.DataFrame, iv_dict: Dict[str, pd.DataFrame], out_path: Path):
    plt.figure(figsize=(10, 7))
    plotted = 0

    for _, row in best_df.iterrows():
        cond = row["Condition"]
        name = row["Name"]
        curve = iv_dict.get(name)

        if curve is None or curve.empty:
            warnings.warn(f"No valid IV curve found for Condition={cond}, Name={name}")
            continue

        plt.plot(
            curve["Volt (V)"].values,
            curve["J (mA/cm^2)"].values,
            linewidth=2,
            label=f"{cond} | {name}",
        )
        plotted += 1

    plt.title("Best-PCE IV Curves by Condition")
    plt.xlabel("Volt (V)")
    plt.ylabel("J (mA/cm^2)")
    if plotted > 0:
        plt.legend(fontsize=9, frameon=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def ask_axis_limits_cli(args) -> Tuple[float | None, float | None, float | None, float | None]:
    """
    Decide axis limits for IV comparison plot.
    Priority:
    1) command line args
    2) optional interactive terminal input
    3) auto (None)
    """
    vmin, vmax, jmin, jmax = args.vmin, args.vmax, args.jmin, args.jmax
    if not args.ask_limits:
        return vmin, vmax, jmin, jmax

    def _prompt_float(prompt: str, default: float | None) -> float | None:
        hint = "auto" if default is None else str(default)
        s = input(f"{prompt} (回车=自动, 当前={hint}): ").strip()
        if s == "":
            return default
        try:
            return float(s)
        except ValueError:
            print(f"  输入无效 '{s}'，将使用自动范围。")
            return None

    print("\n[IV 图坐标范围设置] 你可以手动输入范围，回车则自动范围。")
    vmin = _prompt_float("请输入 V 最小值 vmin", vmin)
    vmax = _prompt_float("请输入 V 最大值 vmax", vmax)
    jmin = _prompt_float("请输入 J 最小值 jmin", jmin)
    jmax = _prompt_float("请输入 J 最大值 jmax", jmax)
    return vmin, vmax, jmin, jmax


def ask_continue_dialog() -> bool:
    """Ask whether to continue selecting another CSV file."""
    if tk is not None and messagebox is not None:
        root = tk.Tk()
        root.withdraw()
        ans = messagebox.askyesno("继续处理", "是否继续选择并处理另一个 CSV 文件？")
        root.destroy()
        return bool(ans)

    s = input("是否继续处理另一个 CSV 文件？[y/N]: ").strip().lower()
    return s in {"y", "yes"}


def process_one_csv(csv_path: Path, args) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    print(f"\nProcessing: {csv_path}")

    # Save outputs into a folder named by input CSV stem, e.g. "0410-C"
    out_dir = csv_path.parent / csv_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Read and split
    text = read_text_with_fallback(csv_path)
    lines = text.splitlines()
    top_lines, bottom_lines = split_top_bottom(lines)

    # 2) Parse summary and IV
    summary_raw = parse_summary_table(bottom_lines)
    iv_dict = parse_iv_blocks(top_lines)

    # Ensure target columns exist
    missing_cols = [col for col in TARGET_PARAMS.values() if col not in summary_raw.columns]
    if missing_cols:
        raise ValueError(f"Missing required summary columns: {missing_cols}")

    # Save raw summary
    summary_raw.to_csv(out_dir / "summary_raw.csv", index=False, encoding="utf-8-sig")

    # 3) Outlier removal
    param_cols = list(TARGET_PARAMS.values())
    summary_cleaned, outlier_report = remove_outliers_iqr(
        summary_raw, condition_col="Condition", params=param_cols, min_n=4
    )

    summary_cleaned.to_csv(out_dir / "summary_cleaned.csv", index=False, encoding="utf-8-sig")
    outlier_report.to_csv(out_dir / "outlier_report.csv", index=False, encoding="utf-8-sig")

    # 4) Print sample counts (raw / cleaned)
    print("\nSample counts by Condition (raw / cleaned):")
    raw_counts = summary_raw["Condition"].value_counts()
    clean_counts = summary_cleaned["Condition"].value_counts()
    all_conds = sorted(set(raw_counts.index).union(set(clean_counts.index)), key=natural_key)
    for c in all_conds:
        print(f"  {c}: {int(raw_counts.get(c, 0))} / {int(clean_counts.get(c, 0))}")

    # 5) Boxplots for 6 params
    setup_plot_style()
    cond_order = sorted(summary_cleaned["Condition"].dropna().unique().tolist(), key=natural_key)

    for short_name, col_name in TARGET_PARAMS.items():
        png_name = f"boxplot_{short_name}.png"
        save_boxplot(
            df=summary_cleaned,
            param_col=col_name,
            param_label=short_name,
            out_path=out_dir / png_name,
            order=cond_order,
        )

    # 6) Best PCE per condition from cleaned data
    pce_col = TARGET_PARAMS["PCE"]
    valid_best = summary_cleaned.dropna(subset=[pce_col]).copy()

    if valid_best.empty:
        warnings.warn("No valid PCE data after cleaning; best_pce outputs will be empty.")
        best_pce = summary_cleaned.iloc[0:0].copy()
    else:
        idx = valid_best.groupby("Condition")[pce_col].idxmax()
        best_pce = valid_best.loc[idx].copy()
        best_pce = best_pce.sort_values("Condition", key=lambda s: s.map(natural_key)).reset_index(drop=True)

    best_pce.to_csv(out_dir / "best_pce_by_condition.csv", index=False, encoding="utf-8-sig")

    print("\nBest PCE by Condition (cleaned):")
    if best_pce.empty:
        print("  No valid records.")
    else:
        for _, r in best_pce.iterrows():
            print(f"  {r['Condition']}: PCE={r[pce_col]:.6g}, Name={r['Name']}")

    # 7) Best-PCE IV comparison plot
    vmin, vmax, jmin, jmax = ask_axis_limits_cli(args)
    plt.figure(figsize=(10, 7))
    plotted = 0
    for _, row in best_pce.iterrows():
        cond = row["Condition"]
        name = row["Name"]
        curve = iv_dict.get(name)
        if curve is None or curve.empty:
            warnings.warn(f"No valid IV curve found for Condition={cond}, Name={name}")
            continue
        plt.plot(curve["Volt (V)"].values, curve["J (mA/cm^2)"].values, linewidth=2, label=f"{cond} | {name}")
        plotted += 1
    plt.title("Best-PCE IV Curves by Condition")
    plt.xlabel("Volt (V)")
    plt.ylabel("J (mA/cm^2)")
    if vmin is not None or vmax is not None:
        plt.xlim(left=vmin, right=vmax)
    if jmin is not None or jmax is not None:
        plt.ylim(bottom=jmin, top=jmax)
    if plotted > 0:
        plt.legend(fontsize=9, frameon=True)
    plt.tight_layout()
    plt.savefig(out_dir / "best_pce_iv_comparison.png", dpi=300)
    plt.close()

    print("\nDone. Files saved to:")
    print(f"  {out_dir}")


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Process special solar-cell IV CSV")
    parser.add_argument("--input", type=str, default=None, help="Path to CSV file")
    parser.add_argument("--vmin", type=float, default=None, help="IV plot x-axis minimum")
    parser.add_argument("--vmax", type=float, default=None, help="IV plot x-axis maximum")
    parser.add_argument("--jmin", type=float, default=None, help="IV plot y-axis minimum")
    parser.add_argument("--jmax", type=float, default=None, help="IV plot y-axis maximum")
    parser.add_argument(
        "--ask-limits",
        action="store_true",
        help="Ask axis limits interactively in terminal before plotting IV comparison",
    )
    parser.add_argument(
        "--single",
        action="store_true",
        help="Only process one file and exit (disable post-run file-selection loop).",
    )
    args = parser.parse_args()

    # Mode A: explicit input path
    if args.input:
        process_one_csv(Path(args.input).expanduser().resolve(), args)
        return

    # Mode B: interactive file picker loop
    while True:
        try:
            csv_path = choose_file_from_dialog().resolve()
        except FileNotFoundError:
            print("未选择文件，程序结束。")
            return

        process_one_csv(csv_path, args)

        if args.single:
            return
        if not ask_continue_dialog():
            return


if __name__ == "__main__":
    main()
