#!/usr/bin/env python3
"""Render a blind mapping-review packet as a self-contained HTML form."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Mapping

from ghost_in_word.mapping_review import validate_mapping_review_packet


def _text(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def render_mapping_review_form(
    packet: Mapping[str, object],
    *,
    reviewer_id: str = "",
    title: str = "Blind alignment review",
) -> str:
    """Return an HTML form that emits a validated mapping-review response."""

    summary = validate_mapping_review_packet(packet)
    source = packet["source"]
    assert isinstance(source, Mapping)
    left = source["leftEdition"]
    right = source["rightEdition"]
    assert isinstance(left, Mapping) and isinstance(right, Mapping)
    packet_json = (
        json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    items = packet["items"]
    assert isinstance(items, list)
    cards: list[str] = []
    for index, item in enumerate(items, start=1):
        assert isinstance(item, Mapping)
        left_refs = ", ".join(str(ref) for ref in item["leftReferences"])
        right_refs = ", ".join(str(ref) for ref in item["rightReferences"])
        cards.append(
            f'''<article class="review-card" data-item-id="{_text(item["id"])}">
  <div class="card-heading"><span>{index} / {summary["itemCount"]}</span><h2>{_text(item["mappingType"])}</h2><code>{_text(item["id"])}</code></div>
  <div class="renderings">
    <section><h3>{_text(left.get("name", left.get("id")))}</h3><p class="refs">{_text(left_refs) or "(no reference)"}</p><p>{_text(item["leftText"]) or "(no text)"}</p></section>
    <section><h3>{_text(right.get("name", right.get("id")))}</h3><p class="refs">{_text(right_refs) or "(no reference)"}</p><p>{_text(item["rightText"]) or "(no text)"}</p></section>
  </div>
  <div class="judgment-grid">
    <label>Mapping decision
      <select data-field="decision" required>
        <option value="">Select decision</option>
        <option value="accept">Accept candidate mapping</option>
        <option value="reject">Reject candidate mapping</option>
        <option value="uncertain">Uncertain</option>
      </select>
    </label>
    <label class="evidence-field">Evidence
      <textarea data-field="evidence" rows="2" required placeholder="Cite the displayed text or source reference."></textarea>
    </label>
  </div>
</article>'''
        )

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; color: #1d2433; background: #f5f6f8; }}
    body {{ margin: 0; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 1rem clamp(1rem, 4vw, 3rem); background: #18253a; color: #fff; box-shadow: 0 2px 10px #0003; }}
    header h1 {{ margin: 0 0 .35rem; font-size: 1.35rem; }}
    header p {{ margin: .3rem 0; color: #dbe7fa; }}
    main {{ max-width: 75rem; margin: 0 auto; padding: 1rem clamp(1rem, 4vw, 3rem) 4rem; }}
    .instructions, .review-card {{ background: #fff; border: 1px solid #d9dee8; border-radius: .7rem; box-shadow: 0 1px 3px #17233b12; }}
    .instructions {{ padding: 1rem 1.2rem; margin-bottom: 1rem; }}
    .instructions p {{ margin: .45rem 0; }}
    .toolbar {{ display: flex; flex-wrap: wrap; align-items: end; gap: .75rem 1rem; margin-top: 1rem; }}
    label {{ display: grid; gap: .3rem; font-weight: 650; }}
    .attestation {{ display: flex; align-items: center; gap: .45rem; }}
    .attestation input {{ width: 1.1rem; height: 1.1rem; }}
    input, select, textarea, button {{ font: inherit; }}
    input, select, textarea {{ border: 1px solid #aeb8c8; border-radius: .4rem; padding: .5rem; color: inherit; background: #fff; }}
    input:focus, select:focus, textarea:focus, button:focus {{ outline: 3px solid #85b7ff; outline-offset: 2px; }}
    input {{ min-width: 14rem; }}
    button {{ border: 0; border-radius: .45rem; padding: .62rem .9rem; background: #2769d8; color: #fff; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #596579; }}
    #progress {{ font-weight: 700; }}
    #status {{ min-height: 1.4em; margin: .65rem 0 0; }}
    .review-card {{ padding: 1rem 1.2rem; margin: 1rem 0; scroll-margin-top: 7rem; }}
    .review-card.incomplete {{ border-color: #c67b1d; }}
    .card-heading {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: .45rem .75rem; }}
    .card-heading h2 {{ margin: 0; font-size: 1.15rem; }}
    .card-heading code, .refs {{ color: #5b6474; }}
    .renderings {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: 1rem 0; }}
    .renderings section {{ border-left: 3px solid #b8c8e6; padding-left: .75rem; }}
    .renderings h3 {{ margin: 0 0 .4rem; font-size: .95rem; }}
    .renderings p {{ margin: .4rem 0; line-height: 1.55; white-space: pre-wrap; }}
    .refs {{ font-size: .9rem; }}
    .judgment-grid {{ display: grid; grid-template-columns: minmax(15rem, 1fr) 2fr; gap: .75rem; }}
    .evidence-field {{ min-width: 0; }}
    textarea {{ resize: vertical; min-height: 3.2rem; }}
    @media (max-width: 44rem) {{ .renderings, .judgment-grid {{ grid-template-columns: 1fr; }} input {{ min-width: 0; width: 100%; }} }}
  </style>
</head>
<body>
<header>
  <h1>{_text(title)}</h1>
  <p>{_text(left.get("name", left.get("id")))} vs. {_text(right.get("name", right.get("id")))}</p>
  <p id="progress" aria-live="polite">0 of {summary["itemCount"]} completed</p>
</header>
<main>
  <section class="instructions" aria-labelledby="instructions-heading">
    <h2 id="instructions-heading">Instructions</h2>
    <p>Review each candidate independently. Accept only when the displayed source references and text belong in one comparison unit.</p>
    <p>Reject a candidate that joins unrelated passages. Use <em>uncertain</em> when the pinned snapshots do not support a confident decision. Cite the displayed text or a source reference.</p>
    <div class="toolbar">
      <label>Reviewer ID<input id="reviewer-id" value="{_text(reviewer_id)}" autocomplete="off" required></label>
      <label class="attestation"><input id="independence" type="checkbox"> I reviewed independently</label>
      <button type="button" id="download">Download response JSON</button>
      <button type="button" id="reset" class="secondary">Clear form</button>
    </div>
    <p id="status" role="status" aria-live="polite"></p>
  </section>
  <form id="review-form" novalidate>{''.join(cards)}</form>
</main>
<script type="application/json" id="packet-data">{packet_json}</script>
<script>
(() => {{
  const packet = JSON.parse(document.getElementById('packet-data').textContent);
  const cards = [...document.querySelectorAll('[data-item-id]')];
  const progress = document.getElementById('progress');
  const status = document.getElementById('status');
  const reviewer = document.getElementById('reviewer-id');
  const independence = document.getElementById('independence');
  function complete(card) {{ return ['decision', 'evidence'].every((name) => card.querySelector(`[data-field="${{name}}"]`).value.trim()); }}
  function update() {{ const count = cards.filter(complete).length; progress.textContent = `${{count}} of ${{cards.length}} completed`; cards.forEach((card) => card.classList.toggle('incomplete', !complete(card))); }}
  function collect() {{ return cards.map((card) => ({{ id: card.dataset.itemId, decision: card.querySelector('[data-field="decision"]').value, evidence: card.querySelector('[data-field="evidence"]').value.trim() }})); }}
  function download() {{
    status.textContent = '';
    const reviewerId = reviewer.value.trim();
    const incomplete = cards.filter((card) => !complete(card));
    if (!reviewerId) {{ reviewer.focus(); status.textContent = 'Enter a reviewer ID before downloading.'; return; }}
    if (!independence.checked) {{ independence.focus(); status.textContent = 'Confirm that you reviewed the packet independently.'; return; }}
    if (incomplete.length) {{ incomplete[0].querySelector('[data-field="decision"]').focus(); status.textContent = `Complete all decisions and evidence first (${{incomplete.length}} remaining).`; return; }}
    const response = {{ schemaVersion: 1, kind: 'blind-mapping-review-response', reviewerId, independence: 'declared', items: collect() }};
    const url = URL.createObjectURL(new Blob([JSON.stringify(response, null, 2) + '\\n'], {{ type: 'application/json' }}));
    const link = document.createElement('a'); link.href = url; link.download = `${{reviewerId.replace(/[^a-z0-9_-]+/gi, '_')}}-mapping-review.json`; link.click(); URL.revokeObjectURL(url); status.textContent = 'Response downloaded.';
  }}
  cards.flatMap((card) => [...card.querySelectorAll('select, textarea')]).forEach((field) => field.addEventListener('input', update));
  document.getElementById('download').addEventListener('click', download);
  document.getElementById('reset').addEventListener('click', () => {{ if (!window.confirm('Clear every decision in this form?')) return; document.getElementById('review-form').reset(); independence.checked = false; status.textContent = 'Form cleared.'; update(); }});
  update();
}})();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer-id", default="")
    parser.add_argument("--title", default="Blind alignment review")
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    validate_mapping_review_packet(packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_mapping_review_form(packet, reviewer_id=args.reviewer_id, title=args.title), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "itemCount": len(packet["items"])}, indent=2))


if __name__ == "__main__":
    main()
