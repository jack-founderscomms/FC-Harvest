"""
Generate a self-contained static HTML file from the harvest database.
Output: docs/index.html  (served by GitHub Pages)

Run directly:  python generate_static.py
Or via:        python run.py static
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from harvest import db as database
from harvest.runner import load_config
from harvest.filters import categories_for_item

OUTPUT = ROOT / "docs" / "index.html"


def generate():
    database.init_db()
    config = load_config()
    label_map = _build_label_map(config)
    all_source_ids = list(label_map.keys())

    keyword_categories: dict = config.get("keyword_categories", {})

    with database.get_db() as conn:
        all_items = database.get_items(conn, limit=2000)
        recent_runs = database.get_recent_runs(conn, limit=5)
        source_health = database.get_source_health(conn)

    # Enrich items with matched categories
    for item in all_items:
        item["matched_categories"] = categories_for_item(
            item.get("matched_kws") or [], keyword_categories
        )

    # Group by source
    grouped: dict[str, list] = defaultdict(list)
    for item in all_items:
        grouped[item["source_id"]].append(item)

    # Category counts
    category_counts: dict[str, int] = {cat: 0 for cat in keyword_categories}
    for item in all_items:
        for cat in (item.get("matched_categories") or []):
            if cat in category_counts:
                category_counts[cat] += 1

    # Keyword frequency (still used for old compat)
    kw_counts: dict[str, int] = defaultdict(int)
    for item in all_items:
        for kw in (item.get("matched_kws") or []):
            kw_counts[kw] += 1
    top_keywords = sorted(kw_counts.items(), key=lambda x: -x[1])[:20]

    # Errored sources
    errored = [
        {
            "label": label_map.get(sid, sid),
            "message": h.get("message", ""),
            "checked_at": (h.get("checked_at") or "")[:16].replace("T", " "),
        }
        for sid, h in source_health.items()
        if h.get("status") == "error"
    ]

    # Build ordered groups
    groups = []
    for sid in all_source_ids:
        items = grouped.get(sid, [])
        kw_matched = [i for i in items if i.get("matched_kws")]
        groups.append({
            "source_id": sid,
            "label": label_map.get(sid, sid),
            "items": items,
            "kw_matched": len(kw_matched),
            "health": source_health.get(sid, {}),
        })

    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    last_run = recent_runs[0] if recent_runs else None

    html = _render(
        groups=groups,
        top_keywords=top_keywords,
        errored=errored,
        total_items=len(all_items),
        generated_at=generated_at,
        last_run=last_run,
        keywords=config.get("keywords", []),
        category_counts=category_counts,
    )

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Generated {OUTPUT}  ({len(all_items)} items, {len(groups)} sources)")


def _render(groups, top_keywords, errored, total_items, generated_at, last_run, keywords, category_counts=None):
    groups_html = ""
    for g in groups:
        if not g["items"]:
            continue
        h = g["health"]
        dot_class = h.get("status", "unknown") if h else "unknown"
        kw_badge = f'<span class="badge-kw">{g["kw_matched"]} matched</span>' if g["kw_matched"] else ""
        rows = "".join(_item_row(i) for i in g["items"])
        groups_html += f"""
        <div class="group" id="grp-{g['source_id']}">
          <div class="group-header" onclick="toggle('{g['source_id']}')">
            <span class="dot {dot_class}" title="{h.get('message','') if h else ''}"></span>
            <span class="group-title">{_esc(g['label'])}</span>
            <span class="count">{len(g['items'])}</span>
            {kw_badge}
            <span class="chev" id="chev-{g['source_id']}">▼</span>
          </div>
          <div id="body-{g['source_id']}">{rows}</div>
        </div>"""

    error_html = ""
    if errored:
        rows_e = "".join(
            f'<li><strong>{_esc(e["label"])}</strong><br>'
            f'<span class="err-msg">{_esc(e["message"])}</span></li>'
            for e in errored
        )
        error_html = f"""
        <div class="error-panel">
          <h3>⚠ {len(errored)} source{'s' if len(errored)!=1 else ''} failed
            <span class="note">(other sources continued normally)</span></h3>
          <ul class="err-list">{rows_e}</ul>
        </div>"""

    kw_pills = "".join(
        f'<button class="kw-pill" onclick="filterKw(this)">{_esc(kw)} <span>{n}</span></button>'
        for kw, n in top_keywords
    )
    kw_cloud = f'<div class="kw-cloud">{kw_pills}</div>' if top_keywords else ""

    last_run_html = ""
    if last_run:
        ts = (last_run.get("started_at") or "")[:16].replace("T", " ")
        new = last_run.get("new_items", 0)
        errs = len(last_run.get("errors") or [])
        err_str = f' · <span style="color:var(--err)">{errs} err</span>' if errs else ""
        last_run_html = f'Last harvest: <strong>{ts} UTC</strong> · +{new} new{err_str}'

    kw_json = json.dumps([k.lower() for k in keywords])

    # Topic tabs
    CAT_COLOURS = {
        "energy": ("--cat-energy-bg", "--cat-energy-text"),
        "AI":     ("--cat-ai-bg",     "--cat-ai-text"),
        "health": ("--cat-health-bg", "--cat-health-text"),
        "tax":    ("--cat-tax-bg",    "--cat-tax-text"),
    }
    cat_tabs = '<button class="topic-tab active" data-cat="" onclick="filterCat(this)">All</button>'
    for cat, count in (category_counts or {}).items():
        cat_lower = cat.lower()
        cat_tabs += (
            f'<button class="topic-tab tab-{cat_lower}" data-cat="{cat_lower}" '
            f'onclick="filterCat(this)">{_esc(cat.capitalize())}'
            f'<span class="tab-count">{count}</span></button>'
        )
    tabs_html = f'<div class="topic-tabs">{cat_tabs}</div>'

    category_counts_json = json.dumps({k.lower(): v for k, v in (category_counts or {}).items()})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FC-Harvest — Parliamentary Monitor</title>
<style>
:root{{
  --bg:#f4f5f7;--surface:#fff;--border:#e1e4e8;--text:#1a1a2e;--muted:#6b7280;
  --accent:#1d4ed8;--accent-light:#eff6ff;--tag:#f0f1f3;
  --kw-bg:#dcfce7;--kw-text:#14532d;
  --ok:#16a34a;--warn:#d97706;--err:#dc2626;--err-bg:#fef2f2;--err-border:#fecaca;
  --cat-energy-bg:#fff7ed;--cat-energy-text:#c2410c;--cat-energy-border:#fed7aa;
  --cat-ai-bg:#eff6ff;--cat-ai-text:#1d4ed8;--cat-ai-border:#bfdbfe;
  --cat-health-bg:#fdf2f8;--cat-health-text:#9d174d;--cat-health-border:#fbcfe8;
  --cat-tax-bg:#f0fdf4;--cat-tax-text:#15803d;--cat-tax-border:#bbf7d0;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
      background:var(--bg);color:var(--text);font-size:14px;line-height:1.5}}
a{{color:var(--accent);text-decoration:none}}
a:hover{{text-decoration:underline}}

/* ── Header ── */
.header{{background:var(--surface);border-bottom:1px solid var(--border);
         padding:16px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;
         position:sticky;top:0;z-index:10}}
.header h1{{font-size:16px;font-weight:700;letter-spacing:-.3px}}
.header-meta{{font-size:12px;color:var(--muted)}}
.header-right{{margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.badge{{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500}}
.badge-ok{{background:#dcfce7;color:var(--ok)}}
.badge-err{{background:var(--err-bg);color:var(--err)}}

/* ── Toolbar ── */
.toolbar{{padding:14px 24px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
          border-bottom:1px solid var(--border);background:var(--surface)}}
.toolbar label{{font-size:12px;display:flex;align-items:center;gap:5px;cursor:pointer}}
input[type=checkbox]{{accent-color:var(--accent);cursor:pointer}}
.search-box{{padding:5px 10px;border:1px solid var(--border);border-radius:6px;
             font-size:13px;outline:none;width:220px}}
.search-box:focus{{border-color:var(--accent)}}
.btn-sm{{padding:5px 12px;border-radius:6px;font-size:12px;font-weight:500;
          cursor:pointer;border:1px solid var(--border);background:var(--tag);color:var(--text)}}
.btn-sm:hover{{background:var(--border)}}

/* ── Layout ── */
.content{{padding:20px 24px;max-width:1100px;margin:0 auto}}

/* ── Error panel ── */
.error-panel{{background:var(--err-bg);border:1px solid var(--err-border);
              border-radius:8px;padding:14px 16px;margin-bottom:18px}}
.error-panel h3{{font-size:13px;font-weight:600;color:var(--err);margin-bottom:8px}}
.error-panel .note{{font-size:11px;font-weight:400;color:var(--muted)}}
.err-list{{list-style:none;font-size:12px}}
.err-list li{{padding:5px 0;border-bottom:1px solid var(--err-border)}}
.err-list li:last-child{{border:none}}
.err-msg{{color:var(--muted)}}

/* ── Keyword cloud ── */
.kw-cloud{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px}}
.kw-pill{{font-size:11px;padding:3px 9px;border-radius:12px;background:var(--kw-bg);
           color:var(--kw-text);font-weight:500;cursor:pointer;border:none}}
.kw-pill span{{opacity:.6;margin-left:3px}}
.kw-pill.active{{outline:2px solid var(--ok)}}

/* ── Groups ── */
.group{{background:var(--surface);border:1px solid var(--border);
        border-radius:8px;margin-bottom:10px;overflow:hidden}}
.group-header{{display:flex;align-items:center;gap:8px;padding:10px 16px;
               background:var(--bg);border-bottom:1px solid var(--border);
               cursor:pointer;user-select:none}}
.group-title{{font-size:13px;font-weight:600;flex:1}}
.count{{font-size:11px;background:var(--tag);color:var(--muted);padding:1px 7px;border-radius:10px}}
.badge-kw{{font-size:11px;background:var(--kw-bg);color:var(--kw-text);
           padding:1px 7px;border-radius:10px;font-weight:500}}
.chev{{font-size:10px;color:var(--muted)}}
.dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.dot.ok{{background:var(--ok)}}.dot.error{{background:var(--err)}}
.dot.warning{{background:var(--warn)}}.dot.unknown{{background:var(--border)}}

/* ── Items ── */
.item{{padding:11px 16px;border-bottom:1px solid var(--border);transition:background .1s}}
.item:last-child{{border:none}}
.item:hover{{background:var(--accent-light)}}
.item-title{{font-size:13px;font-weight:500;line-height:1.4}}
.item-summary{{font-size:12px;color:var(--muted);margin-top:3px;
               overflow:hidden;display:-webkit-box;
               -webkit-line-clamp:2;-webkit-box-orient:vertical}}
.item-meta{{display:flex;gap:12px;margin-top:4px;font-size:11px;color:var(--muted)}}
.item-tags{{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}}
.tag{{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--tag);color:var(--muted)}}
.tag.kw{{background:var(--kw-bg);color:var(--kw-text);font-weight:500}}

/* ── Empty ── */
.empty{{padding:48px;text-align:center;color:var(--muted)}}

/* ── Topic tabs ── */
.topic-tabs{{display:flex;gap:0;overflow-x:auto;border-bottom:1px solid var(--border);
             background:var(--surface);padding:0 24px}}
.topic-tab{{padding:9px 16px;font-size:12px;font-weight:500;cursor:pointer;
            border:none;background:none;border-bottom:3px solid transparent;
            color:var(--muted);white-space:nowrap;display:inline-flex;align-items:center;gap:5px}}
.topic-tab:hover{{color:var(--text)}}
.topic-tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.topic-tab .tab-count{{font-size:10px;padding:1px 5px;border-radius:8px;background:var(--tag)}}
.topic-tab.active .tab-count{{background:var(--accent-light);color:var(--accent)}}
.topic-tab.tab-energy.active{{color:var(--cat-energy-text);border-bottom-color:var(--cat-energy-text)}}
.topic-tab.tab-energy.active .tab-count{{background:var(--cat-energy-bg);color:var(--cat-energy-text)}}
.topic-tab.tab-ai.active{{color:var(--cat-ai-text);border-bottom-color:var(--cat-ai-text)}}
.topic-tab.tab-ai.active .tab-count{{background:var(--cat-ai-bg);color:var(--cat-ai-text)}}
.topic-tab.tab-health.active{{color:var(--cat-health-text);border-bottom-color:var(--cat-health-text)}}
.topic-tab.tab-health.active .tab-count{{background:var(--cat-health-bg);color:var(--cat-health-text)}}
.topic-tab.tab-tax.active{{color:var(--cat-tax-text);border-bottom-color:var(--cat-tax-text)}}
.topic-tab.tab-tax.active .tab-count{{background:var(--cat-tax-bg);color:var(--cat-tax-text)}}

/* ── Category badges on items ── */
.cat-badge{{font-size:10px;font-weight:600;padding:1px 7px;border-radius:10px;border:1px solid;white-space:nowrap}}
.cat-energy{{background:var(--cat-energy-bg);color:var(--cat-energy-text);border-color:var(--cat-energy-border)}}
.cat-ai{{background:var(--cat-ai-bg);color:var(--cat-ai-text);border-color:var(--cat-ai-border)}}
.cat-health{{background:var(--cat-health-bg);color:var(--cat-health-text);border-color:var(--cat-health-border)}}
.cat-tax{{background:var(--cat-tax-bg);color:var(--cat-tax-text);border-color:var(--cat-tax-border)}}

/* ── Footer ── */
.footer{{padding:16px 24px;font-size:11px;color:var(--muted);
         border-top:1px solid var(--border);margin-top:32px}}

.hidden{{display:none!important}}
@media(max-width:600px){{.content{{padding:12px}}.toolbar{{flex-direction:column;align-items:start}}}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>FC-Harvest</h1>
    <div class="header-meta">UK Parliament &amp; Government Monitor</div>
  </div>
  <div class="header-right">
    <span class="header-meta">{_esc(last_run_html)}</span>
    <span class="badge badge-ok">{total_items} items</span>
    {'<span class="badge badge-err">'+str(len(errored))+' source'+('s' if len(errored)!=1 else '')+' failing</span>' if errored else ''}
  </div>
</div>

<div class="toolbar">
  <input class="search-box" type="search" id="search" placeholder="Search titles…" oninput="applyFilters()">
  <label><input type="checkbox" id="kw-only" onchange="applyFilters()"> Keyword matches only</label>
  <button class="btn-sm" onclick="expandAll()">Expand all</button>
  <button class="btn-sm" onclick="collapseAll()">Collapse all</button>
  <span style="font-size:12px;color:var(--muted);margin-left:auto">Generated {_esc(generated_at)}</span>
</div>

{tabs_html}

<div class="content">

  {error_html}
  {kw_cloud}

  <div id="groups-container">
    {groups_html if groups_html.strip() else '<div class="empty"><p>No items yet — run a harvest first.</p></div>'}
  </div>

</div>

<div class="footer">
  FC-Harvest · Generated {_esc(generated_at)} ·
  Sources: GOV.UK Search API, committees-api.parliament.uk, hansard-api.parliament.uk,
  questions-statements-api.parliament.uk, whatson-api.parliament.uk ·
  <a href="https://developer.parliament.uk/" target="_blank">developer.parliament.uk</a>
</div>

<script>
const KEYWORDS = {kw_json};
const CAT_COUNTS = {category_counts_json};

function toggle(id) {{
  const body = document.getElementById('body-' + id);
  const chev = document.getElementById('chev-' + id);
  const hidden = body.classList.toggle('hidden');
  chev.textContent = hidden ? '▶' : '▼';
}}

function expandAll()  {{ document.querySelectorAll('[id^="body-"]').forEach(el => {{ el.classList.remove('hidden'); }}); document.querySelectorAll('[id^="chev-"]').forEach(el => el.textContent='▼'); }}
function collapseAll() {{ document.querySelectorAll('[id^="body-"]').forEach(el => {{ el.classList.add('hidden'); }}); document.querySelectorAll('[id^="chev-"]').forEach(el => el.textContent='▶'); }}

let activeKw = null;
let activeCat = null;

function filterCat(btn) {{
  document.querySelectorAll('.topic-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  activeCat = btn.dataset.cat || null;
  applyFilters();
}}

function filterKw(btn) {{
  const kw = btn.textContent.replace(/\\d+$/,'').trim().toLowerCase();
  if (activeKw === kw) {{ activeKw = null; btn.classList.remove('active'); }}
  else {{
    document.querySelectorAll('.kw-pill').forEach(b => b.classList.remove('active'));
    activeKw = kw; btn.classList.add('active');
  }}
  applyFilters();
}}

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase();
  const kwOnly = document.getElementById('kw-only').checked;

  document.querySelectorAll('.item').forEach(item => {{
    const title = (item.querySelector('.item-title')?.textContent || '').toLowerCase();
    const tags = Array.from(item.querySelectorAll('.tag.kw')).map(t => t.textContent.toLowerCase());
    const cats = Array.from(item.querySelectorAll('.cat-badge')).map(b => b.dataset.cat || '');
    const hasKw = tags.length > 0;
    const matchesSearch = !q || title.includes(q);
    const matchesKwOnly = !kwOnly || hasKw;
    const matchesActiveKw = !activeKw || tags.some(t => t.includes(activeKw));
    const matchesCat = !activeCat || cats.includes(activeCat);
    item.classList.toggle('hidden', !matchesSearch || !matchesKwOnly || !matchesActiveKw || !matchesCat);
  }});

  document.querySelectorAll('.group').forEach(grp => {{
    const visible = grp.querySelectorAll('.item:not(.hidden)').length;
    grp.classList.toggle('hidden', visible === 0);
  }});
}}
</script>
</body>
</html>"""


def _item_row(item: dict) -> str:
    title = _esc(item.get("title", ""))
    url = item.get("url", "")
    title_html = f'<a href="{_esc(url)}" target="_blank" rel="noopener">{title}</a>' if url else title

    summary = _esc((item.get("summary") or "")[:300])
    summary_html = f'<div class="item-summary">{summary}</div>' if summary else ""

    date_str = (item.get("published_at") or "")[:10]

    cats = item.get("matched_categories") or []
    cat_badges = "".join(
        f'<span class="cat-badge cat-{c.lower()}" data-cat="{c.lower()}">{c.capitalize()}</span>'
        for c in cats
    )

    return f"""<div class="item">
      <div class="item-title">{title_html}</div>
      {summary_html}
      <div class="item-meta">
        <span>{_esc(date_str)}</span>
        {cat_badges}
      </div>
    </div>"""


def _esc(s) -> str:
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_label_map(config: dict) -> dict[str, str]:
    return {
        src["id"]: src.get("label", src["id"])
        for group in config.get("sources", {}).values()
        for src in group
    }


if __name__ == "__main__":
    generate()
