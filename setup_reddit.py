"""
One-time Reddit setup for job_finder.py.

Reddit only lets programs read posts through its official API, which needs a
free key tied to your Reddit account. This script saves that key in
config.json (next to this file) and checks that it works.

How to get the key (about 2 minutes):
  1. Sign in to Reddit, then open  https://www.reddit.com/prefs/apps
  2. Click "create another app..." at the bottom.
  3. Name: roblox-job-finder   Type: choose "script"
     Redirect uri: http://localhost:8080   (not used, but required)
  4. Click "create app". If Reddit asks you to accept its API terms or fill
     in a short request form first, do that and wait for approval.
  5. The "client ID" is the short code under the app name.
     The "secret" is shown next to "secret".
Then run:  python setup_reddit.py
"""

import getpass
import json
from pathlib import Path

import job_finder

CONFIG = Path(__file__).resolve().parent / "config.json"


def main():
    print(__doc__)
    cfg = {}
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cid = input("Paste the client ID: ").strip()
    secret = getpass.getpass("Paste the secret (it won't show as you paste): ").strip()
    cfg["reddit"] = {**cfg.get("reddit", {}), "client_id": cid, "client_secret": secret}
    print("Checking the key with Reddit ...")
    try:
        job_finder.reddit_token(cfg["reddit"])
    except Exception as e:
        print(f"That didn't work: {e}\nCheck you copied both values from the 'script' app and try again.")
        return
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("Connected. Saved to config.json - keep that file private. Now run:  python job_finder.py")


if __name__ == "__main__":
    main()
