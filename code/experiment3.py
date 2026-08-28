import os
import json
import re
from collections import defaultdict

# -----------------------------------------------------------------------------
# Normalization
#
# Phenotype names are compared as token sets rather than raw strings so that
# word order and function words do not affect matching ("abnormality of the eye"
# == "eye abnormality").
# -----------------------------------------------------------------------------

FUNCTION_WORDS = {"of", "the", "and", "with", "in", "a", "an", "to", "or", "on", "for", "at", "by"}

# Tokens too generic to establish a match on their own. Used to guard the
# token-subset rule below: a prediction of "abnormality" must not match every
# gold annotation containing the word "abnormality".
GENERIC_TOKENS = {
    "abnormality", "abnormalities", "abnormal", "disorder", "disorders", "disease",
    "diseases", "anomaly", "anomalies", "defect", "defects", "syndrome", "finding",
    "findings", "problem", "problems", "increased", "decreased", "elevated", "reduced",
}


def normalize(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(s).lower())).strip()


def tokenize(s):
    return frozenset(normalize(s).split()) - FUNCTION_WORDS


# -----------------------------------------------------------------------------
# HPO ontology (hp.obo)
#
# Used to expand each gold annotation to its canonical label and synonyms, and
# to resolve predicted strings to concepts for hierarchy matching. Only the GOLD
# annotation's HPO ID is used as an expansion key; the model's own
# 'hpo_matched_name' mapping is never consulted as an ontology assignment, so
# extraction (stage one) and normalization (stage two) remain separable.
# -----------------------------------------------------------------------------

def load_hpo(path):
    names, synonyms, parents, alt_ids, obsolete = {}, defaultdict(set), defaultdict(set), {}, set()
    if not os.path.exists(path):
        print(f"Warning: HPO file {path} not found; matching will fall back to surface strings only.")
        return names, synonyms, parents, alt_ids, obsolete

    current = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line == "[Term]":
                current = None
                continue
            if not line or line.startswith("["):
                continue
            key, _, value = line.partition(": ")
            if key == "id" and value.startswith("HP:"):
                current = value
            elif current is None:
                continue
            elif key == "name":
                names[current] = value
            elif key == "alt_id":
                alt_ids[value] = current
            elif key == "synonym":
                m = re.match(r'"(.*?)"', value)
                if m:
                    synonyms[current].add(m.group(1))
            elif key == "is_a":
                parents[current].add(value.split(" ")[0].split(" !")[0].strip())
            elif key == "is_obsolete" and value == "true":
                obsolete.add(current)
    return names, synonyms, parents, alt_ids, obsolete


script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(script_dir, '..', 'data')

HPO_NAMES, HPO_SYNONYMS, HPO_PARENTS, HPO_ALT_IDS, HPO_OBSOLETE = load_hpo(
    os.path.join(data_dir, "hp.obo"))


def resolve_hpo_id(hpo_id):
    return HPO_ALT_IDS.get(hpo_id, hpo_id)


_ancestor_cache = {}


def hpo_ancestors(hpo_id):
    """Transitive is_a closure for an HPO term."""
    hpo_id = resolve_hpo_id(hpo_id)
    if hpo_id in _ancestor_cache:
        return _ancestor_cache[hpo_id]
    seen, stack = set(), list(HPO_PARENTS.get(hpo_id, ()))
    while stack:
        parent = resolve_hpo_id(stack.pop())
        if parent in seen:
            continue
        seen.add(parent)
        stack.extend(HPO_PARENTS.get(parent, ()))
    _ancestor_cache[hpo_id] = seen
    return seen


# HPO ID -> token sets of its label and synonyms; token set -> HPO IDs
HPO_ID_TOKENS = {}
HPO_LABEL_TO_IDS = defaultdict(set)

for _hid in set(HPO_NAMES) | set(HPO_SYNONYMS):
    _resolved = resolve_hpo_id(_hid)
    _strings = set()
    if _hid in HPO_NAMES:
        _strings.add(HPO_NAMES[_hid])
    _strings |= HPO_SYNONYMS.get(_hid, set())
    _token_sets = {tokenize(s) for s in _strings if normalize(s)}
    HPO_ID_TOKENS.setdefault(_resolved, set()).update(_token_sets)
    for _ts in _token_sets:
        if _ts:
            HPO_LABEL_TO_IDS[_ts].add(_resolved)


