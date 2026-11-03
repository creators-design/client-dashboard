"""
WGS news radar.

Every morning this looks for news that connects to someone who has spoken on the
World Governments Summit stage, scores how post-worthy each story is, and writes:

  news.json  - read by the "News radar" tab on the dashboard
  news.html  - the email body that gets sent to you

It uses Google News RSS, which needs no API key and no account.

Run by .github/workflows/news-radar.yml every morning at 06:30 IST.
"""

import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- watchlist
# Each speaker maps to the news topics that should trigger a post.
# Add a speaker here and the radar picks them up the next morning.
SPEAKERS = {
    "Elon Musk": ["Elon Musk", "Tesla robot", "SpaceX Starship", "Neuralink", "Optimus robot", "Boring Company tunnel"],
    "Neil deGrasse Tyson": ["Neil deGrasse Tyson", "NASA Artemis", "Mars mission", "asteroid Earth", "space telescope discovery"],
    "Simon Sinek": ["Simon Sinek", "leadership burnout", "return to office mandate", "employee engagement survey"],
    "Michio Kaku": ["Michio Kaku", "quantum computing breakthrough", "fusion energy breakthrough", "brain implant"],
    "Jensen Huang": ["Jensen Huang", "Nvidia earnings", "AI chip export", "GPU demand"],
    "Sam Altman": ["Sam Altman", "OpenAI", "ChatGPT update", "AGI"],
    "Sundar Pichai": ["Sundar Pichai", "Google AI", "Gemini AI", "Alphabet earnings"],
    "Yann LeCun": ["Yann LeCun", "Meta AI", "open source AI model"],
    "Larry Ellison": ["Larry Ellison", "Oracle AI", "sovereign AI", "government cloud contract"],
    "Shah Rukh Khan": ["Shah Rukh Khan", "Bollywood box office"],
    "Deepinder Goyal": ["Deepinder Goyal", "Zomato", "Eternal Ltd", "quick commerce India", "food delivery India"],
    "Noland Arbaugh (Neuralink)": ["Neuralink patient", "brain computer interface", "paralysis treatment breakthrough"],
    "Dr. Sanjay Gupta": ["Sanjay Gupta CNN", "Alzheimer research", "dementia study", "brain health study"],
    "Steve Wozniak": ["Steve Wozniak", "Apple launch", "Apple earnings"],
    "Malcolm Gladwell": ["Malcolm Gladwell", "robotaxi crash", "self driving car recall", "diabetes epidemic"],
    "J. Craig Venter": ["genome editing approval", "longevity research", "CRISPR trial"],
    "Ray Dalio": ["Ray Dalio", "US debt crisis", "sovereign debt"],
    "Tony Blair": ["Tony Blair Institute", "government technology policy"],
    "Paul Kagame": ["Paul Kagame", "Rwanda development"],
    "Muhammad Yunus": ["Muhammad Yunus", "Bangladesh interim government", "microfinance"],
    "Goldie Hawn": ["children mental health study", "student wellbeing school"],
}

# Topics WGS covers that aren't tied to one speaker.
TOPICS = [
    "World Governments Summit", "UAE government policy", "Dubai future project",
    "India AI policy", "India startup funding", "future of work automation",
    "universal basic income", "humanoid robot launch", "climate summit",
    "space tourism", "gene therapy approval", "longevity drug",
    "central bank digital currency", "smart city Dubai", "AI regulation",
]

# Words that mean a story is worth posting about today.
HOT = {
    r"\bbreaking\b": 3, r"\bannounce": 2, r"\blaunch": 2, r"\bunveil": 2,
    r"\bfirst\b": 2, r"\brecord\b": 2, r"\bbreakthrough\b": 3, r"\bban\b": 2,
    r"\bwarn": 2, r"\bpredict": 3, r"\bapproved?\b": 2, r"\bresign": 2,
    r"\bdies?\b|\bdeath\b": 2, r"\bsurge": 2, r"\bcrash": 2, r"\bsues?\b|lawsuit": 1,
    r"\bmillion\b|\bbillion\b|\btrillion\b": 1, r"\bstudy\b|\bresearch\b": 1,
    r"\bIndia\b": 2, r"\bUAE\b|\bDubai\b|\bAbu Dhabi\b": 3,
}

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
UA = {"User-Agent": "Mozilla/5.0 (compatible; WGS-news-radar/1.0)"}
HOURS_BACK = 36          # only stories newer than this
MAX_PER_QUERY = 6
MAX_ITEMS = 40


def fetch(query, tries=3):
    url = GOOGLE_NEWS.format(q=urllib.parse.quote(f'"{query}" when:2d' if " " in query else f"{query} when:2d"))
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return ET.fromstring(r.read())
        except Exception as exc:
            if attempt == tries:
                print(f"  ! {query}: {exc}")
                return None
            time.sleep(3 * attempt)


def parse_date(text):
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            d = dt.datetime.strptime(text, fmt)
            return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d
        except Exception:
            pass
    return None


def score(title, published, now):
    s = 0
    for pattern, weight in HOT.items():
        if re.search(pattern, title, re.I):
            s += weight
    age_h = (now - published).total_seconds() / 3600 if published else 48
    if age_h <= 6:
        s += 4
    elif age_h <= 12:
        s += 3
    elif age_h <= 24:
        s += 2
    return s, age_h


