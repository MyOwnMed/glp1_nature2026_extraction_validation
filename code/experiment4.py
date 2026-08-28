#!/usr/bin/env python3
"""Reproduce highlighted cumulative delta HPO plots.

Usage
-----
Run from the project root:

  python experiment4.py \
      --json outputs/comparisons/phenotypes/timeline/hpo_timeline_prevalence.json \
      --top 10

This will write two PNG files into:
  outputs/comparisons/phenotypes/timeline/plots/
    - highlight_delta_cumulative_down_experiment4.png
    - highlight_delta_cumulative_up_experiment4.png

These images should match the corresponding figures from the original
`comparisonhpo2vis.py` given the same JSON input.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Paths (relative to this script)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data"
DEFAULT_JSON = DATA_DIR / "hpo_timeline_prevalence.json"
PLOT_DIR = Path(".")

# Local ontology sources for name mapping (optional)
OBO_PATH = DATA_DIR / "hp.obo"
HPOA_PATH = DATA_DIR / "phenotype.hpoa"

# Codes to exclude from all visualizations (match comparisonhpo2vis.py).
# HP:0000819 (Diabetes mellitus) is excluded because it is an indication for
# GLP-1 RA initiation rather than an outcome of it: its prevalence is
# definitionally near-universal in the treated cohort and swamps the delta
# scale. This exclusion is stated in the Methods.
EXCLUDE_CODES = {"HP:0000819"}  # Diabetes mellitus

# When True, per-window event-count normalization is skipped. Exposed through
# --no-normalize so the normalized result can be checked against an
# unnormalized sensitivity analysis; normalization divides prevalence by
# per-window event counts, so part of the before/after delta would otherwise
# be driven by encounter volume rather than by prevalence change.
DISABLE_NORMALIZATION = False


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def is_excluded(code: str) -> bool:
    return code in EXCLUDE_CODES


def log(msg: str) -> None:
    print(f"[experiment4] {msg}")


def load_results(path: Path) -> Dict[str, Any]:
    """Load the timeline prevalence JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# HPO name resolution (optional, for human-readable labels)
# ---------------------------------------------------------------------------