# -----------------------------------------------------------------------------
# Matching
# -----------------------------------------------------------------------------

def gold_expansion(surface, hpo_id):
    """Token sets a prediction may match: the gold surface string, the canonical
    HPO label for the gold ID, and every hp.obo synonym of that ID."""
    expansion = {tokenize(surface)}
    if hpo_id:
        expansion |= HPO_ID_TOKENS.get(resolve_hpo_id(hpo_id), set())
    return frozenset(t for t in expansion if t)


def prediction_tokens(item):
    """Token sets contributed by a single prediction."""
    if isinstance(item, dict):
        candidates = {tokenize(item.get('name', ''))}
        if item.get('hpo_matched_name'):
            candidates.add(tokenize(item['hpo_matched_name']))
    else:
        candidates = {tokenize(item)}
    return frozenset(t for t in candidates if t)


def _is_informative(token_set):
    return bool(token_set - GENERIC_TOKENS)


def check_match(gold_tokens, gold_hpo_id, pred_tokens):
    """True if a prediction matches a gold annotation.

    Three layers, any of which is sufficient:
      1. exact     - token-set equality against the gold surface form, the
                     canonical HPO label, or any hp.obo synonym of the gold ID.
      2. subset    - strict token-subset in either direction, where the smaller
                     side carries at least one non-generic token.
      3. hierarchy - the predicted string resolves via hp.obo to the gold
                     concept or to a descendant of it.

    Clinically opposite terms (microcephaly/macrocephaly, hypotonia/hypertonia,
    short/tall stature) are rejected by all three layers: they are neither
    synonyms nor token subsets of one another, and neither is a descendant of
    the other. See test_experiment3.py.
    """
    # 1. exact
    for candidate in pred_tokens:
        if candidate in gold_tokens:
            return True

    # 2. token subset, either direction
    for candidate in pred_tokens:
        for expansion in gold_tokens:
            if candidate < expansion and _is_informative(candidate):
                return True
            if expansion < candidate and _is_informative(expansion):
                return True

    # 3. ontology hierarchy
    if gold_hpo_id:
        target = resolve_hpo_id(gold_hpo_id)
        for candidate in pred_tokens:
            for predicted_id in HPO_LABEL_TO_IDS.get(candidate, ()):
                if predicted_id == target or target in hpo_ancestors(predicted_id):
                    return True
    return False


# -----------------------------------------------------------------------------
# Gold standard
# -----------------------------------------------------------------------------

def parse_gold_standard(file_path):
    """Parse the PubTator-format gold file.

    Each document is an ID line, a text line, then one tab-separated annotation
    per line (start, end, name, HPO ID), terminated by a blank line.

    Returns {doc_id: {"phenotypes": [(name, hpo_id), ...]}}.
    """
    documents = {}
    current_doc_id = None
    current_phenotypes = []

    if not os.path.exists(file_path):
        print(f"Warning: Gold standard file {file_path} not found.")
        return {}

    with open(file_path, 'r') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            if current_doc_id is not None:
                documents[current_doc_id] = {"phenotypes": current_phenotypes}
                current_doc_id = None
                current_phenotypes = []
            i += 1
            continue

        # ID line: consume the ID and the text line that follows it, then
        # continue so the shared increment below does not also swallow the
        # document's first annotation.
        if line.isdigit():
            current_doc_id = line
            current_phenotypes = []
            i += 2
            continue

        # Annotation line
        parts = line.split('\t')
        if len(parts) >= 3:
            try:
                int(parts[0])
                int(parts[1])
                name = parts[2]
                hpo_id = parts[3].strip() if len(parts) > 3 else None
                current_phenotypes.append((name, hpo_id))
            except ValueError:
                pass
        i += 1

    # Add last doc if the file does not end with a blank line
    if current_doc_id is not None:
        documents[current_doc_id] = {"phenotypes": current_phenotypes}

    return documents


