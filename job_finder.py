"""
Roblox 3D-modeling job finder.

Searches places where Roblox games hire modelers, keeps only paid, open posts
that want 3D models (Blender meshes, props, maps, UGC accessories, characters),
and writes:
    jobs.html  - open in your browser: search, filter, sort
    jobs.csv   - the same jobs as a spreadsheet

Run:            python job_finder.py
Options:
    --days N          only posts from the last N days (default 30)
    --no-open         don't open the report when finished

Sources: Roblox DevForum (Find & Hire Talent), Reddit (needs a free key, run
setup_reddit.py once), plus Roblox jobs posted on BlenderArtists and Polycount.
Standard library only - nothing to install.
"""

import argparse
import base64
import csv
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
SEEN_FILE = HERE / "seen.json"
TEMPLATE_FILE = HERE / "page_template.html"
UA = "windows:roblox-model-job-finder:v1.0 (personal job search script)"

# ------------------------------------------------------------------ rules --
# The post must ask for 3D modeling work.
MODEL_WORDS = [
    "blender", "3d", "3-d", "modeler", "modeller", "modeling", "modelling", "model",
    "models", "mesh", "meshes", "low poly", "low-poly", "lowpoly", "prop", "props",
    "asset", "assets", "ugc", "accessory", "accessories", "hard surface", "sculpt",
    "sculptor", "character artist", "environment artist", "3d artist", "texturing",
    "texture artist", "rigging", "rigger", "weapon models", "vehicle", "builder",
    "map builder", "map designer", "environment",
]
# Points for things that matter most to a Blender modeler.
BONUS = {
    "blender": 4, "modeler": 3, "modeller": 3, "3d modeler": 3, "3d artist": 3,
    "low poly": 2, "low-poly": 2, "lowpoly": 2, "mesh": 2, "props": 2, "prop": 2,
    "ugc": 2, "accessory": 1, "weapon": 1, "vehicle": 1, "stylized": 1,
    "commission": 2, "per model": 3, "per asset": 3, "per prop": 3, "usd": 2,
    "paypal": 2, "robux": 1, "r$": 1, "long term": 1, "long-term": 1,
    "beginner": 1, "simple": 1,
}
ROBLOX = re.compile(r"\broblox\b|\brobux\b|\bR\$|\bugc\b|\broblox studio\b|\bobby\b|\btycoon\b", re.I)
CLOSED = re.compile(r"\[\s*(closed|filled|done|hired|found)\b|^\s*closed|\(\s*closed|\bno longer hiring\b|\bposition filled\b", re.I)
FOR_HIRE = re.compile(r"\[\s*for\s*hire\s*\]|\bfor hire\b|\bcommissions? (are )?open\b|\bopen for commissions?\b"
                      r"|\blooking for (work|clients|commissions)\b|\bmy portfolio\b|\bhire me\b|\byrs of\b|\byears of experience\b(?=.*\bme\b)", re.I)
UNPAID = re.compile(r"\bunpaid\b|\bvolunteers?\b|\bvolunteer position\b|\[\s*%|%\s*\]|\bpercent(age)?\b|\brev(enue)?[\s-]*share\b"
                    r"|\bpassion project\b|\bno pay\b|\bfor free\b|\bpaid (later|after release)\b|\bdeferred\b|\bsponsor\b|\binvestors?\b", re.I)
HIRING = re.compile(r"\[\s*(hiring|paid|job|task|open|commission)[^\]]*\]|\bhiring\b|\bpaid\b|\blooking for\b|\blf\b|\bneeded\b"
                    r"|\bneed(ed)? (a|an|some)\b|\bseeking\b|\bwanted\b|\bcommission\b|\brecruit", re.I)
NOT_MODEL_ROLE = re.compile(r"\b(scripter|programmer|ui designer|ui/ux|gfx artist|thumbnail|voice actor|clothing designer"
                            r"|shirt|pants|sfx|music|composer|video editor|content creator|youtuber|clipper"
                            r"|animator|animation|video|voice ?over|playtest|tester|qa|backend|marketing|shopify)\b", re.I)
