# GitHub 量化交易 Repo 爬蟲

依 [config.yaml](config.yaml) 設定的 topics / 關鍵字 / star 門檻 / 活躍度,
用 GitHub Search API 定期找出符合條件的量化交易相關 repo。

## 運作方式

- `crawler.py` 依設定組出多組 GitHub search query,呼叫 Search API。
- 結果去重後累積存到 `data/repos.json`(完整資料庫,含 first_seen 首次發現日期)。
- 本次(`weekly_window_days` 天內)有 push 的 repo,另外存成兩份:
  - `data/weekly_pushed_<日期>.json` — 機器可讀,給之後的 Discord / Teams 通知用
  - `data/weekly_pushed_<日期>.md` — 人看的清單(repo 名稱、star/fork、topics、描述),方便快速掃過再自己丟給 AI 摘要
  每筆都有 `is_new` 欄位標示是不是這次才第一次抓到。
- 由 `.github/workflows/crawl.yml` 排程,**每週一台灣時間早上 9 點**自動跑一次,也可以在 GitHub Actions 頁面手動按 "Run workflow" 觸發。
- 跑完後 workflow 會自動把更新的 `data/` 內容 commit 回 repo。

## 部署步驟

1. 在 GitHub 建一個新 repo(可以 private),把這個資料夾內容 push 上去:
   ```bash
   git init
   git add .
   git commit -m "init: github quant repo crawler"
   git branch -M main
   git remote add origin <你的 repo URL>
   git push -u origin main
   ```
2. 到 repo 的 **Settings → Actions → General → Workflow permissions**,選擇
   「Read and write permissions」(讓 workflow 能把爬到的資料 commit 回去)。
3. 不需要額外設定 token——workflow 用的是 GitHub Actions 內建的 `GITHUB_TOKEN`。
4. 到 **Actions** 頁面手動觸發一次 `GitHub Quant Repo Crawler`,確認能正常跑完並看到
   `data/repos.json` 被更新。

## 調整篩選條件

直接改 [config.yaml](config.yaml),不用碰程式碼:

- `min_stars`:star 數門檻
- `max_days_since_push`:搜尋範圍,多少天內要有 push 才納入候選(排除死掉的專案)
- `weekly_window_days`:週報範圍,多少天內有 push 才會列進本次報告(預設 7 天)
- `topics` / `keywords`:要比對的 GitHub topic 標籤 / 關鍵字

## 之後串 Discord / Teams

`data/weekly_pushed_<日期>.json` 就是每次的週報清單(JSON array),
之後另一個通知專案只要讀這個檔案、組訊息、丟 webhook 就好,不需要重新爬一次。
