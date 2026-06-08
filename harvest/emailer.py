"""
Email digest sender.

Sends an HTML email summarising new keyword-matched items from the latest harvest.
Items are grouped by topic category (energy / AI / health / tax), with any
uncategorised keyword matches listed at the bottom.

Configuration (config.yaml):
  email:
    enabled: true
    to: "jack@founderscomms.co"
    from: "FC-Harvest <noreply@founderscomms.co>"
    subject: "FC-Harvest digest — {date}"
    only_if_matches: true   # skip send when nothing matched keywords

SMTP credentials (environment variables — never put passwords in config):
  SMTP_HOST      e.g. smtp.gmail.com
  SMTP_PORT      e.g. 587  (default: 587)
  SMTP_USER      e.g. you@gmail.com
  SMTP_PASSWORD  app password / API key
  SMTP_TLS       "true" (default) or "false"
"""

import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .filters import categories_for_item

logger = logging.getLogger(__name__)

# Topic display order and colour palette
CATEGORY_STYLES: dict[str, dict] = {
    "energy": {"label": "Energy",  "bg": "#fff7ed", "text": "#c2410c", "border": "#fed7aa"},
    "AI":     {"label": "AI",      "bg": "#eff6ff", "text": "#1d4ed8", "border": "#bfdbfe"},
    "health": {"label": "Health",  "bg": "#fdf2f8", "text": "#9d174d", "border": "#fbcfe8"},
    "tax":    {"label": "Tax",     "bg": "#f0fdf4", "text": "#15803d", "border": "#bbf7d0"},
}


def send_digest(new_items: list[dict], config: dict, label_map: dict[str, str]) -> bool:
    """
    Format and send the digest email.

    new_items  — items returned as new by this harvest run (already have matched_kws set)
    config     — full loaded config dict
    label_map  — {source_id: human label}

    Returns True if email was sent, False if skipped or disabled.
    Raises on SMTP errors so the caller can log them.
    """
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled", False):
        logger.debug("Email digest disabled in config.")
        return False

    keyword_categories: dict[str, list[str]] = config.get("keyword_categories", {})

    # Enrich items with categories
    matched_items = []
    for item in new_items:
        kws = item.get("matched_kws") or []
        if kws:
            item = dict(item)
            item["matched_categories"] = categories_for_item(kws, keyword_categories)
            matched_items.append(item)

    only_if_matches = email_cfg.get("only_if_matches", True)
    if only_if_matches and not matched_items:
        logger.info("No keyword-matched new items — skipping digest email.")
        return False

    to_addr = email_cfg.get("to", "")
    from_addr = email_cfg.get("from", "FC-Harvest <noreply@example.com>")
    date_str = datetime.now(timezone.utc).strftime("%A %-d %B %Y")
    subject = email_cfg.get("subject", "FC-Harvest digest — {date}").format(date=date_str)

    html_body = _build_html(matched_items, new_items, keyword_categories, label_map, date_str)
    text_body = _build_text(matched_items, new_items, label_map, date_str)

    _send(from_addr, to_addr, subject, html_body, text_body)
    logger.info("Digest email sent to %s (%d matched items)", to_addr, len(matched_items))
    return True