def update_name_class_stats(stats, gold_annotations, actual_items):
    gold = [(gold_expansion(name, hpo_id), hpo_id, normalize(name))
            for name, hpo_id in gold_annotations]
    predictions = []
    for item in actual_items:
        name = normalize(item.get('name', '')) if isinstance(item, dict) else normalize(item)
        predictions.append((prediction_tokens(item), name))

    # TP and FN
    for gold_tokens, gold_hpo_id, gold_class in gold:
        if gold_class not in stats:
            stats[gold_class] = {"tp": 0, "fp": 0, "fn": 0}
        found = any(check_match(gold_tokens, gold_hpo_id, pred_tokens)
                    for pred_tokens, _ in predictions)
        stats[gold_class]["tp" if found else "fn"] += 1

    # FP
    for pred_tokens, pred_class in predictions:
        found = any(check_match(gold_tokens, gold_hpo_id, pred_tokens)
                    for gold_tokens, gold_hpo_id, _ in gold)
        if not found:
            if pred_class not in stats:
                stats[pred_class] = {"tp": 0, "fp": 0, "fn": 0}
            stats[pred_class]["fp"] += 1


# -----------------------------------------------------------------------------
# Post-processing validity filter
# -----------------------------------------------------------------------------

GENETIC_KEYWORDS = ['mutation', 'deletion', 'duplication', 'translocation', 'chromosome',
                    'gene', 'allelic', 'mosaicism', 'trisomy', 'monosomy', 'karyotype']

# Word-boundary patterns. Substring matching would remove 'Abnormal EEG' via
# 'normal', and 'renal agenesis' / 'generalized hypotonia' via 'gene'.
_GENETIC_PATTERNS = [re.compile(r"\b" + k + r"s?\b") for k in GENETIC_KEYWORDS]
_NORMAL_PATTERN = re.compile(r"\bnormal\b")
_UNREMARKABLE_PATTERN = re.compile(r"\bunremarkable\b")
_SYNDROME_PATTERN = re.compile(r"\bsyndromes?\b")


def is_valid_phenotype(item):
    if not isinstance(item, dict):
        return False
    name = normalize(item.get('name', ''))

    # 1. Normal findings
    if _NORMAL_PATTERN.search(name) or _UNREMARKABLE_PATTERN.search(name) or 'no abnormal' in name:
        return False

    # 2. Genetic/Molecular
    if any(p.search(name) for p in _GENETIC_PATTERNS):
        return False

    # 3. Disease Names (Heuristic)
    if _SYNDROME_PATTERN.search(name):
        return False

    return True


# -----------------------------------------------------------------------------
# Main Logic
# -----------------------------------------------------------------------------