def build_hpo_name_map_from_obo(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    name_map: Dict[str, str] = {}
    current_id: Optional[str] = None
    current_name: Optional[str] = None
    in_term = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        if line == "[Term]":
            if in_term and current_id and current_name:
                name_map[current_id] = current_name
            in_term = True
            current_id = None
            current_name = None
            continue
        if not in_term:
            continue
        if line.startswith("id: "):
            current_id = line.split("id: ", 1)[1].strip()
        elif line.startswith("name: "):
            current_name = line.split("name: ", 1)[1].strip()
        elif line.startswith("[Typedef]"):
            if in_term and current_id and current_name:
                name_map[current_id] = current_name
            break
    if in_term and current_id and current_name:
        name_map[current_id] = current_name
    return name_map


def build_hpo_name_map_from_hpoa(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    name_map: Dict[str, str] = {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        return {}
    header = lines[0].split("\t")
    try:
        id_idx = next(i for i, h in enumerate(header) if h.lower() in {"hpo_id", "phenotype_id", "hpo-term-id", "hpo term id"})
    except StopIteration:
        id_idx = None
    try:
        name_idx = next(i for i, h in enumerate(header) if h.lower() in {"hpo_term_name", "phenotype_name", "hpo-term-name", "hpo term name"})
    except StopIteration:
        name_idx = None
    if id_idx is None or name_idx is None:
        return {}
    for ln in lines[1:]:
        cols = ln.split("\t")
        if len(cols) <= max(id_idx, name_idx):
            continue
        code = cols[id_idx].strip()
        name = cols[name_idx].strip()
        if code and name and code.startswith("HP:"):
            name_map[code] = name
    return name_map


def build_hpo_name_map() -> Dict[str, str]:
    """Try OBO first, then HPOA. Return empty dict if both missing."""
    m = build_hpo_name_map_from_obo(OBO_PATH)
    if m:
        return m
    return build_hpo_name_map_from_hpoa(HPOA_PATH)


# ---------------------------------------------------------------------------
# Timeline helpers (copied from comparisonhpo2vis.py for reproducibility)
# ---------------------------------------------------------------------------

def extract_window_order(result: Dict[str, Any]) -> List[str]:
    meta = result.get("meta", {}) or {}
    before = meta.get("window_labels_before", [])
    after = meta.get("window_labels_after", [])
    return list(before) + list(after)


def label_to_day(label: str) -> int:
    """Convert labels like 'prev_30' -> -30, 'post_30' -> +30."""
    try:
        d = int(label.split("_", 1)[1])
    except Exception:
        d = 0
    return -d if label.startswith("prev_") else d


def get_normalization_factors(result: Dict[str, Any]) -> Dict[str, float]:
    """Return per-window normalization factors based on event counts.

    If meta.overall_event_counts is missing or total_patients <= 0, returns
    an empty dict and no normalization is applied (matching comparisonhpo2vis).
    """
    if DISABLE_NORMALIZATION:
        return {}
    meta = result.get("meta", {}) or {}
    total_patients = meta.get("total_patients", 0)
    event_counts = meta.get("overall_event_counts", {}) or {}
    factors: Dict[str, float] = {}
    if not event_counts or total_patients <= 0:
        return factors
    for label, count in event_counts.items():
        if count > 0:
            factors[label] = float(total_patients) / float(count)
        else:
            factors[label] = 0.0
    return factors


# ---------------------------------------------------------------------------
# Core: delta cumulative series + highlighted plots
# ---------------------------------------------------------------------------

def get_delta_cumulative_series(result: Dict[str, Any]) -> Tuple[List[int], Dict[str, List[float]]]:
    """Compute per-HPO series of cumulative after-before deltas across thresholds.

    This exactly mirrors get_delta_cumulative_series in comparisonhpo2vis.py.
    """
    overall_cum = result.get("overall_cumulative_by_window", {}) or {}
    factors = get_normalization_factors(result)
    use_norm = bool(factors)

    def get_pct(lbl: str) -> Dict[str, float]:
        raw = {c: v for c, v in ((overall_cum.get(lbl) or {}).get("percent", {}) or {}).items() if not is_excluded(c)}
        if not use_norm:
            return raw
        factor = factors.get(lbl, 1.0)
        return {c: float(v) * factor for c, v in raw.items()}

    window_order = extract_window_order(result)
    thresholds = sorted({abs(label_to_day(lbl)) for lbl in window_order})
    thresholds = [t for t in thresholds if t != 0]

    series: Dict[str, List[float]] = {}
    codes_set = set()
    for t in thresholds:
        prev_lbl = f"prev_{t}"
        post_lbl = f"post_{t}"
        codes_set |= set(get_pct(prev_lbl).keys())
        codes_set |= set(get_pct(post_lbl).keys())

    for code in codes_set:
        y_vals: List[float] = []
        for t in thresholds:
            prev_lbl = f"prev_{t}"
            post_lbl = f"post_{t}"
            dv = float(get_pct(post_lbl).get(code, 0.0)) - float(get_pct(prev_lbl).get(code, 0.0))
            y_vals.append(dv)
        series[code] = y_vals

    return thresholds, series


def make_highlight_delta_cumulative_lines(
    result: Dict[str, Any],
    name_map: Dict[str, str],
    top_highlight: int = 10,
    fade_alpha: float = 0.2,
    suffix: str = "experiment4",
) -> Tuple[Optional[Path], Optional[Path]]:
    """Create plots highlighting largest downward/upward cumulative delta slopes.

    Returns (down_path, up_path).
    """
    thresholds, series = get_delta_cumulative_series(result)
    if not thresholds or not series:
        return None, None

    factors = get_normalization_factors(result)
    use_norm = bool(factors)

    x = np.array(thresholds, dtype=float)

    # Compute slopes via linear regression on (threshold, delta) pairs
    slopes: List[Tuple[str, float]] = []
    for code, y in series.items():
        y_arr = np.array(y, dtype=float)
        if np.allclose(y_arr, 0.0):
            slope = 0.0
        else:
            try:
                slope = float(np.polyfit(x, y_arr, 1)[0])
            except Exception:
                slope = 0.0
        slopes.append((code, slope))

    slopes_sorted_neg = sorted(slopes, key=lambda kv: kv[1])  # most negative first
    slopes_sorted_pos = sorted(slopes, key=lambda kv: -kv[1])  # most positive first

    neg_codes = [code for code, _ in slopes_sorted_neg[: max(1, top_highlight)]]
    pos_codes = [code for code, _ in slopes_sorted_pos[: max(1, top_highlight)]]

    palette = [
        "#4e79a7",
        "#e15759",
        "#76b7b2",
        "#59a14f",
        "#edc948",
        "#b07aa1",
        "#ff9da7",
        "#9c755f",
        "#bab0ab",
        "#f28e2b",
    ]

    def color_for(idx: int) -> str:
        return palette[idx % len(palette)]

    def plot_highlight(high_codes: List[str], title_suffix: str, out_name: str) -> Path:
        plt.figure(figsize=(max(12, 0.6 * len(thresholds)), 7))
        # Plot all lines with low opacity background
        for _, y in series.items():
            plt.plot(thresholds, y, color="#bbbbbb", alpha=fade_alpha, linewidth=1, label=None)
        # Overlay highlighted lines
        for idx, code in enumerate(high_codes):
            y = series.get(code, [])
            lab = name_map.get(code, code)
            label = f"{lab} [{code}]" if lab != code else code
            plt.plot(thresholds, y, color=color_for(idx), alpha=1.0, linewidth=1.5, marker="o", label=label)
        plt.axhline(0, color="#999999", linestyle="--", linewidth=1)
        plt.title(
            f"Delta {'Normalized ' if use_norm else ''}Prevalence (After - Before), "
            f"Cumulative - {title_suffix}"
        )
        plt.xlabel("Days threshold")
        plt.ylabel(f"Delta {'Normalized ' if use_norm else ''}%")
        if high_codes:
            plt.legend(ncol=2, fontsize=12)
        plt.grid(True, axis="y", linestyle=":", alpha=0.5)
        plt.tight_layout()
        out_path = PLOT_DIR / out_name
        plt.savefig(out_path, dpi=150)
        plt.close()
        return out_path

    down_path = plot_highlight(
        neg_codes,
        "largest downward slopes",
        f"highlight_delta_cumulative_down_{suffix}.png",
    )
    up_path = plot_highlight(
        pos_codes,
        "largest upward slopes",
        f"highlight_delta_cumulative_up_{suffix}.png",
    )
    return down_path, up_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    plt.rcParams.update(
        {
            "font.size": 12,
            "axes.titlesize": 16,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "figure.titlesize": 18,
        }
    )

    parser = argparse.ArgumentParser(
        description=(
            "Reproduce highlighted cumulative delta HPO plots (up/down) "
            "from comparisonhpo2vis.py"
        )
    )
    parser.add_argument(
        "--json",
        default=str(DEFAULT_JSON),
        help="Path to hpo_timeline_prevalence.json",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of HPO codes to highlight (up and down)",
    )
    parser.add_argument(
        "--suffix",
        default="experiment4",
        help="Suffix to append to output filenames",
    )
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Directory to save output plots",
    )
    parser.add_argument(
        "--data_dir",
        default=".",
        help="Directory containing ontology files",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help=(
            "Skip per-window event-count normalization (unnormalized "
            "sensitivity analysis)"
        ),
    )
    args = parser.parse_args()

    global DISABLE_NORMALIZATION
    DISABLE_NORMALIZATION = args.no_normalize
    if DISABLE_NORMALIZATION:
        log("Normalization DISABLED (unnormalized sensitivity analysis).")

    global PLOT_DIR, OBO_PATH, HPOA_PATH
    PLOT_DIR = Path(args.output_dir)
    data_dir = Path(args.data_dir)
    OBO_PATH = data_dir / "hp.obo"
    HPOA_PATH = data_dir / "phenotype.hpoa"

    json_path = Path(args.json).resolve()
    if not json_path.exists():
        raise FileNotFoundError(f"Results JSON not found: {json_path}")

    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    # Log the path relative to the repository root when the input sits inside
    # the repository, so the results files record a reproducible location
    # rather than whoever's home directory the run happened to start from.
    try:
        display_path = json_path.relative_to(ROOT.parent)
    except ValueError:
        display_path = json_path
    log(f"Loading results from: {display_path}")
    result = load_results(json_path)

    log("Building HPO name map (optional)...")
    name_map = build_hpo_name_map()
    if not name_map:
        log("Warning: no ontology found; using raw HPO codes as labels.")

    log("Generating highlighted cumulative delta plots...")
    down_path, up_path = make_highlight_delta_cumulative_lines(
        result,
        name_map,
        top_highlight=max(1, args.top),
        suffix=args.suffix,
    )

    if down_path is None or up_path is None:
        log("No data available to generate plots (empty series or thresholds).")
        return

    log(f"Wrote downward-highlight plot to: {down_path}")
    log(f"Wrote upward-highlight plot to: {up_path}")


if __name__ == "__main__":
    main()
