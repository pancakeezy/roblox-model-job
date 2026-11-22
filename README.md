# Roblox Model Jobs

This program finds **paid Roblox jobs that want 3D models**, such as Blender meshes, props, maps, weapons, vehicles, characters and UGC accessories. It puts them all on one job board page.

## Use it on your computer

Double-click **`Find Roblox Jobs.bat`**. When it's done, `jobs.html` opens in your browser. On that page you can:
- search, e.g. `low poly`, `sword`, `usd`
- filter by the kind of work: props, weapons, vehicles, characters, UGC, maps
- sort by newest, by highest pay or by best match. Robux amounts also show a rough dollar value.
- ★ save jobs for later, or hide the ones you're not interested in
- see **NEW** jobs, which are ones found since your last visit

The same jobs are also saved to `jobs.csv`, which opens in Excel or Google Sheets.

From a terminal you can add options:

```
python job_finder.py --days 60            # look back 60 days instead of 30
python job_finder.py --include-unpaid     # also show volunteer / % posts (marked)
```

## Share it with friends (auto-updating website)

GitHub can run the search every 4 hours and put the page on a free website, so friends just open a link. It works even when your PC is off. Each friend's saved and hidden jobs are kept in their own browser.

1. Make a free account at https://github.com
2. Create a **new public repository** named `roblox-model-jobs`. Leave it empty: no README.
3. In that repository go to **Settings → Pages**, and under **Source** pick **GitHub Actions**.
4. Upload this folder to the repository. Claude can do this for you with `git push`.
5. Open the **Actions** tab and wait for "Update job board" to finish, about 2 minutes. Then your site is at
   `https://YOUR-USERNAME.github.io/roblox-model-jobs/`

To run it right away, go to **Actions → Update job board → Run workflow**.
The website is public: anyone with the link can see it. It only shows posts that are already public.

**Reddit on the website (optional):** in the repository go to **Settings → Secrets and variables → Actions** and add two secrets, `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.

## Where it looks

| Source | Notes |
|---|---|
| Roblox DevForum: Find & Hire Talent | The main source, with about 1–3 new hiring posts a day |
| Work With Indies | Game-studio jobs (3D/character/environment artist) that mention Roblox |
| Mastodon | Hiring posts under #robloxdev, #robloxstudio, #robloxugc and similar hashtags |
| BlenderArtists Paid Work, Polycount job boards | Only posts that mention Roblox |
| Reddit: r/robloxgamedev, r/RobloxDevelopers, r/ROBLOXStudio, r/RobloxUGC, plus Roblox posts on r/gameDevClassifieds, r/HungryArtists, r/forhire, r/3Dmodeling | Needs a free Reddit API key (below). Off until you add one. |

It automatically skips:
- closed or filled posts
- artists advertising themselves ("for hire", portfolios)
- volunteer, %-of-revenue and "passion project" posts
- jobs that aren't for modelers, such as scripter, UI, clothing or thumbnail jobs

## Not covered (and why)

- **Discord**: reading servers with a bot on your own account breaks Discord's rules and can get you banned. Check Roblox hiring servers yourself.
- **YouTube, X/Twitter, Bluesky**: they need paid or signed-in access, and YouTube isn't where jobs get posted.
- **Roblox Talent Hub**, **Fiverr**, **Upwork**: they need you to be signed in, or they don't allow programs to read them. Check them yourself.

## Reddit setup (optional)

1. Sign in at https://www.reddit.com/prefs/apps and click **create another app…**
2. Name it `roblox-job-finder`, choose **script**, and set the redirect URI to `http://localhost:8080`
3. If Reddit says you've reached the maximum number of apps, or asks for an access request, Reddit has to approve your account first.
4. Run `python setup_reddit.py` and paste the **client ID** and **secret**. They're saved in `config.json`, which is never uploaded.

## Staying safe

Ask for a deposit, or for pay after each finished model. Send previews or screenshots rather than the .blend until you've been paid. Never download "test files" or run programs that a client sends you.
