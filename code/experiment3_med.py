import json
import os

from agreement import pairwise_agreement, HEADER, format_row

SOURCE_DISPLAY = {
    'med_ner': 'Bert Large Med NER',
    'disease_ner_meds': 'BioNER',
    'medications': 'Ours (GPT)',
}

MED_SECTIONS = ['med_ner', 'disease_ner_meds', 'medications']


def calculate_aggregate_performance_from_json(data_dir):
    """
    Load pre-computed aggregate stats from med_aggregate_stats.json.
    This includes reviews from all reviewers (not just MD1/MD2/MD3).

    N is the number of extracted items reviewed. The source file carries no
    count of items the reviewers flagged as missing, so no recall-side
    denominator is available here; the column is labelled accordingly and
    matches the 'N (extracted)' column in experiment2.py.
    """
    stats_path = os.path.join(data_dir, 'med_aggregate_stats.json')
    with open(stats_path, 'r') as f:
        agg = json.load(f)

    results = {}
    for section in MED_SECTIONS:
        s = agg[section]
        total_extracted = s['total_extracted']
        correct = s['correct']
        neg_err = s['neg_err']
        other_err = s['other_err']
        tp_entity = correct + neg_err

        results[section] = {
            'n_extracted': total_extracted,
            'precision': (correct / total_extracted * 100) if total_extracted else 0,
            'negation_error_rate': (neg_err / tp_entity * 100) if tp_entity else 0,
            'other_error_rate': (other_err / total_extracted * 100) if total_extracted else 0,
        }

    return results


def build_items(source_reviews):
    """Map each reviewed item to {reviewer: label}."""
    items = {}
    for row in source_reviews:
        if row['is_missing']:
            continue
        key = f"{row['visit_key']}|{row['finding_name']}|{row['finding_index']}"
        items.setdefault(key, {})[row['reviewer']] = row['label']
    return items


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')

    files = [
        os.path.join(data_dir, 'MD1_med.json'),
        os.path.join(data_dir, 'MD2_med.json'),
        os.path.join(data_dir, 'MD3_med.json'),
    ]
    missing_files = [f for f in files if not os.path.exists(f)]
    if missing_files:
        print(f"Missing input files: {missing_files}")
        return 1

    all_reviews = []
    print("Loading reviews from JSON files...")
    for fpath in files:
        with open(fpath, 'r') as f:
            all_reviews.extend(json.load(f))

    reviews_by_source = {}
    for row in all_reviews:
        reviews_by_source.setdefault(row['source'], []).append(row)

    # =========================================================================
    # Table 1: Inter-Rater Agreement
    # =========================================================================
    print("\n" + "=" * 100)
    print("Table 1: Inter-Rater Agreement (Medications)")
    print("=" * 100)
    print(f"{'Medications':<20} {HEADER}")
    print("-" * 100)

    for section in MED_SECTIONS:
        if section not in reviews_by_source:
            continue
        display_name = SOURCE_DISPLAY[section]
        for idx, res in enumerate(pairwise_agreement(build_items(reviews_by_source[section]))):
            src_label = display_name if idx == 0 else ""
            print(f"{src_label:<20} {format_row(res)}")

    print("\n  Cohen's K and PABAK are reported separately for every pair; neither column")
    print("  mixes estimators. 'Degenerate' marks pairs where a rater's marginal has no")
    print("  variance, which forces p0 == pe and hence Cohen's K == 0 (or 0/0, undefined)")
    print("  regardless of observed agreement. PABAK should be read in place of Cohen's K")
    print("  on those rows. See agreement.py.")

    # =========================================================================
    # Table 2: Aggregate Performance (from JSON, all reviewers)
    # =========================================================================
    print("\n" + "=" * 90)
    print("Table 2: Medication Extraction Performance (aggregated across all reviewers)")
    print("=" * 90)
    print(f"{'Model':<20} {'N (extracted)':<16} {'Precision (%)':<16} {'Negation Error (%)':<20} {'Other Error (%)':<16}")
    print("-" * 90)

    agg_stats = calculate_aggregate_performance_from_json(data_dir)
    for section in MED_SECTIONS:
        display_name = SOURCE_DISPLAY[section]
        s = agg_stats[section]
        print(f"{display_name:<20} {s['n_extracted']:<16,} {s['precision']:<15.1f} {s['negation_error_rate']:<19.1f} {s['other_error_rate']:<15.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
