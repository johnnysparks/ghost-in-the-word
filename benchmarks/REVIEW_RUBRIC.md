# Human review rubric

Use this form for a blind review of a ranked list of translation differences. Reviewers should see the reference, both renderings, and the comparison method label, but should not see the model rank or the other reviewer’s judgment.

The natural benchmark packet contains 30 highest-ranked leads and a seeded background
sample. Treat every item as an independent close-reading question; the packet order is
not meaningful and the background sample is not a control label.

For each item, record:

| Field | Values |
| --- | --- |
| Useful for close reading | yes / no / uncertain |
| Difference type | wording / likely meaning / source-text issue / alignment issue / unclear |
| Confidence | low / medium / high |
| Evidence | short note citing the displayed words or source reference |

“Useful for close reading” means the item deserves a reader’s attention. It does not mean one translation is wrong. A legitimate ambiguity, a genre effect, a source-text variant, and a meaningful change can all be useful findings.

For source-conditioned fidelity judgments, use reviewers competent in the relevant source language and require a specified source edition. Preserve disagreements and abstentions; do not turn an unresolved judgment into a binary label.

## JSON response shape

Return one document per reviewer. Keep the `id` values from the blind packet, but do
not add a model score or rank to the response:

```json
{
  "schemaVersion": 1,
  "reviewerId": "reviewer-1",
  "items": [
    {
      "id": "JHN-3-16",
      "useful": "yes",
      "differenceType": "likely meaning",
      "confidence": "medium",
      "evidence": "The participant and causal relation differ."
    }
  ]
}
```

Use `uncertain` when the reviewer cannot make a useful/not-useful judgment. The
aggregation script reports this separately and preserves each reviewer’s vote. The
natural-evaluation gate is eligible only after two reviewers have judged every one of
the 30 top-ranked items; a useful-rate result before that point is descriptive only.
