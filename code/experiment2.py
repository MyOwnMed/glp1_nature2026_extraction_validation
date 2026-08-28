import json
import os

from agreement import pairwise_agreement, HEADER, format_row


# Display names for sources
SOURCE_DISPLAY = {
    'PhenoTagger': 'PhenoTagger',
    'Verified': 'Ours (GPT)'
}


def calculate_performance_metrics(reviews, reviewer_name, source_name):
    """
    Calculate Precision, Recall, F1 for Strict, Entity, and Negation Errors
    Based on the logic from app.py
    """
    correct_count = 0
    negation_errors = 0
    other_errors = 0
    total_extracted = 0
    missing_count = 0

    for r in reviews:
        if r['reviewer'] != reviewer_name or r['source'] != source_name:
            continue

        if r['is_missing']:
            missing_count += 1
        else:
            total_extracted += 1
            if r['is_correct']:
                correct_count += 1
            else:
                orig = r['original_negation']
                corr = r['corrected_negation']
                if corr != orig:
                    negation_errors += 1
                else:
                    other_errors += 1

    tp_strict = correct_count
    neg_err = negation_errors
    fn = missing_count
    tp_entity = tp_strict + neg_err

    # Strict Metrics
    p_strict = tp_strict / total_extracted if total_extracted else 0
    denom_r_strict = tp_strict + fn + neg_err
    r_strict = tp_strict / denom_r_strict if denom_r_strict else 0
    f1_strict = 2 * (p_strict * r_strict) / (p_strict + r_strict) if (p_strict + r_strict) else 0

    # Entity Metrics (Ignore Negation)
    p_entity = tp_entity / total_extracted if total_extracted else 0
    denom_r_entity = tp_entity + fn
    r_entity = tp_entity / denom_r_entity if denom_r_entity else 0
    f1_entity = 2 * (p_entity * r_entity) / (p_entity + r_entity) if (p_entity + r_entity) else 0

    negation_error_rate = (neg_err / tp_entity * 100) if tp_entity else 0

    return {
        'strict': {'precision': p_strict * 100, 'recall': r_strict * 100, 'f1': f1_strict * 100},
        'entity': {'precision': p_entity * 100, 'recall': r_entity * 100, 'f1': f1_entity * 100},
        'negation_error_rate': negation_error_rate,
        'counts': {
            'tp_strict': tp_strict, 'neg_err': neg_err, 'other_err': other_errors,
            'missing': fn, 'total_extracted': total_extracted, 'tp_entity': tp_entity
        }
    }


def calculate_aggregate_performance(reviews, source_name):
    """
    Aggregate performance across all reviewers for a given source.

    Extracted and missing counts are reported as separate columns rather than
    summed into a single ambiguous 'N'. The 'N (extracted)' column is directly
    comparable to the identically named column in experiment3_med.py.
    """
    correct_count = 0
    negation_errors = 0
    other_errors = 0
    total_extracted = 0
    missing_count = 0
    asserted_present = 0
    asserted_negated = 0

    for r in reviews:
        if r['source'] != source_name:
            continue
        if r['is_missing']:
            missing_count += 1
        else:
            total_extracted += 1
            if r['original_negation']:
                asserted_negated += 1
            else:
                asserted_present += 1
            if r['is_correct']:
                correct_count += 1
            else:
                orig = r['original_negation']
                corr = r['corrected_negation']
                if corr != orig:
                    negation_errors += 1
                else:
                    other_errors += 1

    tp_entity = correct_count + negation_errors

    return {
        'n_extracted': total_extracted,
        'n_missing': missing_count,
        'precision': (correct_count / total_extracted * 100) if total_extracted else 0,
        'negation_error_rate': (negation_errors / tp_entity * 100) if tp_entity else 0,
        'other_error_rate': (other_errors / total_extracted * 100) if total_extracted else 0,
        'asserted_present': asserted_present,
        'asserted_negated': asserted_negated,
    }


def build_items(source_reviews):
    """Map each reviewed item to {reviewer: label}."""
    items = {}
    for row in source_reviews:
        if row['is_missing']:
            continue
        key = f"{row['visit_key']}|{row['phenotype_name']}|{row['start_pos']}|{row['end_pos']}"
        items.setdefault(key, {})[row['reviewer']] = row['label']
    return items