UNPAID_FLAG = "volunteer / % / unpaid"
PAY = re.compile(
    r"(?:(?:usd|us\$|\$|€|£|r\$|robux)\s?\d[\d,.]*\s*k?(?:\s*(?:-|–|to)\s*(?:\$|r\$)?\s?\d[\d,.]*\s*k?)?"
    r"(?:\s*(?:/|per|an?)\s*(?:hr|hour|model|asset|prop|item|map|day|week|month|project))?"
    r"|\d[\d,.]*\s*k?\s*(?:usd|eur|gbp|robux|r\$|dollars)(?:\s*(?:/|per|an?)\s*(?:hr|hour|model|asset|prop|item|map|day|week|month|project))?)",
    re.I,
)


# ----------------------------------------------------------------- helpers --
def log(msg):
    print(msg, flush=True)


def fetch(url, headers=None, data=None, tries=3):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=h, data=data)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                wait = int(e.headers.get("Retry-After") or 10 * (attempt + 1))
                log(f"    rate limited, waiting {wait}s ...")
                time.sleep(min(wait, 60))
                continue
            raise
        except urllib.error.URLError:
            if attempt < tries - 1:
                time.sleep(3)
                continue
            raise


def fetch_json(url, **kw):
    return json.loads(fetch(url, **kw))


def strip_html(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<img[^>]*>", " ", s, flags=re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def parse_time(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def make_job(source, title, url, posted, text, author="", tags=None, **extra):
    job = {"source": source, "title": strip_html(title), "url": url, "posted": posted,
           "text": strip_html(text)[:5000], "author": author or "", "tags": tags or []}
    job.update(extra)
    return job


def load_config():
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"Could not read config.json: {e}")
    # On the shared website the Reddit key comes from GitHub secrets instead of config.json.
    if os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"):
        cfg.setdefault("reddit", {}).update(client_id=os.environ["REDDIT_CLIENT_ID"],
                                            client_secret=os.environ["REDDIT_CLIENT_SECRET"])
    return cfg


# ----------------------------------------------------------------- sources --
def discourse_category(site, label, cat_path, cutoff, max_pages):
    """Latest topics in a Discourse category, back to the cutoff date."""
    jobs = []
    for page in range(max_pages):
        data = fetch_json(f"{site}/c/{cat_path}/l/latest.json?page={page}")
        topics = data.get("topic_list", {}).get("topics", [])
        if not topics:
            break
        for t in topics:
            if t.get("pinned") or t.get("pinned_globally"):
                continue
            tags = [x if isinstance(x, str) else x.get("name", "") for x in t.get("tags") or []]
            jobs.append(make_job(label, t.get("title", ""), f"{site}/t/{t.get('slug')}/{t['id']}",
                                 parse_time(t.get("created_at")), t.get("excerpt", ""), tags=tags,
                                 _id=t["id"], _site=site, _need_body=True))
        # Topics are ordered by last bump; stop once a whole page is older than the cutoff.
        last = [parse_time(t.get("bumped_at") or t.get("last_posted_at")) for t in topics]
        if all(d and d < cutoff for d in last):
            break
        time.sleep(0.6)
    return jobs


def fill_discourse_body(job):
    try:
        d = fetch_json(f"{job['_site']}/t/{job['_id']}.json")
        post = d["post_stream"]["posts"][0]
        job["text"] = strip_html(post.get("cooked", ""))[:5000]
        job["author"] = post.get("username", "")
    except Exception:
        pass


def src_devforum(cutoff, args):
    return discourse_category("https://devforum.roblox.com", "Roblox DevForum",
                              "collaboration/recruitment/82", cutoff, 25)


def src_blenderartists(cutoff, args):
    jobs = discourse_category("https://blenderartists.org", "BlenderArtists",
                              "jobs/paid-work/53", cutoff, 3)
    for j in jobs:
        j["_need_roblox"] = True
    return jobs


def src_polycount(cutoff, args):
    jobs = []
    for cat in (82, 45):
        for d in fetch_json(f"https://polycount.com/api/v2/discussions?categoryID={cat}&limit=100&sort=-dateInserted"):
            jobs.append(make_job("Polycount", d.get("name", ""), d.get("url", ""),
                                 parse_time(d.get("dateInserted")), d.get("body", ""),
                                 author=(d.get("insertUser") or {}).get("name", ""), _need_roblox=True))
        time.sleep(0.6)
    return jobs


