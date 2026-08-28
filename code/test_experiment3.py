"""Regression tests pinning the three defects found in code review.

Run: python3 -m unittest discover -s code -p 'test_*.py' -v
"""
import os
import unittest

import experiment3 as e3

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
GOLD = os.path.join(DATA_DIR, "GSCplus_test_gold.tsv")


def match(gold_name, gold_hpo_id, predicted_name):
    """Match a single predicted name against a single gold annotation."""
    return e3.check_match(
        e3.gold_expansion(gold_name, gold_hpo_id),
        gold_hpo_id,
        e3.prediction_tokens({"name": predicted_name, "hpo_matched_name": ""}),
    )


class TestGoldParser(unittest.TestCase):
    """The parser previously advanced twice on the ID line and then fell through
    to a shared increment, consuming the first annotation of every document."""

    @classmethod
    def setUpClass(cls):
        cls.docs = e3.parse_gold_standard(GOLD)

    def test_document_count(self):
        self.assertEqual(len(self.docs), 206)

    def test_annotation_count(self):
        total = sum(len(d["phenotypes"]) for d in self.docs.values())
        self.assertEqual(total, 1949)

    def test_first_annotation_is_retained(self):
        # Document 1003450 begins with 'brachydactyly' at offset 14.
        names = [n for n, _ in self.docs["1003450"]["phenotypes"]]
        self.assertEqual(names[0], "brachydactyly")

    def test_every_annotation_carries_an_hpo_id(self):
        missing = [(n, h) for d in self.docs.values()
                   for n, h in d["phenotypes"]
                   if not (h or "").startswith("HP:")]
        self.assertEqual(missing, [])

    def test_documents_with_no_annotations_are_retained(self):
        # Seven abstracts carry only Mode-of-Inheritance or obsolete terms and
        # therefore hold no annotations inside the phenotypic-abnormality
        # branch. They must survive parsing as empty documents.
        empty = [d for d, v in self.docs.items() if not v["phenotypes"]]
        self.assertEqual(len(empty), 7)


class TestMatcherRejectsOpposites(unittest.TestCase):
    """A difflib ratio of 0.5 accepted clinically opposite phenotypes, because
    an antonymous morpheme is orthographically tiny (microcephaly/macrocephaly
    scores 0.917) while genuine synonyms score low (deafness/hearing loss 0.50).
    No threshold separates them; synonym and hierarchy matching does."""

    OPPOSITES = [
        ("microcephaly", "HP:0000252", "macrocephaly"),
        ("hypotonia", "HP:0001252", "hypertonia"),
        ("deafness", "HP:0000365", "blindness"),
        ("increased muscle tone", "HP:0001276", "decreased muscle tone"),
        ("short stature", "HP:0004322", "tall stature"),
        ("polydactyly", "HP:0010442", "syndactyly"),
        ("hyperglycemia", "HP:0003074", "hypoglycemia"),
        ("hypertension", "HP:0000822", "hypotension"),
        ("hyperreflexia", "HP:0001347", "hyporeflexia"),
        ("macrognathia", "HP:0000303", "micrognathia"),
        ("hypercalcemia", "HP:0003072", "hypocalcemia"),
        ("bradycardia", "HP:0001662", "tachycardia"),
        ("hyperthyroidism", "HP:0000836", "hypothyroidism"),
        # wrong organ, high orthographic similarity (difflib ratio 0.77)
        ("cardiac anomalies", "HP:0001627", "hand anomalies"),
    ]

    def test_opposites_are_rejected(self):
        for gold, hpo_id, predicted in self.OPPOSITES:
            with self.subTest(gold=gold, predicted=predicted):
                self.assertFalse(match(gold, hpo_id, predicted))


class TestMatcherAcceptsVariants(unittest.TestCase):
    """Legitimate naming variance must still match. The model emits free-text
    names; ontology normalization is a separate downstream stage."""

    VARIANTS = [
        ("seizures", "HP:0001250", "epilepsy"),
        ("hearing impairment", "HP:0000365", "hearing loss"),
        ("hearing impairment", "HP:0000365", "deafness"),
        ("intellectual disability", "HP:0001249", "mental retardation"),
        ("abnormal eeg", "HP:0002353", "abnormal electroencephalogram"),
        ("schwannomas", "HP:0100008", "vestibular schwannoma"),
        ("hypopigmented", "HP:0001010", "hypopigmentation"),
        ("ear malformations", "HP:0000598", "external ear malformation"),
    ]

    def test_variants_are_accepted(self):
        for gold, hpo_id, predicted in self.VARIANTS:
            with self.subTest(gold=gold, predicted=predicted):
                self.assertTrue(match(gold, hpo_id, predicted))

    def test_generic_token_alone_does_not_match(self):
        # 'abnormality' is a subset of the gold token set but carries no
        # informative token, so the subset rule must not fire.
        self.assertFalse(match("abnormality of the eye", "HP:0000478", "abnormality"))


class TestValidityFilter(unittest.TestCase):
    """'normal' in name matched abnormal; 'gene' matched agenesis, generalized
    and degeneration. 485 predictions were dropped this way across the nine
    prediction files."""

    KEEP = [
        "Abnormal EEG",
        "renal agenesis",
        "generalized hypotonia",
        "retinal degeneration",
        "bilateral renal agenesis",
        "abnormal electroencephalogram",
    ]
    DROP = [
        "normal findings",
        "unremarkable exam",
        "no abnormality detected",
        "FBN1 gene mutation",
        "chromosome 15 deletion",
        "Marfan syndrome",
        "trisomy 21",
    ]

    def test_valid_phenotypes_are_kept(self):
        for name in self.KEEP:
            with self.subTest(name=name):
                self.assertTrue(e3.is_valid_phenotype({"name": name}))

    def test_invalid_phenotypes_are_dropped(self):
        for name in self.DROP:
            with self.subTest(name=name):
                self.assertFalse(e3.is_valid_phenotype({"name": name}))


if __name__ == "__main__":
    unittest.main()
