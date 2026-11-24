# ⚽ Man City Season Tracker

這個網頁呈現曼城本季（2026-27）所有一線隊賽事的資訊，介面為英文。

- **This Week**：本週（週一到週日）的所有比賽，下一場會標亮
- **Last Week's Results**：上週的賽果
- **Season at a Glance**：近 5 場戰績和各賽事成績
- **Premier League Journey**：每輪排名和累積積分折線圖，可以選一隊比較
- **Premier League Table**：目前積分榜（曼城那一列標亮）
- **All Fixtures & Results**：所有賽程和賽果，可依賽事篩選

資料來源是 ESPN 公開 API（免費、不需要 API key），涵蓋英超、歐冠、足總盃、聯賽盃和社區盾。
英超每輪排名是抓 20 隊所有已完賽的比分**自己算**出來的（積分 → 淨勝球 → 進球數）。
「第 N 輪」的意思是每隊踢完前 N 場聯賽後的排名，所以延賽不會讓排名失真。

## 檔案

```
mancity_site/
  fetch_data.py   抓 ESPN 資料 → 產生 site/data.json
  site/           網頁本體（index.html、style.css、app.js）
.github/workflows/mancity-site.yml   每 6 小時更新資料並部署到 GitHub Pages
```

## 第一次設定（GitHub Pages）

1. 到 repo 的 **Settings → Pages**，**Source** 選 **GitHub Actions**
2. 到 **Settings → Environments → github-pages**，在 **Deployment branches and tags** 加上
   `mci-match-webpage`（預設只允許從預設分支部署；合併到預設分支後就不用這步）
3. 到 **Actions → Man City site → Run workflow** 手動執行一次
4. 完成後網址會出現在 workflow 的 deploy 步驟，通常是 `https://<帳號>.github.io/<repo>/`

## 在自己電腦上預覽

```bash
python mancity_site/fetch_data.py
```

```bash
python -m http.server 8000 --directory mancity_site/site
```

然後打開 http://localhost:8000 。