# Subreddits; True = every post there is Roblox-related, False = must mention Roblox.
REDDIT_SUBS = {
    "robloxgamedev": True, "RobloxDevelopers": True, "ROBLOXStudio": True, "RobloxUGC": True,
    "gameDevClassifieds": False, "HungryArtists": False, "forhire": False, "3Dmodeling": False,
}
REDDIT_SEARCHES = ["roblox modeler", "roblox 3d model hiring", "roblox blender commission", "roblox ugc hiring"]


def reddit_token(cfg):
    cid, secret = cfg.get("client_id", "").strip(), cfg.get("client_secret", "").strip()
    if not cid or not secret:
        raise RuntimeError("skipped: run  python setup_reddit.py  once to connect your Reddit key")
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    body = json.loads(fetch("https://www.reddit.com/api/v1/access_token",
                            headers={"Authorization": f"Basic {auth}",
                                     "Content-Type": "application/x-www-form-urlencoded"},
                            data=b"grant_type=client_credentials"))
    if "access_token" not in body:
        raise RuntimeError(f"Reddit refused the key: {body}")
    return body["access_token"]


def reddit_posts(data, label, need_roblox):
    out = []
    for c in data.get("data", {}).get("children", []):
        p = c.get("data", {})
        flair = p.get("link_flair_text") or ""
        out.append(make_job(label, (f"[{flair}] " if flair else "") + p.get("title", ""),
                            "https://www.reddit.com" + p.get("permalink", ""),
                            parse_time(p.get("created_utc")), p.get("selftext", ""),
                            author=p.get("author", ""), tags=[flair] if flair else [],
                            _need_roblox=need_roblox, _reddit=True))
    return out


def src_reddit(cutoff, args):
    cfg = load_config().get("reddit", {})
    hdr = {"Authorization": f"bearer {reddit_token(cfg)}"}
    jobs = []
    for sub, roblox_only in (cfg.get("subreddits") or REDDIT_SUBS).items():
        try:
            data = fetch_json(f"https://oauth.reddit.com/r/{sub}/new?limit=100&raw_json=1", headers=hdr)
            jobs += reddit_posts(data, f"Reddit r/{sub}", not roblox_only)
        except Exception as e:
            log(f"    r/{sub}: {e}")
        time.sleep(1.1)
    for q in REDDIT_SEARCHES:
        try:
            qs = urllib.parse.urlencode({"q": q, "sort": "new", "t": "month", "limit": 100, "raw_json": 1})
            jobs += reddit_posts(fetch_json(f"https://oauth.reddit.com/search?{qs}", headers=hdr),
                                 "Reddit search", True)
        except Exception as e:
            log(f"    search '{q}': {e}")
        time.sleep(1.1)
    return jobs


def src_workwithindies(cutoff, args):
    """Game-studio jobs board. Only art/3D roles whose full post mentions Roblox."""
    page = fetch("https://www.workwithindies.com/", headers={"Accept": "text/html"})
    jobs = []
    for path in dict.fromkeys(re.findall(r'href="(/careers/[^"#?]+)"', page)):
        slug = path.rsplit("/", 1)[-1].replace("-", " ")
        if not words_in(slug, ["3d", "artist", "modeler", "modeller", "environment artist", "character artist",
                               "prop", "technical artist", "builder", "level designer"]):
            continue
        if words_in(slug, ["2d", "concept", "pixel", "animator", "illustrator", "marketing", "producer",
                           "head of", "creators", "background artist", "lighting artist", "ui"]):
            continue
        try:
            p = fetch("https://www.workwithindies.com" + path, headers={"Accept": "text/html"})
            ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', p, re.S).group(1),
                            strict=False)
        except Exception:
            continue
        org = (ld.get("hiringOrganization") or {}).get("name", "")
        salary = ""
        bs = (ld.get("baseSalary") or {}).get("value") or {}
        if isinstance(bs, dict) and (bs.get("minValue") or bs.get("value")):
            salary = f"\nSalary: ${bs.get('minValue') or bs.get('value'):,}" + (f"-${bs['maxValue']:,}" if bs.get("maxValue") else "")
        jobs.append(make_job("Work With Indies", f"{html.unescape(ld.get('title', ''))} @ {org}",
                             "https://www.workwithindies.com" + path, parse_time(ld.get("datePosted")),
                             html.unescape(ld.get("description", "")) + salary, author=org, _need_roblox=True,
                             _studio=True))
        time.sleep(0.5)
    return jobs