def angle(speaker, title):
    """What to actually make from this story."""
    if speaker == "WGS topic":
        return "Archive clip on this theme + a text-led reel stating the prediction and today's news."
    return (f"Pull the {speaker} clip from the archive. Hook: \u201cIn [year], {speaker} said this on our stage.\u201d "
            f"Then one line of today's news. Post as a Reel and a Short the same day.")


def main():
    now = dt.datetime.now(dt.timezone.utc)
    seen_links, seen_titles, items = set(), set(), []

    jobs = [(sp, q) for sp, qs in SPEAKERS.items() for q in qs] + [("WGS topic", t) for t in TOPICS]
    print(f"Checking {len(jobs)} queries...")

    for speaker, query in jobs:
        root = fetch(query)
        if root is None:
            continue
        for node in list(root.iter("item"))[:MAX_PER_QUERY]:
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            src_el = node.find("source")
            source = (src_el.text if src_el is not None and src_el.text else "")
            published = parse_date((node.findtext("pubDate") or "").strip())
            if not title or not link:
                continue
            if published and (now - published).total_seconds() / 3600 > HOURS_BACK:
                continue
            key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
            if link in seen_links or key in seen_titles:
                continue
            seen_links.add(link)
            seen_titles.add(key)
            sc, age_h = score(title, published, now)
            items.append({
                "speaker": speaker,
                "trigger": query,
                "title": re.sub(r"\s+-\s+[^-]+$", "", title).strip(),
                "source": (source or "").strip(),
                "link": link,
                "hours_old": round(age_h, 1),
                "score": sc,
                "angle": angle(speaker, title),
            })
        time.sleep(0.6)   # be polite to Google

    items.sort(key=lambda x: (-x["score"], x["hours_old"]))
    items = items[:MAX_ITEMS]
    top = items[:8]

    out = {
        "generated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "generated_ist": (now + dt.timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %H:%M IST"),
        "count": len(items),
        "items": items,
    }
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote news.json with {len(items)} stories")

    # ----- email body -----
    e = html.escape
    rows = []
    for i, it in enumerate(top, 1):
        rows.append(f"""
        <tr><td style="padding:16px 18px;border-bottom:1px solid #e6eaef">
          <div style="font:600 12px/1.4 Arial,sans-serif;color:#0e7c66;text-transform:uppercase;letter-spacing:.06em">
            {i}. {e(it['speaker'])} &nbsp;·&nbsp; {it['hours_old']}h ago &nbsp;·&nbsp; score {it['score']}
          </div>
          <div style="font:700 16px/1.45 Arial,sans-serif;color:#14181d;margin:6px 0 4px">{e(it['title'])}</div>
          <div style="font:400 13px/1.5 Arial,sans-serif;color:#5e6a75;margin-bottom:8px">{e(it['source'])}</div>
          <div style="font:400 13px/1.55 Arial,sans-serif;color:#14181d;background:#f3f7f6;border-left:3px solid #0e7c66;padding:9px 12px;border-radius:4px">
            <b>What to make:</b> {e(it['angle'])}
          </div>
          <div style="margin-top:10px"><a href="{e(it['link'])}" style="font:600 13px Arial,sans-serif;color:#0e7c66">Read the story &rarr;</a></div>
        </td></tr>""")

    body = f"""<!DOCTYPE html><html><body style="margin:0;background:#f5f7f8;padding:22px 12px">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:660px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e6eaef">
<tr><td style="background:#14302b;padding:22px 20px">
  <div style="font:700 19px Arial,sans-serif;color:#fff">WGS news radar</div>
  <div style="font:400 13px Arial,sans-serif;color:#9ab8ae;margin-top:4px">{out['generated_ist']} &nbsp;·&nbsp; {len(items)} stories matched to people who have spoken on the stage</div>
</td></tr>
{''.join(rows) if rows else '<tr><td style="padding:26px;font:400 14px Arial,sans-serif;color:#5e6a75">Nothing strong enough matched in the last 36 hours. The radar runs again tomorrow morning.</td></tr>'}
<tr><td style="padding:16px 18px;background:#f8fafb">
  <div style="font:400 12px/1.6 Arial,sans-serif;color:#5e6a75">
    Scored on recency and on words that signal a post-worthy story. Anything scoring 6 or more is usually worth acting on the same day.<br>
    Full list of {len(items)} on the dashboard: <a href="https://creators-design.github.io/client-dashboard/#news" style="color:#0e7c66">News radar tab</a>
  </div>
</td></tr></table></body></html>"""

    with open("news.html", "w", encoding="utf-8") as f:
        f.write(body)
    print("Wrote news.html")

    # ----- markdown version (used when the digest is delivered as a GitHub issue) -----
    md = [f"**{out['generated_ist']}** — {len(items)} stories matched to people who have spoken on the stage.", ""]
    if not top:
        md.append("_Nothing strong enough matched in the last 36 hours. The radar runs again tomorrow morning._")
    for i, it in enumerate(top, 1):
        label = "POST NOW" if it["score"] >= 8 else "ACT TODAY" if it["score"] >= 6 else "WATCH"
        md += [
            f"### {i}. {it['title']}",
            f"`{label}` · **{it['speaker']}** · {it['hours_old']}h ago · {it['source'] or 'source unknown'} · score {it['score']}",
            "",
            f"> **What to make:** {it['angle']}",
            "",
            f"[Read the story]({it['link']})",
            "",
            "---",
            "",
        ]
    md.append(f"Full list of {len(items)} on the [News radar tab](https://creators-design.github.io/client-dashboard/#news).")
    with open("news.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("Wrote news.md")


if __name__ == "__main__":
    main()
