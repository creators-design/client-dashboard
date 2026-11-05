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
# Everyone who has spoken on the WGS stage, with the news topics that should
# trigger a post. Pulled from the WGS YouTube archive (4,500 sessions).
# Add a name here and the radar picks it up the next morning.
SPEAKERS = {
    # --- the big draws ---
    "Elon Musk": ["Elon Musk", "Tesla robot", "SpaceX Starship", "Neuralink", "Optimus robot", "xAI Grok"],
    "Shah Rukh Khan": ["Shah Rukh Khan", "Bollywood box office"],
    "Jensen Huang": ["Jensen Huang", "Nvidia earnings", "AI chip export"],
    "Sam Altman": ["Sam Altman", "OpenAI", "ChatGPT update"],
    "Sundar Pichai": ["Sundar Pichai", "Google AI", "Gemini AI"],
    "Neil deGrasse Tyson": ["Neil deGrasse Tyson", "NASA Artemis", "Mars mission", "asteroid Earth"],
    "Michio Kaku": ["Michio Kaku", "quantum computing breakthrough", "fusion energy breakthrough"],
    "Simon Sinek": ["Simon Sinek", "leadership burnout", "return to office mandate"],
    "Malcolm Gladwell": ["Malcolm Gladwell", "robotaxi crash", "self driving recall"],
    "Steve Wozniak": ["Steve Wozniak", "Apple launch", "Apple earnings"],
    "Larry Ellison": ["Larry Ellison", "Oracle AI", "sovereign AI"],
    "Yann LeCun": ["Yann LeCun", "Meta AI", "open source AI model"],
    "Tucker Carlson & Ray Dalio": ["Ray Dalio", "US debt crisis"],
    "Deepinder Goyal": ["Deepinder Goyal", "Zomato", "Eternal Ltd", "quick commerce India"],
    "Noland Arbaugh (Neuralink)": ["Neuralink patient", "brain computer interface"],
    "Dr. Sanjay Gupta": ["Sanjay Gupta CNN", "Alzheimer research", "dementia study"],
    "Harrison Ford": ["Harrison Ford", "climate actor campaign"],
    "Goldie Hawn": ["children mental health study", "student wellbeing school"],

    # --- heads of state & government ---
    "David Beasley (WFP)": ["World Food Programme", "global hunger crisis", "famine declaration"],
    "Paul Kagame": ["Paul Kagame", "Rwanda development"],
    "Muhammad Yunus": ["Muhammad Yunus", "Bangladesh government", "microfinance"],
    "Tshering Tobgay": ["Bhutan", "Gross National Happiness"],
    "Alexander Stubb": ["Alexander Stubb", "Finland president"],
    "Louise Araneta-Marcos": ["Philippines first lady", "Philippines government"],
    "Najla Bouden Romdhane": ["Tunisia government"],
    "Tony Blair": ["Tony Blair Institute", "government technology policy"],

    # --- economy & institutions ---
    "Christine Lagarde": ["Christine Lagarde", "European Central Bank", "ECB rate decision"],
    "Sri Mulyani Indrawati": ["Sri Mulyani", "Indonesia economy"],
    "Klaus Schwab": ["Klaus Schwab", "World Economic Forum Davos"],
    "Jeffrey Sachs": ["Jeffrey Sachs", "sustainable development goals"],
    "John Cryan": ["Deutsche Bank", "European banking"],
    "Amina J. Mohammed (UN)": ["Amina Mohammed UN", "United Nations deputy secretary"],

    # --- UAE leadership & officials ---
    "Yousef Al Otaiba": ["Yousef Al Otaiba", "UAE United States relations"],
    "Reem Al Hashimy": ["Reem Al Hashimy", "UAE international cooperation"],
    "Sultan Al Jaber": ["Sultan Al Jaber", "ADNOC", "COP climate UAE"],
    "Omar Al Olama": ["Omar Al Olama", "UAE artificial intelligence minister"],
    "Abdulla Lootah": ["UAE competitiveness", "UAE government performance"],

    # --- science, health & tech ---
    "J. Craig Venter": ["genome editing approval", "longevity research", "CRISPR trial"],
    "Robynne Chutkan": ["gut microbiome study", "gut health research"],
    "Eleni Linos": ["public health research", "digital health study"],
    "Roman Yampolskiy": ["AI safety researcher", "AI existential risk"],
    "Robin Li (Baidu)": ["Robin Li Baidu", "Baidu AI", "China AI model"],
    "K. Radhakrishnan (ISRO)": ["ISRO mission", "India space programme", "Chandrayaan", "Gaganyaan"],
    "Sonja Lyubomirsky / Paul Dolan": ["happiness research study", "wellbeing index"],
    "James Doty": ["compassion neuroscience", "mindfulness research"],
    "Dino Varkey (GEMS)": ["GEMS Education", "private schooling India"],
    "Princess Ameerah Al-Taweel": ["Saudi women leadership", "Saudi Vision 2030"],
}