MASTODON_TAGS = ["robloxdev", "robloxdevelopment", "robloxdeveloper", "robloxstudio", "robloxugc"]


def src_mastodon(cutoff, args):
    jobs, seen = [], set()
    for tag in MASTODON_TAGS:
        try:
            posts = fetch_json(f"https://mastodon.social/api/v1/timelines/tag/{tag}?limit=40")
        except Exception:
            continue
        for p in posts:
            if p.get("id") in seen or p.get("reblog"):
                continue
            seen.add(p.get("id"))
            text = strip_html(p.get("content", ""))
            acct = (p.get("account") or {}).get("acct", "")
            jobs.append(make_job("Mastodon", text.split("\n")[0][:140], p.get("url") or p.get("uri", ""),
                                 parse_time(p.get("created_at")), text, author=acct, _social=True))
        time.sleep(0.6)
    return jobs


# Rough exchange rates, only for the "about $" estimate and pay sorting.
ROUGH_USD = {"USD": 1, "EUR": 1.08, "GBP": 1.27, "AUD": 0.65, "CAD": 0.72, "NZD": 0.6, "SGD": 0.74,
             "INR": 0.012, "PHP": 0.017, "HKD": 0.13, "JPY": 0.0066, "SEK": 0.095, "PLN": 0.25}
FREELANCER_QUERIES = ["roblox", "roblox 3d model", "roblox ugc", "roblox blender", "roblox map"]


def src_freelancer(cutoff, args):
    """Freelancer.com public project search (no account needed to search)."""
    jobs, seen = [], set()
    for q in FREELANCER_QUERIES:
        qs = urllib.parse.urlencode({"query": q, "limit": 100, "full_description": "true",
                                     "job_details": "true", "sort_field": "time_updated"})
        try:
            data = fetch_json(f"https://www.freelancer.com/api/projects/0.1/projects/active/?{qs}")
        except Exception as e:
            log(f"    '{q}': {e}")
            continue
        for p in (data.get("result") or {}).get("projects", []):
            if p.get("id") in seen:
                continue
            seen.add(p.get("id"))
            b = p.get("budget") or {}
            cur = (p.get("currency") or {}).get("code", "")
            lo, hi = b.get("minimum"), b.get("maximum")
            hourly = p.get("type") == "hourly"
            pay = ""
            if lo:
                pay = f"{lo:,.0f}" + (f"–{hi:,.0f}" if hi and hi != lo else "") + f" {cur}" + ("/hr" if hourly else " budget")
            skills = [j.get("name", "") for j in p.get("jobs") or []]
            title = re.sub(r"\s*--\s*\d+$", "", p.get("title", ""))
            job = make_job("Freelancer.com", title, f"https://www.freelancer.com/projects/{p.get('seo_url', p.get('id'))}",
                           parse_time(p.get("time_submitted")),
                           (p.get("description") or p.get("preview_description") or "") + (f"\n\nBudget: {pay}" if pay else ""),
                           tags=skills, _need_roblox=True, _strict_roblox=True)
            job["_pay"] = pay
            jobs.append(job)
        time.sleep(1)
    return jobs


X_QUERY = ('(roblox OR robux OR "roblox studio") '
           '(modeler OR modeller OR "3d model" OR "3d models" OR blender OR "low poly" OR ugc OR "3d artist" OR mesh) '
           '(hiring OR "looking for" OR commission OR paid OR "need a") -is:retweet')
X_CACHE = HERE / "x_cache.json"


