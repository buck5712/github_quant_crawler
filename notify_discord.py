"""
讀取 crawler.py 產出的 data/weekly_pushed_<date>.json,
組成 Discord 訊息(前 5 名 star 數的 repo 用 embed 顯示,完整清單用附件 .md 檔),
推播到 DISCORD_WEBHOOK_URL 指定的 webhook。
"""

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

TOP_N = 5


def latest_weekly_files():
    json_files = sorted(DATA_DIR.glob("weekly_pushed_*.json"))
    if not json_files:
        return None, None, None
    latest_json = json_files[-1]
    date_str = latest_json.stem.replace("weekly_pushed_", "")
    md_path = DATA_DIR / f"weekly_pushed_{date_str}.md"
    return latest_json, md_path if md_path.exists() else None, date_str


def build_embed(repo: dict) -> dict:
    return {
        "title": repo["full_name"],
        "url": repo["html_url"],
        "description": (repo.get("description") or "(無描述)")[:300],
        "fields": [
            {"name": "⭐ Stars", "value": str(repo["stars"]), "inline": True},
            {"name": "🍴 Forks", "value": str(repo["forks"]), "inline": True},
            {"name": "Language", "value": repo.get("language") or "-", "inline": True},
        ],
    }


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        print("沒有設定 DISCORD_WEBHOOK_URL,略過通知")
        return

    result = latest_weekly_files()
    if result[0] is None:
        print("找不到 weekly_pushed 檔案,略過通知")
        return
    json_path, md_path, date_str = result

    with open(json_path, "r", encoding="utf-8") as f:
        repos = json.load(f)

    if not repos:
        print("本週沒有符合條件的 repo,略過通知")
        return

    new_count = sum(1 for r in repos if r.get("is_new"))
    top_repos = sorted(repos, key=lambda r: r["stars"], reverse=True)[:TOP_N]

    content = (
        f"📊 **GitHub 量化交易週報 — {date_str}**\n"
        f"本週有 push 的 repo:**{len(repos)}** 個(其中 **{new_count}** 個是本次新發現)\n"
        f"完整清單請看附件,以下是 star 數最高的前 {len(top_repos)} 名:"
    )
    payload = {"content": content, "embeds": [build_embed(r) for r in top_repos]}

    if md_path:
        with open(md_path, "rb") as f:
            resp = requests.post(
                webhook_url,
                data={"payload_json": json.dumps(payload)},
                files={"file": (md_path.name, f, "text/markdown")},
                timeout=30,
            )
    else:
        resp = requests.post(webhook_url, json=payload, timeout=30)

    resp.raise_for_status()
    print(f"已推送到 Discord:{len(repos)} 個 repo(附件:{md_path.name if md_path else '無'})")


if __name__ == "__main__":
    main()
