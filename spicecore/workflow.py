"""Creative briefs and a local review desk."""

from __future__ import annotations

import hashlib
import hmac
import html
import random

from .core import Store


def build_briefs(personas: list[dict], theme: str, channel: str, seed: int | None = None) -> list[dict]:
    """Draft testable directions without claiming external demand or generating images."""
    if not theme.strip() or not channel.strip():
        raise ValueError('Theme and channel are required')
    rng = random.Random(seed)
    briefs = []
    for person in personas:
        interests = list(person['hobbies'])
        chosen = rng.choice(interests)
        prompt = (f"Original fictional AI-generated adult character {person['name']}, age {person['age']}; "
                  f"distinctive original look: {person['visual']}; engaged in {chosen}; "
                  f"theme: {theme}; candid detail, coherent anatomy, same identity across the series. "
                  "Do not resemble a public figure. No youth-coded sexual styling.")
        briefs.append({'persona_id': person['id'], 'persona_name': person['name'],
                       'reference_version': person['version'], 'theme': theme,
                       'channel': channel, 'interest': chosen, 'format': 'still',
                       'evidence_level': 'hypothesis', 'prompt': prompt,
                       'test_question': f'Does {theme} featuring {chosen} draw qualified engagement for {person["name"]}?',
                       'disclosure': person['disclosure']})
    return briefs


def apply_review(store: Store, cid: str, decision: str, reviewer: str,
                 note: str, supplied_token: str, csrf_token: str) -> dict:
    if not hmac.compare_digest(supplied_token, csrf_token):
        raise PermissionError('Invalid review token')
    return store.review(cid, decision, reviewer, note)


def render_dashboard(store: Store, personas: list[dict], csrf_token: str) -> str:
    safe = lambda value: html.escape(str(value), quote=True)
    rows = store.db.execute("SELECT * FROM candidates WHERE status='proposed' ORDER BY created_at").fetchall()
    cards = []
    # Review is intentionally one-at-a-time: disposing the current item reveals the next.
    for row in rows[:1]:
        buttons = ''.join(f'<button name="decision" value="{d}">{d.title()}</button>'
                          for d in ('approved', 'revise', 'rejected'))
        cards.append(f'''<article><h3>{safe(row['persona_id'])} · {safe(row['theme'])}</h3>
          <p>{safe(row['channel'])} · {safe(row['format'])} · {safe(row['offer'])}</p>
          {f'<img class="asset" src="/asset/{safe(row["id"])}?token={safe(csrf_token)}" alt="Generated asset for {safe(row["persona_id"])}" loading="eager">' if row['asset_uri'] else ''}
          <p class="asset-path">Asset: {safe(row['asset_uri'] or 'pending generation')}</p>
          <pre>{safe(row['prompt'] or '')}</pre>
          <form method="post" action="/review">
            <input type="hidden" name="token" value="{safe(csrf_token)}">
            <input type="hidden" name="candidate_id" value="{safe(row['id'])}">
            <label>Reviewer <input name="reviewer" required></label>
            <label>Note <input name="note"></label>{buttons}
          </form></article>''')
    stat_rows = ''.join(f'<tr><td>{safe(s["name"])}</td><td>{s["published"]}</td><td>{s["clicks"]}</td><td>{s["net_cents"] / 100:.2f}</td></tr>'
                        for s in store.stats(personas))
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Spice Hoes · local review</title><style>
      body{{font:16px system-ui;background:#171320;color:#f7f1fb;max-width:900px;margin:auto;padding:24px}}
      article{{background:#292135;border:1px solid #62546f;border-radius:14px;padding:18px;margin:14px 0}}
      input,button{{font:inherit;margin:6px;padding:8px;border-radius:7px}}button{{cursor:pointer}}
      .asset{{display:block;width:100%;max-height:75vh;object-fit:contain;background:#0e0b12;border-radius:12px;margin:12px 0}}
      .asset-path{{font-size:.8rem;opacity:.7;overflow-wrap:anywhere}}
      pre{{white-space:pre-wrap;overflow-wrap:anywhere}}table{{width:100%;text-align:left}}th,td{{padding:8px;border-bottom:1px solid #62546f}}
      </style><h1>Review queue</h1><p>{len(rows)} awaiting review. Approval records a decision; it does not publish content.</p>
      {''.join(cards) or '<p>No candidates waiting.</p>'}
      <h2>Observed totals</h2><table><tr><th>Persona</th><th>Published</th><th>Clicks</th><th>Net $</th></tr>{stat_rows}</table></html>'''