# Topics WGS covers that are not tied to one speaker.
TOPICS = [
    "World Governments Summit", "UAE government policy", "Dubai future project",
    "India AI policy", "India startup funding", "future of work automation",
    "universal basic income", "humanoid robot launch", "climate summit",
    "space tourism", "gene therapy approval", "longevity drug",
    "central bank digital currency", "smart city Dubai", "AI regulation",
    "government AI adoption", "digital government service",
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
HOURS_BACK = 24          # nothing older than this is ever shown
MAX_PER_QUERY = 8
MAX_ITEMS = 120
EMAIL_ITEMS = 30         # how many make it into the digest you receive
MIN_ITEMS = 10           # if fewer than this are fresh, widen the window once


def fetch(query, tries=3):
    url = GOOGLE_NEWS.format(q=urllib.parse.quote(f'"{query}" when:1d' if " " in query else f"{query} when:1d"))
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
    # recency is the dominant signal - a 2-hour-old story beats a 20-hour-old one
    age_h = (now - published).total_seconds() / 3600 if published else 99
    if age_h <= 3:
        s += 10
    elif age_h <= 6:
        s += 8
    elif age_h <= 9:
        s += 6
    elif age_h <= 12:
        s += 4
    elif age_h <= 18:
        s += 2
    return s, age_h


def fresh_label(age_h):
    if age_h <= 3:
        return "JUST BROKE"
    if age_h <= 6:
        return "THIS MORNING"
    if age_h <= 12:
        return "TODAY"
    if age_h <= 24:
        return "YESTERDAY"
    return "OLDER"


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

    window = HOURS_BACK
    feeds = {}
    for speaker, query in jobs:
        root = feeds.get(query)
        if root is None:
            root = fetch(query)
            feeds[query] = root
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
            if published and (now - published).total_seconds() / 3600 > window:
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
                "fresh": fresh_label(age_h),
            })
        time.sleep(0.6)   # be polite to Google

    if len(items) < MIN_ITEMS:
        print(f"Only {len(items)} stories inside {HOURS_BACK}h - widening to 48h once")
        window = 48
        for speaker, query in jobs:
            root = feeds.get(query)
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
                if published and (now - published).total_seconds() / 3600 > window:
                    continue
                key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
                if link in seen_links or key in seen_titles:
                    continue
                seen_links.add(link)
                seen_titles.add(key)
                sc, age_h = score(title, published, now)
                items.append({"speaker": speaker, "trigger": query,
                              "title": re.sub(r"\s+-\s+[^-]+$", "", title).strip(),
                              "source": (source or "").strip(), "link": link,
                              "hours_old": round(age_h, 1), "score": sc,
                              "angle": angle(speaker, title), "fresh": fresh_label(age_h)})

    items.sort(key=lambda x: (-x["score"], x["hours_old"]))
    items = items[:MAX_ITEMS]
    top = items[:EMAIL_ITEMS]

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
  <div style="font:400 13px Arial,sans-serif;color:#9ab8ae;margin-top:4px">{out['generated_ist']} &nbsp;·&nbsp; {len(items)} stories found &nbsp;·&nbsp; {len(top)} below</div>
</td></tr>
{''.join(rows) if rows else '<tr><td style="padding:26px;font:400 14px Arial,sans-serif;color:#5e6a75">Nothing matched in the last 48 hours. The radar runs again tomorrow morning.</td></tr>'}
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
    bands = [("JUST BROKE - last 3 hours", "Newest stories on the wire. First mover advantage is here.", lambda it: it["hours_old"] <= 3),
             ("THIS MORNING - 3 to 6 hours", "Still early. Post today and you are ahead of most pages.", lambda it: 3 < it["hours_old"] <= 6),
             ("TODAY - 6 to 12 hours", "Live today. Worth building something around.", lambda it: 6 < it["hours_old"] <= 12),
             ("LAST 24 HOURS", "Still current, but moving fast. Check it has not peaked.", lambda it: 12 < it["hours_old"] <= 24),
             ("OLDER THAN A DAY", "Only shown because today was quiet. Treat as background.", lambda it: it["hours_old"] > 24)]
    newest = min((i["hours_old"] for i in items), default=None)
    md = [f"**{out['generated_ist']}** — {len(items)} stories found, {len(top)} below."
          + (f" Newest is {newest}h old." if newest is not None else ""),
          "", "_Sorted newest first. Anything under 6 hours is where you want to be._", ""]
    if not top:
        md.append("_Nothing matched in the last 48 hours. The radar runs again tomorrow morning._")
    n = 0
    for name, blurb, test in bands:
        group = [i for i in top if test(i)]
        if not group:
            continue
        md += [f"## {name} ({len(group)})", f"_{blurb}_", ""]
        for it in group:
            n += 1
            md += [
                f"**{n}. {it['title']}**",
                f"**{it['speaker']}** · {it['hours_old']}h ago · {it['source'] or 'source unknown'}",
                "",
                f"> {it['angle']}",
                "",
                f"[Read the story]({it['link']})",
                "",
            ]
        md.append("---")
        md.append("")
    md.append(f"Full list of {len(items)} on the [News radar tab](https://creators-design.github.io/client-dashboard/#news).")
    with open("news.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("Wrote news.md")


if __name__ == "__main__":
    main()