def src_x(cutoff, args):
    """X (Twitter) via the official API. Needs a paid X API bearer token in X_BEARER_TOKEN.
    To keep API costs down it only searches every X_EVERY_HOURS hours (default 6) and reuses
    the last results in between."""
    token = os.environ.get("X_BEARER_TOKEN") or load_config().get("x", {}).get("bearer_token", "")
    if not token:
        raise RuntimeError("skipped: needs an X API key (see README)")
    every = int(os.environ.get("X_EVERY_HOURS", "6"))
    cache = {}
    if X_CACHE.exists():
        try:
            cache = json.loads(X_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    last = parse_time(cache.get("fetched"))
    if last and datetime.now(timezone.utc) - last < timedelta(hours=every) - timedelta(minutes=10):
        posts = cache.get("posts", [])
    else:
        qs = urllib.parse.urlencode({"query": X_QUERY, "max_results": 100, "tweet.fields": "created_at,author_id",
                                     "expansions": "author_id", "user.fields": "username"})
        data = fetch_json(f"https://api.x.com/2/tweets/search/recent?{qs}",
                          headers={"Authorization": f"Bearer {token}"})
        users = {u["id"]: u.get("username", "") for u in (data.get("includes") or {}).get("users", [])}
        posts = [{"id": t["id"], "text": t.get("text", ""), "created_at": t.get("created_at"),
                  "user": users.get(t.get("author_id"), "")} for t in data.get("data", [])]
        # Keep older cached posts too (recent search only looks back 7 days).
        old = {p["id"]: p for p in cache.get("posts", [])}
        old.update({p["id"]: p for p in posts})
        posts = list(old.values())
        X_CACHE.write_text(json.dumps({"fetched": datetime.now(timezone.utc).isoformat(), "posts": posts}),
                           encoding="utf-8")
    jobs = []
    for p in posts:
        user = p.get("user") or "i"
        jobs.append(make_job("X (Twitter)", p["text"].split("\n")[0][:140],
                             f"https://x.com/{user}/status/{p['id']}", parse_time(p.get("created_at")),
                             p["text"], author="@" + user if p.get("user") else "", _social=True))
    return jobs


SOURCES = [
    ("Roblox DevForum (Find & Hire Talent)", src_devforum),
    ("Freelancer.com (Roblox projects)", src_freelancer),
    ("Reddit", src_reddit),
    ("X (Twitter)", src_x),
    ("Work With Indies (Roblox studios)", src_workwithindies),
    ("Mastodon (#robloxdev and similar)", src_mastodon),
    ("BlenderArtists paid work (Roblox only)", src_blenderartists),
    ("Polycount job boards (Roblox only)", src_polycount),
]

# Kinds of modeling work, used for the filter buttons on the page.
CATEGORIES = [
    ("UGC & accessories", ["ugc", "accessory", "accessories", "hat", "hats", "hair", "limited", "limiteds"]),
    ("Characters & creatures", ["character", "characters", "creature", "creatures", "monster", "npc", "rig",
                                "rigging", "avatar", "pet", "pets", "animal"]),
    ("Weapons & tools", ["weapon", "weapons", "gun", "guns", "sword", "swords", "tool", "tools", "knife"]),
    ("Vehicles", ["vehicle", "vehicles", "car", "cars", "truck", "plane", "boat", "ship", "train", "tank"]),
    ("Props & assets", ["prop", "props", "asset", "assets", "furniture", "item", "items", "low poly",
                        "low-poly", "lowpoly", "decoration", "foliage"]),
    ("Maps & environments", ["map", "maps", "environment", "environments", "builder", "building", "lobby",
                             "level", "terrain", "world", "facility", "city"]),
]
DEVEX_USD_PER_ROBUX = 0.0038  # Roblox Developer Exchange rate, used only for a rough "about $" estimate


def categorize(job):
    text = f"{job['title']} {' '.join(job['tags'])} {job['text'][:2000]}"
    cats = [name for name, words in CATEGORIES if words_in(text, words)]
    return cats or ["General 3D"]


CURRENCY_ALIASES = {"$": "USD", "us$": "USD", "usd": "USD", "dollars": "USD", "dollar": "USD",
                    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "£": "GBP", "gbp": "GBP",
                    "₹": "INR", "r$": "ROBUX", "robux": "ROBUX"}
_CUR = "|".join(sorted({re.escape(c) for c in list(CURRENCY_ALIASES) + [c.lower() for c in ROUGH_USD]},
                       key=len, reverse=True))
_NUM = r"(\d[\d,]*(?:\.\d+)?)\s*(k\b)?"
MONEY = re.compile(rf"(?:({_CUR})\s?)?{_NUM}(?:\s*(?:-|–|to)\s*(?:{_CUR})?\s?{_NUM})?\s*(?:({_CUR})(?![a-z]))?", re.I)


def pay_to_usd(pay_text):
    """Convert every amount in a pay text to rough US dollars.
    Returns (low, high, was_converted). Robux uses Roblox's DevEx rate."""
    lo = hi = None
    converted = False
    for m in MONEY.finditer(pay_text or ""):
        code = (m.group(1) or m.group(6) or "").lower()
        code = CURRENCY_ALIASES.get(code, code.upper())
        if not code:
            continue
        rate = DEVEX_USD_PER_ROBUX if code == "ROBUX" else ROUGH_USD.get(code)
        if not rate:
            continue
        try:
            a = float(m.group(2).replace(",", "")) * (1000 if m.group(3) else 1)
            b = float(m.group(4).replace(",", "")) * (1000 if m.group(5) else 1) if m.group(4) else a
        except ValueError:
            continue
        a, b = a * rate, b * rate
        lo = a if lo is None else min(lo, a)
        hi = b if hi is None else max(hi, b)
        converted |= code != "USD"
    return lo, hi, converted


def usd_label(lo, hi):
    def f(x):
        return "<$1" if x < 1 else f"${x:,.0f}"
    if lo is None:
        return ""
    return "≈ " + (f(lo) if round(lo) == round(hi) else f"{f(lo)}–{f(hi)[1:] if hi >= 1 else f(hi)}") + " USD"


# --------------------------------------------------------------- filtering --
def words_in(text, words):
    t = text.lower()
    return [w for w in words if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t)]


