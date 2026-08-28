# GLP-1 technical development and validation code — Part I

Code and evaluation inputs accompanying "Computable longitudinal patient journeys from structured and unstructured EHR data" paper for publication in Nature Medicine.
This repository covers the extraction validation experiments; the downstream outcome analysis is released separately as Part II. For
methods, definitions and interpretation of any result, refer to the paper.

## Running

Python 3.12.

```bash
pip install -r code/requirements.txt
bash code/run.sh
```

`run.sh` runs the unit tests and the experiments against `data/` and writes to `results/`. The
tests alone run with no third-party packages:

```bash
python3 -m unittest discover -s code -p 'test_*.py' -v
```

## Where things are

```
code/          experiment scripts, the shared agreement module, tests and run.sh
data/          the inputs the experiments read including the physician labels on the extractions
prompts/       the prompts used to generate the model outputs in data/
results/       committed outputs of a full run
adjudication/  the verification of physician disagreement on the extractions 
clustering/    the concept-discovery cluster taxonomy
```

| Script | Reads | Writes |
|---|---|---|
| `code/experiment2.py` | `data/MD{1,2,3}.json` | `results/experiment2_results.txt` |
| `code/experiment3_med.py` | `data/MD{1,2,3}_med.json`, `data/med_aggregate_stats.json` | `results/experiment3_med_results.txt` |
| `code/experiment3.py` | `data/GSCplus_test_gold.tsv`, `data/hp.obo`, `data/{base,sft}-*.json` | `results/experiment3_results.txt` |
| `code/experiment4.py` | `data/hpo_timeline_prevalence.json`, `data/hp.obo` | `results/experiment4*.txt`, `results/*_experiment4*.png` |

`code/CHANGES.md` records the changes made in response to code review.

## Data and licensing

The underlying clinical notes are licensed from Harris Computer Systems and are not distributed;
see the paper's Data availability statement. The RespondHealth extraction platform is proprietary
and not distributed; see the paper's Code availability statement. `data/hp.obo` and
`data/GSCplus_test_gold.tsv` are third-party materials carrying their own terms — see `NOTICE`.

The code is released under the Apache License 2.0 (`LICENSE`). Please cite the paper rather than
the repository; `CITATION.cff` carries the machine-readable citation record.