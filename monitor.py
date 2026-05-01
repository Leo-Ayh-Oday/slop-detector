"""Browser Monitor -- check replies across platforms.

Usage:
    python monitor.py                    # check all platforms
    python monitor.py --login            # first time: open browser, log in manually
    python monitor.py --platform juejin  # check one platform
"""

import json
import sys
from pathlib import Path
from datetime import datetime

COOKIES_DIR = Path(__file__).parent / ".browser_cookies"
COOKIES_DIR.mkdir(exist_ok=True)

PLATFORMS = {
    "juejin": {
        "name": "Juejin",
        "url": "https://juejin.cn/notifications",
        "login_url": "https://juejin.cn/login",
        "check_selector": ".notification-item",
    },
    "zhihu": {
        "name": "Zhihu",
        "url": "https://www.zhihu.com/notifications",
        "login_url": "https://www.zhihu.com/signin",
        "check_selector": ".NotificationItem",
    },
    "reddit": {
        "name": "Reddit",
        "url": "https://www.reddit.com/notifications",
        "login_url": "https://www.reddit.com/login",
        "check_selector": "shreddit-notification",
    },
}


def login_platform(platform_key: str):
    """Open browser for manual login, save cookies."""
    from playwright.sync_api import sync_playwright

    info = PLATFORMS[platform_key]
    cookie_file = COOKIES_DIR / f"{platform_key}.json"

    print(f"\n{'='*50}")
    print(f"Login to {info['name']}")
    print(f"Log in manually in the browser, then press Enter...")
    print(f"{'='*50}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(info["login_url"])
        input(f"\nPress Enter after logging in to save cookies...")
        cookies = context.cookies()
        cookie_file.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        print(f"Cookies saved to {cookie_file}")
        browser.close()


def check_platform(platform_key: str) -> dict:
    """Check notifications on one platform."""
    from playwright.sync_api import sync_playwright

    info = PLATFORMS[platform_key]
    cookie_file = COOKIES_DIR / f"{platform_key}.json"

    if not cookie_file.exists():
        return {"platform": info["name"], "status": "not logged in", "items": []}

    cookies = json.loads(cookie_file.read_text(encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()

        try:
            page.goto(info["url"], timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            items = page.query_selector_all(info["check_selector"])
            results = []
            for item in items[:20]:
                text = item.inner_text().strip()[:200]
                if text:
                    results.append(text)
            browser.close()
            return {
                "platform": info["name"],
                "status": "OK",
                "count": len(results),
                "items": results,
            }
        except Exception as e:
            browser.close()
            return {"platform": info["name"], "status": f"error: {e}", "items": []}


def check_github_repo(repo_name: str) -> dict:
    """Check GitHub repo stats via public API."""
    import requests
    results = {}
    try:
        r = requests.get(
            f"https://api.github.com/repos/Leo-Ayh-Oday/{repo_name}",
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            results = {
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "updated": data.get("updated_at", ""),
            }
    except Exception:
        pass
    return results


def main():
    if "--login" in sys.argv:
        platform = "juejin"
        for i, arg in enumerate(sys.argv):
            if arg == "--platform" and i + 1 < len(sys.argv):
                platform = sys.argv[i + 1]
        login_platform(platform)
        return

    specific = None
    for i, arg in enumerate(sys.argv):
        if arg == "--platform" and i + 1 < len(sys.argv):
            specific = sys.argv[i + 1]

    print(f"\n{'='*50}")
    print(f"Project Monitor -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    # GitHub repos (public, no auth needed)
    print("\n-- GitHub Repos --")
    for repo in ["slop-detector", "supply-chain-calc"]:
        stats = check_github_repo(repo)
        if stats:
            print(f"  {repo}: Stars={stats['stars']} Forks={stats['forks']} Issues={stats['open_issues']}")
        else:
            print(f"  {repo}: query failed")

    # Browser-based platforms (need login cookies)
    platforms_to_check = [specific] if specific else list(PLATFORMS.keys())
    for pk in platforms_to_check:
        print(f"\n-- {PLATFORMS[pk]['name']} --")
        cookie_file = COOKIES_DIR / f"{pk}.json"
        if not cookie_file.exists():
            print(f"  Not logged in. Run: python monitor.py --login --platform {pk}")
            continue
        result = check_platform(pk)
        print(f"  Status: {result['status']}")
        if result["items"]:
            print(f"  Notifications: {result['count']}")
            for item in result["items"][:5]:
                print(f"    - {item[:100]}")
        else:
            print(f"  No new notifications")

    print(f"\n{'='*50}")
    print("Tip: python monitor.py --login (first-time login)")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