def classify(job, include_unpaid):
    """Return (keep, score, pay, flags)."""
    title, body = job["title"], job["text"]
    tags = " ".join(job["tags"])
    full = f"{title}\n{body}\n{tags}"

    if CLOSED.search(title) or CLOSED.search(tags):
        return False, 0, "", []
    if job.get("_need_roblox") and not ROBLOX.search(full):
        return False, 0, "", []
    if job.get("_strict_roblox") and not re.search(r"\broblox\b", title + "\n" + body, re.I):
        return False, 0, "", []  # e.g. "UGC" marketing videos on general freelance sites
    model_hits = words_in(f"{title}\n{tags}\n{body[:1500]}", MODEL_WORDS)
    if not model_hits:
        return False, 0, "", []
    # A scripter/UI post that only says "model" in passing isn't a modeling job.
    title_model = words_in(title + " " + tags, MODEL_WORDS)
    if NOT_MODEL_ROLE.search(title) and not title_model:
        return False, 0, "", []

    flags = []
    hiring_signal = HIRING.search(title + " " + tags)
    for_hire = bool(FOR_HIRE.search(title)) or ((job.get("_reddit") or job.get("_social")) and not hiring_signal)
    if for_hire and not re.search(r"hiring", title + " " + tags, re.I):
        return False, 0, "", []  # an artist advertising themselves, not a job
    pays = list(dict.fromkeys(p.strip() for p in PAY.findall(full) if re.search(r"\d", p)))
    unpaid = bool(UNPAID.search(title)) or (bool(UNPAID.search(body)) and not pays)
    if unpaid:
        if not include_unpaid:
            return False, 0, "", []
        flags.append(UNPAID_FLAG)
    if not words_in(title + " " + tags, ["modeler", "modeller", "modeling", "modelling", "3d", "blender",
                                          "mesh", "props", "ugc", "low poly", "model", "models"]):
        if words_in(full, ["builder", "map builder"]):
            flags.append("builder role - check if meshes are wanted")

    score = len(set(model_hits))
    for w, pts in BONUS.items():
        if words_in(full, [w]):
            score += pts
    if pays:
        score += 4
    if title_model:
        score += 4
    return True, score, ", ".join(pays)[:140], flags


# ------------------------------------------------------------------ output --
def write_csv(jobs, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Posted", "Source", "Title", "Kind of work", "Pay mentioned", "About USD", "Notes",
                    "Posted by", "Link", "Description"])
        for j in jobs:
            w.writerow([j["posted"].strftime("%Y-%m-%d"), j["source"], j["title"], "; ".join(j["cats"]),
                        j["pay"], j["usd_text"] or (f"${j['usd']:,.0f}" if j["usd"] else ""), "; ".join(j["flags"]), j["author"], j["url"], j["text"][:1500]])


