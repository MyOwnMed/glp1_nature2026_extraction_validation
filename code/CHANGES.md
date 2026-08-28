# Changes made in response to code review

All changes are in `code/`. Input data in `data/` is unchanged.

## 1. Gold-standard parser dropped the first annotation of every document

`experiment3.py:parse_gold_standard` advanced twice on the ID line (ID -> text)
and then fell through to a shared `i += 1`, consuming each document's first
annotation. Documents with no annotations also lost their blank-line separator
and disappeared.

**Fix:** `continue` after consuming the ID and text lines. The parser now also
retains the HPO ID in column 4, which the matcher requires.

Gold now parses as **206 documents / 1,949 annotations** (previously 199 /
1,750). The seven documents with no annotations are retained as empty: they
carry only Mode-of-Inheritance or obsolete terms, which fall outside the HPO
phenotypic-abnormality branch that the standard GSC+ protocol evaluates, so they
contribute zero gold annotations either way.

## 2. String matching accepted clinically opposite phenotypes

`check_match` accepted a `difflib` ratio of 0.5. Similarity is anti-correlated
with clinical correctness here: microcephaly/macrocephaly scores 0.917 while
deafness/hearing loss scores 0.50, so no threshold separates opposites from
synonyms. Raising the threshold to 0.8 still admitted 9 of 13 opposite pairs
while costing 7-13 F1 points.

**Fix:** `difflib` removed. Matching is now synonym- and hierarchy-aware, keyed
on the **gold** HPO ID (present on all 1,949 annotations):

1. **exact** - token-set equality against the gold surface form, the canonical
   HPO label, or any `hp.obo` synonym of the gold ID
2. **subset** - strict token-subset in either direction, where the smaller side
   carries at least one non-generic token
3. **hierarchy** - the predicted string resolves via `hp.obo` to the gold concept
   or a descendant of it

Layer 3 resolves the prediction's own string against the ontology on the scoring
side; the model's `hpo_matched_name` is never used as an ontology assignment, so
extraction (stage one) and normalization (stage two) stay separately measurable.

## 3. Post-processing filter matched substrings inside words

`'normal' in name` caught *ab*normal; `'gene' in name` caught a*gene*sis,
*gene*ralized and de*gene*ration, so `Abnormal EEG`, `renal agenesis` and
`generalized hypotonia` were all discarded as invalid. 485 predictions across the
nine prediction files were removed purely this way.

**Fix:** word-boundary regexes in `is_valid_phenotype`.

## 4. Multi-agent SFT combination was never computed

`combined_models` contained only base-model pairs, so no SFT+SFT combination
existed in the code.

**Fix:** added `sft-gpt-4.1-mini` + `sft-qwen-4b-instruct` as
`Combined SFT G4.1M+Qwen4B`.

## 5. The two agreement tables used different estimators

`experiment2.py` had no PABAK path and used an exact `pe == 1` comparison;
`experiment3_med.py` substituted PABAK when `kappa < pabak * 0.5 and po > 0.5`,
which compares the magnitudes of two statistics rather than testing for
degeneracy.

**Fix:** new shared module `agreement.py`, imported by both. It tests the
degeneracy condition directly (a constant rater marginal, or `p_e -> 1` within
`1e-10`) and reports **Cohen's kappa and PABAK in separate columns for every
pair**, alongside `p_o` and `p_e`, so no column mixes estimators and a reader can
verify the degeneracy.

For medications, all three "Ours (GPT)" pairs are degenerate: MD1-MD2 and MD1-MD3
are 22/22 Present/Present (kappa undefined, 0/0; PABAK 1.000), and MD2-MD3 has a
constant MD2 marginal (kappa exactly 0.000 despite 95.8% observed agreement;
PABAK 0.917). The baselines are not degenerate and retain valid Cohen's kappa.

## 6. Negation error rate had no denominator context

**Fix:** `experiment2.py` now prints **Table 2b**, the emitted-negation
distribution. PhenoTagger asserts "present" on 96.0% of its extractions and
negated on 4.0%; our pipeline asserts negated on 78.0%. The negation error rates
describe a capability difference rather than competing error rates on a shared
task.

## 7. Ambiguous "N" column

`experiment2.py` reported `total_extracted + missing_count`;
`experiment3_med.py` reported `total_extracted`. The medication source file
carries no missing count.

**Fix:** both now report **`N (extracted)`**, and `experiment2.py` reports
`N (missing)` as its own column.

## 8. `run.sh` reported success unconditionally

No `set -e`, exit codes unchecked, and tracebacks written into the results files
where they were invisible.

**Fix:** `set -euo pipefail`, every step's exit status recorded, the tail of the
log echoed to stderr on failure, and a non-zero exit with a list of failed steps.
Remaining steps still run so one failure does not mask others.

## 9. Experiment 4 normalization and exclusion undocumented

**Fix:** added `--no-normalize` for an unnormalized sensitivity analysis (run
automatically by `run.sh`), and documented why `HP:0000819` (Diabetes mellitus)
is excluded.

## 10. Dead code and dependencies

Removed unused `get_label` (`experiment3_med.py`) and `source_names`
(`experiment2.py`). Added pinned `requirements.txt`.

## Tests

`test_experiment3.py` pins all three scoring defects: parser counts
(206 / 1,949, first annotation retained, HPO ID coverage, empty documents
retained), rejection of 14 opposite or wrong-concept pairs, acceptance of 8
legitimate naming variants, and word-boundary filter behaviour. Run via
`run.sh` or `python3 -m unittest discover -s code -p 'test_*.py' -v`.

## Note on macro F1

Macro precision and recall are averaged over overlapping but non-identical class
sets: precision over classes with at least one prediction, recall over classes
with at least one gold annotation. Macro F1 is the harmonic mean of those two
averages (the F-score of macro-averages), not the mean of per-class F1 scores.
This convention is retained and now stated explicitly in the code and in the
Table S1a footnote. Micro F1 over all 1,949 annotations is printed alongside;
model ranking is identical under both.
