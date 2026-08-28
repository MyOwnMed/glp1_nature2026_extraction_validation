# Adjudication notes

Reviewing physician's written rationale for the blind adjudication round of 1 July 2026, recorded
alongside the structured verdicts in `adjudication_decisions_blind.csv` and
`recall_adjudications_blind.csv`. Transcribed verbatim from the source document; only the layout has
been changed.

Medication names appearing as "redacted" or "REDACTED" were removed by the de-identification
pipeline before extraction, not by the extractor and not by this release. Where the note recorded a
dose as `*`, the value was absent from the source record.

## Blind adjudication

a. Redacted ophthalmic drops. If the chart had a `*` for the number of drops, this is not the
   model's fault; the dose was not present.

b. Redacted 500 mg tablet. The name was redacted and again a `*` was present for the number of
   tablets to take per day. The model did what it was supposed to do.

c. Redacted ophthalmic solution. Same issue here with the `*` for the number of drops; again, the
   model did what it was supposed to do.

d. Rosuvastatin oral tablet. There are two doses listed, 5 mg and then "continue 10 mg", so either
   the dose was increased or one of the listed doses was incorrect. The model acted correctly given
   the information provided.

e. Omega-3 fatty acid oral product. This is not clear. The model determined that Arcadia-3 is a
   trial evaluating therapy for dry eyes, which is an omega-3 fatty acid product. The trial is
   called Arcadia-3, or the Discovery study. The model did very well.

f. Blood glucose meter kit. While not a medication, it is often listed on the medication list
   because it requires a prescription.

g. Many devices (blood pressure, glucose monitoring and similar) are listed as medications, and
   these are all appropriate.

h. Ketoconazole 2% is the same as 20 mg/mL, so the model was correct.

i. Hypoxia. While 92% saturation does not qualify for oxygen supplementation, it is not normal at
   sea level.

j. Alanine aminotransferase. The criteria for elevation have changed and are much more stringent;
   greater than 40 is of concern. The model is correct.

k. Respiratory distress. It is not clear what kind of distress is referred to in this note.
   Respiratory distress would be included, but any type of distress is included. Usually the term
   is "no acute distress".

## Recall adjudications

- **Antidepressant.** Does not look like the actual medication was listed, so the model was unable
  to identify it.
- **Anxiolytic.** Trazodone was listed and it can be used as an anxiolytic.
- **Shingrix.** Not a miss, as it was only recommended and not prescribed.
- **Ativan.** Listed as lorazepam on the medication list.
- **Butalbital.** A barbiturate that the model figured out was part of a combination medication
  called Fioricet, an older medication for migraine.
- **DuoNeb.** A combination inhaled medication of albuterol and ipratropium, but one that often
  does not make it to the medication list. The medication list is wrong, not the model.
- **Fosamax.** Stated to have been prescribed by rheumatology, but it is not on the medication
  list, so it is not clear whether the patient is taking it. Not a miss.
- **Silvadene.** There is a redacted cream on the medication list and that is most likely
  silvadene; the model could not have known that.