def get_agreement_stats():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')

    files = [
        os.path.join(data_dir, 'MD1.json'),
        os.path.join(data_dir, 'MD2.json'),
        os.path.join(data_dir, 'MD3.json'),
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

    reviewer_names = sorted(set(r['reviewer'] for r in all_reviews))

    reviews_by_source = {}
    for row in all_reviews:
        reviews_by_source.setdefault(row['source'], []).append(row)

    # =========================================================================
    # Table 1: Inter-Rater Agreement
    # =========================================================================
    print("\n" + "=" * 100)
    print("Table 1: Inter-Rater Agreement")
    print("=" * 100)
    print(f"{'Phenotypes':<15} {HEADER}")
    print("-" * 100)

    for source in ['PhenoTagger', 'Verified']:
        if source not in reviews_by_source:
            continue
        display_name = SOURCE_DISPLAY.get(source, source)
        for idx, res in enumerate(pairwise_agreement(build_items(reviews_by_source[source]))):
            src_label = display_name if idx == 0 else ""
            print(f"{src_label:<15} {format_row(res)}")

    print("\n  Cohen's K and PABAK are reported separately for every pair, using the same")
    print("  estimator as experiment3_med.py. See agreement.py.")

    # =========================================================================
    # Table 2: Aggregate Performance by Model
    # =========================================================================
    print("\n" + "=" * 110)
    print("Table 2: Phenotype Extraction Performance (aggregated across all reviewers)")
    print("=" * 110)
    print(f"{'Model':<15} {'N (extracted)':<15} {'N (missing)':<13} {'Precision (%)':<16} {'Negation Error (%)':<20} {'Other Error (%)':<16}")
    print("-" * 110)

    agg = {}
    for source in ['PhenoTagger', 'Verified']:
        display_name = SOURCE_DISPLAY.get(source, source)
        stats = calculate_aggregate_performance(all_reviews, source)
        agg[source] = stats
        print(f"{display_name:<15} {stats['n_extracted']:<15,} {stats['n_missing']:<13,} {stats['precision']:<15.1f} {stats['negation_error_rate']:<19.1f} {stats['other_error_rate']:<15.1f}")

    # =========================================================================
    # Table 2b: Emitted negation distribution
    #
    # Negation error rate is only interpretable against how much negation each
    # system actually emits. A system that almost never asserts a negated
    # phenotype has little opportunity to make a negation error, so the error
    # rates above describe a capability difference rather than competing error
    # rates on a shared task.
    # =========================================================================
    print("\n" + "=" * 110)
    print("Table 2b: Emitted negation distribution (denominator for the negation error rate)")
    print("=" * 110)
    print(f"{'Model':<15} {'N (extracted)':<15} {'Asserted present':<20} {'Asserted negated':<20}")
    print("-" * 110)
    for source in ['PhenoTagger', 'Verified']:
        s = agg[source]
        n = s['n_extracted']
        pres = f"{s['asserted_present']:,} ({s['asserted_present']/n*100:.1f}%)" if n else "0"
        neg = f"{s['asserted_negated']:,} ({s['asserted_negated']/n*100:.1f}%)" if n else "0"
        print(f"{SOURCE_DISPLAY.get(source, source):<15} {n:<15,} {pres:<20} {neg:<20}")

    # =========================================================================
    # Table 3: Per-Reviewer Performance Detail
    # =========================================================================
    print("\n" + "=" * 80)
    print("Table 3: Per-Reviewer Performance Detail")
    print("=" * 80)

    for source in ['PhenoTagger', 'Verified']:
        if source not in reviews_by_source:
            continue
        display_name = SOURCE_DISPLAY.get(source, source)
        print(f"\nSource: {display_name}")
        print("-" * 80)

        header = f"{'Metric':<25}"
        for rn in reviewer_names:
            header += f" | {rn:<15}"
        print(header)
        print("-" * 80)

        stats = {}
        for rn in reviewer_names:
            stats[rn] = calculate_performance_metrics(reviews_by_source[source], rn, source)

        def fmt(val):
            return f"{val:.1f}%"

        # Strict
        for metric_name, metric_key in [('Strict Precision', 'precision'), ('Strict Recall', 'recall'), ('Strict F1', 'f1')]:
            row = f"{metric_name:<25}"
            for rn in reviewer_names:
                row += f" | {fmt(stats[rn]['strict'][metric_key]):<15}"
            print(row)
        print("-" * 80)

        # Entity
        for metric_name, metric_key in [('Entity Precision', 'precision'), ('Entity Recall', 'recall'), ('Entity F1', 'f1')]:
            row = f"{metric_name:<25}"
            for rn in reviewer_names:
                row += f" | {fmt(stats[rn]['entity'][metric_key]):<15}"
            print(row)
        print("-" * 80)

        # Negation Error Rate
        row = f"{'Negation Error Rate':<25}"
        for rn in reviewer_names:
            row += f" | {fmt(stats[rn]['negation_error_rate']):<15}"
        print(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(get_agreement_stats())