def write_html(jobs, path, errors, days, schedule_minutes=None):
    rows = [{"id": j["url"], "t": j["title"], "u": j["url"],
             "s": "Reddit" if j["source"].startswith("Reddit") else j["source"], "ss": j["source"],
             "a": j["author"], "d": j["posted"].isoformat(), "fs": j["first_seen"], "p": j["pay"],
             "usd": j["usd"], "c": j["cats"], "x": j["text"][:3500], "sc": j["score"], "f": j["flags"],
             "studio": bool(j.get("_studio")), "up": UNPAID_FLAG in j["flags"], "uc": j["usd_text"]} for j in jobs]
    meta = {"generated": datetime.now(timezone.utc).isoformat(), "days": days,
            "errors": errors, "sources": [label for label, _ in SOURCES], "schedule_minutes": schedule_minutes}
    page = (TEMPLATE_FILE.read_text(encoding="utf-8")
            .replace("__DATA__", json.dumps(rows).replace("</", "<\\/"))
            .replace("__META__", json.dumps(meta).replace("</", "<\\/")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


# -------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser(description="Find paid Roblox 3D modeling jobs.")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--out", help="where to write the page (default jobs.html next to this script)")
    ap.add_argument("--schedule-minutes", type=lambda v: sorted(int(x) for x in v.split(",")), default=None,
                    help="minutes past each hour the website rebuilds, e.g. 0,30 (shows a next-update countdown)")
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    raw, errors = [], {}
    for label, fn in SOURCES:
        log(f"Searching {label} ...")
        try:
            got = fn(cutoff, args)
            log(f"    {len(got)} posts")
            raw.extend(got)
        except Exception as e:
            log(f"    {e}")
            errors[label] = str(e)

    # First pass on title/excerpt (generous), then read full posts, then decide.
    candidates, urls = [], set()
    for j in raw:
        if j["url"] in urls or not j["posted"] or j["posted"] < cutoff:
            continue
        urls.add(j["url"])
        if classify(j, True)[0] or (j.get("_need_body") and not CLOSED.search(j["title"])
                                    and words_in(j["title"] + " " + " ".join(j["tags"]) + " " + j["text"], MODEL_WORDS)):
            candidates.append(j)

    need = [j for j in candidates if j.get("_need_body")]
    if need:
        log(f"Reading {len(need)} forum posts in full ...")
        for i, j in enumerate(need, 1):
            fill_discourse_body(j)
            time.sleep(0.4)
            if i % 25 == 0:
                log(f"    {i}/{len(need)}")

    jobs = []
    for j in candidates:
        keep, score, pay, flags = classify(j, True)  # unpaid posts are kept but marked; the page hides them
        pay = j.get("_pay") or pay
        if keep:
            j.update(score=score, pay=pay, flags=flags)
            jobs.append(j)

    # Remember when each job was first found, so the page can mark new ones.
    seen = {}
    if SEEN_FILE.exists():
        try:
            old = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            seen = old if isinstance(old, dict) else {u: "2000-01-01T00:00:00+00:00" for u in old}
        except Exception:
            pass
    now = datetime.now(timezone.utc).isoformat()
    for j in jobs:
        j["first_seen"] = seen.setdefault(j["url"], now)
        j["cats"] = categorize(j)
        lo, hi, converted = pay_to_usd(j["pay"])
        j["usd"] = round(hi, 2) if hi else 0
        unit = re.search(r"/\s*h(?:ou)?r\b|per hour|hourly|(?:per|/|an?)\s*(?:model|asset|prop|item)", j["pay"], re.I)
        unit = ("/hr" if "h" in unit.group(0).lower()[:3] or "hour" in unit.group(0).lower()
                else " per " + re.sub(r".*(model|asset|prop|item).*", r"\1", unit.group(0).lower())) if unit else ""
        j["usd_text"] = usd_label(lo, hi) + unit if converted else ""
    SEEN_FILE.write_text(json.dumps(seen), encoding="utf-8")

    jobs.sort(key=lambda j: j["posted"], reverse=True)
    out = Path(args.out).resolve() if args.out else HERE / "jobs.html"
    write_html(jobs, out, errors, args.days, args.schedule_minutes)
    write_csv(jobs, out.with_suffix(".csv"))
    new = sum(j["first_seen"] == now for j in jobs)
    log(f"\nFound {len(jobs)} Roblox modeling jobs ({new} new since the last run).")
    log(f"Report: {out}")
    if not args.no_open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    sys.exit(main())
