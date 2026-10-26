"""
Pulls the latest Instagram + YouTube numbers from Windsor.ai and writes data.json,
which index.html reads. Run daily by .github/workflows/daily-update.yml.
Needs one secret: WINDSOR_API_KEY (from https://onboard.windsor.ai -> API key).
"""
import datetime, json, os, sys, time, urllib.parse, urllib.request

API_KEY = os.environ.get("WINDSOR_API_KEY")
if not API_KEY:
    sys.exit("WINDSOR_API_KEY is not set. Add it under Settings > Secrets and variables > Actions.")

BASE = "https://connectors.windsor.ai/"

# Accounts shown on the dashboard. Add a new client here (Instagram username / YouTube channel name).
IG_USERS = {"sandeepdasauthor", "drtarangkrishna", "ajithkarimpana"}
YT_FULL_CHANNELS = {"Sandeep Das", "Dr Tarang Krishna"}   # every content type
YT_SHORTS_ONLY = {"CoinDCX"}                               # YouTube Shorts only
YT_ALL = YT_FULL_CHANNELS | YT_SHORTS_ONLY


def get(connector, fields, preset, tries=4):
    query = urllib.parse.urlencode({"api_key": API_KEY, "date_preset": preset, "fields": ",".join(fields)})
    url = BASE + connector + "?" + query
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=600) as resp:
                body = json.load(resp)
            rows = body.get("data", body) if isinstance(body, dict) else body
            if not isinstance(rows, list):
                raise ValueError("unexpected response: " + json.dumps(body)[:300])
            print(f"  {connector} {preset}: {len(rows)} rows")
            return rows
        except Exception as e:  # network hiccup or Windsor still preparing the report
            print(f"  {connector} {preset} attempt {attempt} failed: {e}")
            if attempt == tries:
                raise
            time.sleep(30 * attempt)


def num(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def latest_by(rows, key):
    out = {}
    for r in rows:
        out[r.get(key)] = r
    return list(out.values())


def trim_videos(rows, keep_top=15, recent_days=35):
    cutoff = (datetime.date.today() - datetime.timedelta(days=recent_days)).isoformat()
    by = {}
    for r in rows:
        by.setdefault(r["channel_title"], []).append(r)
    out = []
    for vids in by.values():
        top = {v["video"] for v in sorted(vids, key=lambda x: -(num(x.get("views")) or 0))[:keep_top]}
        out += [v for v in vids if v["video"] in top or str(v.get("published_at", ""))[:10] >= cutoff]
    return out


def main():
    print("Instagram profiles")
    ig_profile = [r for r in latest_by(get("instagram", ["username", "followers_count", "media_count"], "last_7d"), "username")
                  if r.get("username") in IG_USERS]

    print("YouTube channels")
    yt_profile = [r for r in latest_by(get("youtube", ["channel_title", "subscriber_count", "view_count", "video_count"], "last_7d"), "channel_title")
                  if r.get("channel_title") in YT_ALL]

    print("Instagram daily")
    ig_daily = [r for r in get("instagram", ["date", "username", "follower_count_1d", "reach_1d", "views", "total_interactions"], "last_30d")
                if r.get("username") in IG_USERS]

    print("YouTube daily by content type")
    raw = get("youtube", ["date", "channel_title", "creator_content_type", "views", "likes", "comments", "shares",
                          "estimated_minutes_watched", "subscribers_gained", "subscribers_lost"], "last_30d")
    agg, yt_daily = {}, []
    for r in raw:
        ch = r.get("channel_title")
        if ch in YT_SHORTS_ONLY and r.get("creator_content_type") == "shorts":
            yt_daily.append(r)
        elif ch in YT_FULL_CHANNELS:
            k = (ch, str(r["date"])[:10])
            o = agg.setdefault(k, {"date": k[1], "channel_title": ch, "views": 0, "likes": 0, "comments": 0, "shares": 0,
                                   "estimated_minutes_watched": 0})
            for f in ("views", "likes", "comments", "shares", "estimated_minutes_watched"):
                o[f] += num(r.get(f)) or 0
    yt_daily += list(agg.values())

    print("YouTube daily subscribers")
    yt_subs = [r for r in get("youtube", ["date", "channel_title", "subscribers_gained_channel", "subscribers_lost_channel"], "last_30d")
               if r.get("channel_title") in YT_FULL_CHANNELS]

    print("Instagram posts")
    ig_media = []
    for m in get("instagram", ["username", "media_id", "media_caption", "timestamp", "media_type", "media_reach", "media_views",
                               "media_like_count", "media_comments_count", "media_saved", "media_shares", "media_follows",
                               "media_engagement", "media_permalink"], "last_30d"):
        if m.get("username") not in IG_USERS:
            continue
        m["media_caption"] = (m.get("media_caption") or "").split("\n")[0].strip()[:140]
        ig_media.append(m)

    yt_videos, cdx = {}, {}
    for preset in ("last_7d", "last_14d", "last_30d"):
        print("YouTube videos", preset)
        rows = get("youtube", ["channel_title", "video", "video_title", "published_at", "creator_content_type", "views", "likes",
                               "comments", "shares", "subscribers_gained", "average_view_duration", "average_view_percentage"], preset)
        yt_videos[preset] = trim_videos([r for r in rows if r.get("channel_title") in YT_FULL_CHANNELS])
        cdx[preset] = trim_videos([r for r in rows if r.get("channel_title") in YT_SHORTS_ONLY and r.get("creator_content_type") == "shorts"])

    data = {
        "asOf": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
        "ig_profile": ig_profile, "yt_profile": yt_profile, "ig_daily": ig_daily, "yt_daily": yt_daily,
        "yt_subs_daily": yt_subs, "ig_media": ig_media, "yt_videos": yt_videos, "cdx": cdx,
    }
    if not ig_profile or not yt_profile:
        sys.exit("No profile rows came back — check the API key and that the accounts are still connected in Windsor.ai. data.json was left unchanged.")
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Wrote data.json")


if __name__ == "__main__":
    main()