def main():
    gold_file = os.path.join(data_dir, "GSCplus_test_gold.tsv")
    gold_docs = parse_gold_standard(gold_file)
    n_annotations = sum(len(d["phenotypes"]) for d in gold_docs.values())
    print(f"Loaded {len(gold_docs)} documents ({n_annotations} annotations) from Gold Standard.")

    models = [
        ("sft-gpt-4.1-mini.json", "SFT GPT-4.1 Mini"),
        ("sft-gpt-4.1-nano.json", "SFT GPT-4.1 Nano"),
        ("sft-qwen-4b-instruct.json", "SFT Qwen 4B"),
        ("base-claude-4.5.json", "Base Claude 4.5"),
        ("base-qwen-4b-instruct.json", "Base Qwen 4B"),
        ("base-gpt-4.1-mini.json", "Base GPT-4.1 Mini"),
        ("base-gpt-4.1-nano.json", "Base GPT-4.1 Nano"),
        ("base-gpt-5-mini-thinking-low.json", "Base GPT-5 Mini TL"),
        ("base-gpt-5.2-thinking-low.json", "GPT-5.2 Thinking Low")
    ]

    print("\nMacro Name Metrics")
    print("="*115)
    print(f"{'Model':<25} | {'Type':<10} | {'Prec':<6} | {'Rec':<6} | {'F1':<6} | {'microF1':<7} | {'TP':<5} | {'FP':<5} | {'FN':<5}")

    print("="*115)

    def process_and_report(model_display_name, model_data):
        class_stats_raw = {}
        class_stats_valid = {}

        # Iterate over ALL gold standard documents
        for doc_id in sorted(gold_docs.keys()):
            gold_annotations = gold_docs[doc_id]["phenotypes"]

            # If doc missing in predictions, findings is empty list (all FNs)
            findings = model_data.get(doc_id, [])

            # 1. Raw Results
            update_name_class_stats(class_stats_raw, gold_annotations, findings)

            # 2. Post-processed Results (Validity Filter)
            valid_findings = [f for f in findings if is_valid_phenotype(f)]
            update_name_class_stats(class_stats_valid, gold_annotations, valid_findings)

        def print_macro_row(label, stats_dict):
            micro_tp = micro_fp = micro_fn = 0
            p_list, r_list = [], []

            for name, stats in stats_dict.items():
                tp, fp, fn = stats["tp"], stats["fp"], stats["fn"]
                micro_tp += tp
                micro_fp += fp
                micro_fn += fn
                if (tp + fp) > 0:
                    p_list.append(tp / (tp + fp))
                if (tp + fn) > 0:
                    r_list.append(tp / (tp + fn))

            # Macro P and R are averaged over overlapping but non-identical class
            # sets: precision over classes with at least one prediction, recall
            # over classes with at least one gold annotation. Macro F1 is the
            # harmonic mean of those two averages (the F-score of macro-averages),
            # not the mean of per-class F1 scores. Micro F1 over all annotations
            # is reported alongside; model ranking is identical under both.
            p_macro = sum(p_list)/len(p_list) if p_list else 0
            r_macro = sum(r_list)/len(r_list) if r_list else 0
            f1_macro = 2 * (p_macro * r_macro) / (p_macro + r_macro) if (p_macro + r_macro) > 0 else 0
            micro_f1 = (2 * micro_tp / (2 * micro_tp + micro_fp + micro_fn)
                        if (2 * micro_tp + micro_fp + micro_fn) > 0 else 0)

            print(f"{model_display_name:<25} | {label:<10} | {p_macro:.2f}   | {r_macro:.2f}   | {f1_macro:.2f}   | {micro_f1:.2f}    | {micro_tp:<5} | {micro_fp:<5} | {micro_fn:<5}")

        print_macro_row("Base", class_stats_raw)
        print_macro_row("PP", class_stats_valid)
        print("-" * 115)

    # 1. Single Models
    for json_filename, model_name in models:
        json_file = os.path.join(data_dir, json_filename)
        if not os.path.exists(json_file):
            print(f"{model_name:<25} | FILE NOT FOUND: {json_file}")
            continue

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        process_and_report(model_name, data)

    # 2. Combined Models
    combined_models = [
        ("base-claude-4.5.json", "base-gpt-5.2-thinking-low.json", "Combined Sonnet+GPT5.2"),
        ("base-gpt-4.1-mini.json", "base-qwen-4b-instruct.json", "Combined G4.1M+Qwen4B"),
        ("sft-gpt-4.1-mini.json", "sft-qwen-4b-instruct.json", "Combined SFT G4.1M+Qwen4B"),
    ]

    for f1_name, f2_name, model_name in combined_models:
        file1 = os.path.join(data_dir, f1_name)
        file2 = os.path.join(data_dir, f2_name)

        if not os.path.exists(file1):
            print(f"{model_name:<25} | FILE NOT FOUND: {file1}")
            continue
        if not os.path.exists(file2):
            print(f"{model_name:<25} | FILE NOT FOUND: {file2}")
            continue

        with open(file1, 'r', encoding='utf-8') as f: data1 = json.load(f)
        with open(file2, 'r', encoding='utf-8') as f: data2 = json.load(f)

        combined_data = {}
        all_doc_ids = set(data1.keys()) | set(data2.keys())

        for doc_id in all_doc_ids:
            items1 = data1.get(doc_id, [])
            items2 = data2.get(doc_id, [])

            # Combine and deduplicate based on (name, hpo_matched_name)
            combined_map = {}
            for item in items1 + items2:
                if isinstance(item, dict):
                    key = (item.get('name', ''), item.get('hpo_matched_name', ''))
                    combined_map[key] = item
                else:
                    key = (str(item), str(item))
                    combined_map[key] = item

            combined_data[doc_id] = list(combined_map.values())

        process_and_report(model_name, combined_data)

    print("="*115)

if __name__ == "__main__":
    main()
