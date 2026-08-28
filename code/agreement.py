"""Shared inter-rater agreement estimator.

Both agreement tables (experiment2.py for phenotypes, experiment3_med.py for
medications) import from this module so they use an identical estimator.

Cohen's kappa is degenerate whenever a rater's marginal has no variance. If one
rater assigns every item to the same category, then for that category
p_o = m/n and p_e = (n*m)/n^2 = m/n, so p_o == p_e exactly and

    kappa = (p_o - p_e) / (1 - p_e) = 0

for *any* level of observed agreement. Two clinicians agreeing on 46 of 48 items
still yield kappa = 0.000. Where both marginals collapse onto a single category,
p_e = 1 and kappa is 0/0, i.e. undefined.

PABAK (prevalence-adjusted bias-adjusted kappa, 2*p_o - 1) is the standard
response to this degeneracy. This module reports Cohen's kappa and PABAK as
separate values for every pair, together with p_o and p_e, so a reader can
verify the degeneracy rather than take a footnote on trust. The degeneracy flag
tests the degeneracy condition itself -- a constant rater marginal, or p_e -> 1
-- rather than comparing the magnitudes of the two statistics.
"""

N_CLASSES = 3          # 0 = Present, 1 = Absent, 2 = Rejected
TOL = 1e-10


def confusion_matrix(items, r1, r2):
    """3x3 matrix of paired labels for the items both reviewers scored."""
    common = [k for k, v in items.items() if r1 in v and r2 in v]
    matrix = [[0] * N_CLASSES for _ in range(N_CLASSES)]
    for k in common:
        matrix[items[k][r1]][items[k][r2]] += 1
    return matrix, len(common)


def agreement_stats(matrix, n):
    """Return p_o, p_e, Cohen's kappa (None if undefined), PABAK, degeneracy."""
    if n == 0:
        return None

    po = sum(matrix[x][x] for x in range(N_CLASSES)) / n

    row_totals = [sum(matrix[x][y] for y in range(N_CLASSES)) for x in range(N_CLASSES)]
    col_totals = [sum(matrix[y][x] for y in range(N_CLASSES)) for x in range(N_CLASSES)]
    pe = sum(row_totals[x] * col_totals[x] for x in range(N_CLASSES)) / (n * n)

    pabak = 2 * po - 1

    # Degeneracy: either rater used a single category, or p_e is numerically 1.
    constant_marginal = (max(row_totals) == n) or (max(col_totals) == n)
    pe_saturated = abs(1 - pe) < TOL
    degenerate = constant_marginal or pe_saturated

    kappa = None if pe_saturated else (po - pe) / (1 - pe)

    return {
        'n': n,
        'po': po,
        'pe': pe,
        'kappa': kappa,              # None when undefined (0/0)
        'pabak': pabak,
        'degenerate': degenerate,
        'constant_marginal': constant_marginal,
    }


def pairwise_agreement(items):
    """Agreement statistics for every reviewer pair present in `items`.

    `items` maps an item key to {reviewer: label}.
    """
    reviewers = sorted({r for v in items.values() for r in v})
    results = []
    for i in range(len(reviewers)):
        for j in range(i + 1, len(reviewers)):
            r1, r2 = reviewers[i], reviewers[j]
            matrix, n = confusion_matrix(items, r1, r2)
            if n == 0:
                continue
            stats = agreement_stats(matrix, n)
            stats['pair'] = f"{r1} vs {r2}"
            results.append(stats)
    return results


def format_kappa(stats):
    return "undefined" if stats['kappa'] is None else f"{stats['kappa']:.3f}"


HEADER = ('{:<15} {:<7} {:<15} {:<7} {:<7} {:<11} {:<8} {:<10}'
          .format('Rater Pair', 'N', 'Agreement (%)', 'p0', 'pe', "Cohen's K", 'PABAK', 'Degenerate'))


def format_row(stats):
    return (f"{stats['pair']:<15} {stats['n']:<7} {stats['po']*100:<14.1f} "
            f"{stats['po']:<7.3f} {stats['pe']:<7.3f} {format_kappa(stats):<11} "
            f"{stats['pabak']:<8.3f} {'yes' if stats['degenerate'] else 'no':<10}")