def _send(from_addr: str, to_addr: str, subject: str, html: str, text: str):
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    use_tls = os.environ.get("SMTP_TLS", "true").lower() != "false"

    if not host:
        raise RuntimeError(
            "SMTP_HOST environment variable is not set. "
            "Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD to enable email."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as smtp:
        if use_tls:
            smtp.starttls(context=context)
        if user and password:
            smtp.login(user, password)
        smtp.sendmail(from_addr, to_addr, msg.as_string())


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(
    matched_items: list[dict],
    all_new_items: list[dict],
    keyword_categories: dict[str, list[str]],
    label_map: dict[str, str],
    date_str: str,
) -> str:
    # Group matched items by category (an item can appear in multiple categories)
    by_cat: dict[str, list[dict]] = {cat: [] for cat in keyword_categories}
    uncategorised: list[dict] = []

    for item in matched_items:
        cats = item.get("matched_categories") or []
        if cats:
            for cat in cats:
                if cat in by_cat:
                    by_cat[cat].append(item)
        else:
            uncategorised.append(item)

    sections_html = ""
    for cat, items in by_cat.items():
        if not items:
            continue
        style = CATEGORY_STYLES.get(cat, {"label": cat.capitalize(), "bg": "#f0f1f3", "text": "#374151", "border": "#e5e7eb"})
        rows = "".join(_item_row_html(i, label_map) for i in items)
        sections_html += f"""
        <div style="margin-bottom:28px">
          <div style="display:inline-block;background:{style['bg']};color:{style['text']};
                      border:1px solid {style['border']};border-radius:12px;
                      font-size:11px;font-weight:700;padding:3px 10px;
                      letter-spacing:.04em;text-transform:uppercase;margin-bottom:10px">
            {_esc(style['label'])}
          </div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
            {rows}
          </table>
        </div>"""

    if uncategorised:
        rows = "".join(_item_row_html(i, label_map) for i in uncategorised)
        sections_html += f"""
        <div style="margin-bottom:28px">
          <div style="display:inline-block;background:#f0f1f3;color:#374151;
                      border:1px solid #e5e7eb;border-radius:12px;
                      font-size:11px;font-weight:700;padding:3px 10px;
                      letter-spacing:.04em;text-transform:uppercase;margin-bottom:10px">
            Other matches
          </div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
            {rows}
          </table>
        </div>"""

    total_new = len(all_new_items)
    total_matched = len(matched_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 0">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%">

        <!-- Header -->
        <tr><td style="background:#1a1a2e;border-radius:8px 8px 0 0;padding:20px 28px">
          <span style="color:#fff;font-size:16px;font-weight:700;letter-spacing:-.3px">FC-Harvest</span>
          <span style="color:#6b7280;font-size:13px;margin-left:10px">UK Parliament &amp; Government Monitor</span>
        </td></tr>

        <!-- Date bar -->
        <tr><td style="background:#1d4ed8;padding:10px 28px">
          <span style="color:#fff;font-size:13px;font-weight:500">{_esc(date_str)}</span>
          <span style="color:#93c5fd;font-size:12px;margin-left:12px">
            {total_matched} relevant item{"s" if total_matched != 1 else ""} &nbsp;·&nbsp;
            {total_new} total new
          </span>
        </td></tr>

        <!-- Body -->
        <tr><td style="background:#fff;padding:24px 28px;border-radius:0 0 8px 8px">
          {sections_html if sections_html else
           '<p style="color:#6b7280;font-size:13px">No keyword-matched items in this harvest.</p>'}
        </td></tr>

        <!-- Footer -->
        <tr><td style="padding:16px 28px">
          <p style="color:#9ca3af;font-size:11px;margin:0">
            FC-Harvest &nbsp;·&nbsp; Sources: GOV.UK, Parliament APIs, Hansard &nbsp;·&nbsp;
            Edit keywords and sources in <code>config.yaml</code>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _item_row_html(item: dict, label_map: dict[str, str]) -> str:
    title = _esc(item.get("title", ""))
    url = item.get("url", "")
    source_label = _esc(label_map.get(item.get("source_id", ""), item.get("source_id", "")))
    date_str = (item.get("published_at") or "")[:10]
    summary = _esc((item.get("summary") or "")[:220])

    title_html = (
        f'<a href="{_esc(url)}" style="color:#1d4ed8;text-decoration:none;font-weight:600;font-size:13px">{title}</a>'
        if url else
        f'<span style="font-weight:600;font-size:13px">{title}</span>'
    )
    summary_html = (
        f'<div style="color:#6b7280;font-size:12px;margin-top:3px;line-height:1.5">{summary}…</div>'
        if summary else ""
    )

    return f"""<tr>
      <td style="padding:10px 0;border-bottom:1px solid #f0f1f3;vertical-align:top">
        {title_html}
        {summary_html}
        <div style="margin-top:4px;font-size:11px;color:#9ca3af">
          {date_str} &nbsp;·&nbsp; {source_label}
        </div>
      </td>
    </tr>"""


# ── Plain-text builder ────────────────────────────────────────────────────────

def _build_text(
    matched_items: list[dict],
    all_new_items: list[dict],
    label_map: dict[str, str],
    date_str: str,
) -> str:
    lines = [
        "FC-Harvest — UK Parliament & Government Monitor",
        f"{date_str}",
        f"{len(matched_items)} relevant items · {len(all_new_items)} total new",
        "=" * 60,
        "",
    ]

    # Group by category (show each item once under its first category)
    seen_ids: set = set()
    by_cat: dict[str, list[dict]] = {}
    for item in matched_items:
        for cat in (item.get("matched_categories") or ["other"]):
            by_cat.setdefault(cat, []).append(item)

    for cat, items in by_cat.items():
        lines.append(f"── {cat.upper()} ──")
        lines.append("")
        for item in items:
            iid = item.get("item_id", item.get("url", ""))
            if iid in seen_ids:
                continue
            seen_ids.add(iid)
            title = item.get("title", "")
            url = item.get("url", "")
            source = label_map.get(item.get("source_id", ""), "")
            date = (item.get("published_at") or "")[:10]
            summary = (item.get("summary") or "")[:200]
            lines.append(f"  {title}")
            if url:
                lines.append(f"  {url}")
            lines.append(f"  {date}  {source}")
            if summary:
                lines.append(f"  {summary}…")
            lines.append("")
        lines.append("")

    lines += [
        "-" * 60,
        "Edit keywords and sources: config.yaml",
    ]
    return "\n".join(lines)


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
