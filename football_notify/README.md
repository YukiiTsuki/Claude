# ⚽ Man City 賽後通知（Rúben Dias 個人數據）

曼城在**英超**或**歐冠**踢完一場比賽後，會自動推送一則通知到你的 Android 手機，內容包括：

- 比分（延長賽和 PK 大戰會另外標示）
- 每位進球球員和進球時間（含 PK、烏龍球、補時）
- Rúben Dias 的評分、進球、助攻、黃紅牌、出場時間（並標示先發或替補）

```
歐冠｜Manchester City 2 - 1 Real Madrid
🏆 UEFA Champions League｜League Stage - 4
🥅 Manchester City：E. Haaland 12'、E. Haaland 45+2'（PK）
🥅 Real Madrid：Vinícius Júnior 80'
⭐ Rúben Dias：評分 7.4
⚽ 進球 0｜🅰️ 助攻 1｜牌 🟨｜⏱️ 90'（先發）
```

## 設定步驟（約 5 分鐘）

1. **手機裝 ntfy**：從 Google Play 下載 [ntfy](https://play.google.com/store/apps/details?id=io.heckel.ntfy)，按「+」訂閱一個主題。主題名稱要取得**別人猜不到**，例如 `mancity-dias-8f3k2q`，因為知道名稱的人都能看到你的通知。
2. **申請 API-Football key**：到 <https://dashboard.api-football.com/register> 註冊免費帳號，然後在 Dashboard 複製你的 API key。
3. **把兩個值設成 GitHub Secrets**：在 repo 的 **Settings → Secrets and variables → Actions → New repository secret** 新增：
   - `API_FOOTBALL_KEY`：你的 API key
   - `NTFY_TOPIC`：你在第 1 步取的主題名稱
4. **測試**：到 **Actions → Man City 賽後通知 → Run workflow** 手動跑一次。如果今天沒有比賽，Log 會顯示正常結束，但不會推送任何通知。

> ⚠️ GitHub 的排程只會在 repo 的**預設分支**上執行。如果這個分支不是預設分支，要先 merge 進預設分支（或在 Settings 把它設成預設分支），排程才會自動跑。

## 運作方式

- 台灣時間 20:30～06:30 之間，每 30 分鐘檢查一次曼城今天和前一天（UTC）有沒有比賽。前一天也查，是為了補推在時段結束後才完場的比賽。
- **每場比賽只推一則**終場報告，檢查頻率只影響終場後多快收到通知。
- 比賽結束（FT / AET / PEN）後，再抓一次完整比賽資料，組成通知推送。
- 如果終場後評分還沒公布，會繼續等，最多等到開賽後約 4 小時；還是沒有評分的話，就照樣推送，評分欄位顯示「尚未公布」。
- 已經推送過的比賽會記錄在 `state/notified.json`，不會重複通知。
- 每天跑 21 次、大約用掉 45 次請求，在免費方案的 100 次額度內。

## 自訂

`notify.py` 開頭的設定區可以修改：

- `LEAGUES`：要追蹤的賽事，例如加上 `45: "足總盃"`、`48: "聯賽盃"`。
- `PLAYER_NAME_KEYWORDS` / `PLAYER_ID`：換成你要追蹤的球員。
- `TEAM_ID`：換成你要追蹤的球隊。

本機測試（只印出內容，不會推送）：

```bash
API_FOOTBALL_KEY=你的key DRY_RUN=1 python football_notify/notify.py
```
