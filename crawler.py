"""
GitHub 量化交易相關 repo 爬蟲。

依 config.yaml 設定的 topics / 關鍵字 / star 門檻 / 活躍度,
透過 GitHub Search API 找出符合條件的 repo,結果累積存到 data/repos.json,
並把「這週(weekly_window_days 天內)有 push」的 repo 另外存一份到
data/weekly_pushed_<date>.json,方便之後接 Discord / Teams 通知使用。
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
REPOS_DB = DATA_DIR / "repos.json"
CONFIG_PATH = ROOT / "config.yaml"

GITHUB_API = "https://api.github.com/search/repositories"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_existing_db() -> dict:
    if REPOS_DB.exists():
        with open(REPOS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_queries(cfg: dict) -> list[str]:
    min_stars = cfg["min_stars"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cfg["max_days_since_push"])).strftime("%Y-%m-%d")

    queries = []
    for topic in cfg.get("topics", []):
        queries.append(f"topic:{topic} stars:>={min_stars} pushed:>={cutoff}")
    for kw in cfg.get("keywords", []):
        queries.append(f'"{kw}" in:name,description stars:>={min_stars} pushed:>={cutoff}')
    return queries


def write_markdown_report(repos: list[dict], out_path: Path, today: str) -> None:
    lines = [f"# GitHub 量化交易週報 — {today}", "", f"本週有 push 的 repo:共 {len(repos)} 個", ""]
    for r in repos:
        tag = " 🆕" if r["is_new"] else ""
        topics = ", ".join(r["topics"]) if r["topics"] else "-"
        lines.append(f"## [{r['full_name']}]({r['html_url']}){tag}")
        lines.append(f"- ⭐ {r['stars']} · 🍴 {r['forks']} · language: {r['language'] or '-'}")
        lines.append(f"- pushed: {r['pushed_at']}")
        lines.append(f"- topics: {topics}")
        lines.append(f"- {r['description'] or '(無描述)'}")
        lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def search_github(query: str, token: str, per_page: int, max_pages: int) -> list[dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results = []
    for page in range(1, max_pages + 1):
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": per_page, "page": page}
        resp = requests.get(GITHUB_API, headers=headers, params=params, timeout=30)

        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset - time.time(), 1)
            print(f"  觸發 rate limit,等待 {wait:.0f} 秒...", file=sys.stderr)
            time.sleep(wait)
            resp = requests.get(GITHUB_API, headers=headers, params=params, timeout=30)

        resp.raise_for_status()
        items = resp.json().get("items", [])
        results.extend(items)
        if len(items) < per_page:
            break
        time.sleep(2)  # 避免打太快超過 search API 的速率限制

    return results


def main():
    cfg_all = load_config()
    cfg = cfg_all["search"]
    token = os.environ.get("GITHUB_TOKEN", "")

    queries = build_queries(cfg)
    print(f"共 {len(queries)} 組查詢條件")

    found = {}  # repo_id -> repo dict(原始 API 回傳)
    for q in queries:
        print(f"查詢: {q}")
        try:
            items = search_github(q, token, cfg["per_page"], cfg["max_pages_per_query"])
        except requests.HTTPError as e:
            print(f"  失敗: {e}", file=sys.stderr)
            continue
        print(f"  取得 {len(items)} 筆")
        for item in items:
            found[str(item["id"])] = item
        time.sleep(2)

    db = load_existing_db()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    weekly_cutoff = now - timedelta(days=cfg.get("weekly_window_days", 7))
    weekly_pushed = []

    for repo_id, item in found.items():
        entry = {
            "id": item["id"],
            "full_name": item["full_name"],
            "html_url": item["html_url"],
            "description": item.get("description"),
            "stars": item["stargazers_count"],
            "forks": item["forks_count"],
            "open_issues": item["open_issues_count"],
            "topics": item.get("topics", []),
            "language": item.get("language"),
            "pushed_at": item["pushed_at"],
            "last_checked": today,
        }
        entry["is_new"] = repo_id not in db
        entry["first_seen"] = db[repo_id]["first_seen"] if repo_id in db else today
        db[repo_id] = entry

        pushed_at = datetime.strptime(item["pushed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if pushed_at >= weekly_cutoff:
            weekly_pushed.append(entry)

    DATA_DIR.mkdir(exist_ok=True)
    with open(REPOS_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2, sort_keys=True)

    if weekly_pushed:
        weekly_pushed.sort(key=lambda r: r["pushed_at"], reverse=True)
        json_path = DATA_DIR / f"weekly_pushed_{today}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(weekly_pushed, f, ensure_ascii=False, indent=2)
        md_path = DATA_DIR / f"weekly_pushed_{today}.md"
        write_markdown_report(weekly_pushed, md_path, today)
        print(f"本週有 push 的 repo 共 {len(weekly_pushed)} 個,已存到 {json_path.name} / {md_path.name}")
    else:
        print("本週沒有任何符合條件的 repo 有 push")

    print(f"資料庫累積共 {len(db)} 個 repo")


if __name__ == "__main__":
    main()
