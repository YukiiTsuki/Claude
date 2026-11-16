# ⚽ Man City 賽後通知（Rúben Dias 個人數據）

資料來源：ESPN 公開 API（免費、不需要 API key）。ESPN **沒有球員評分**，所以通知裡不含評分。

曼城在**英超**或**歐冠**踢完一場比賽後，會自動推送一則通知到你的 Android 手機，內容包括：

- 比分（延長賽和 PK 大戰會另外標示）
- 每位進球球員和進球時間（含 PK、烏龍球、補時）
- Rúben Dias 的進球、助攻、黃紅牌、出場時間（並標示先發或替補）

```
歐冠｜Manchester City 2 - 1 Real Madrid
🥅 Manchester City：Erling Haaland 12'、Erling Haaland 45'+2'（PK）
🥅 Real Madrid：Vinícius Júnior 80'
👤 Rúben Dias｜⚽ 進球 0｜🅰️ 助攻 1｜牌 🟨｜⏱️ 90'（先發）
```

## 設定步驟（約 5 分鐘）

1. **手機裝 ntfy**：從 Google Play 下載 [ntfy](https://play.google.com/store/apps/details?id=io.heckel.ntfy)，按「+」訂閱一個主題。主題名稱要取得**別人猜不到**，例如 `mancity-dias-8f3k2q`，因為知道名稱的人都能看到你的通知。
2. **設定 GitHub Secret**：在 repo 的 **Settings → Secrets and variables → Actions → New repository secret** 新增 `NTFY_TOPIC`：你在第 1 步取的主題名稱
3. **測試**：到 **Actions → Man City 賽後通知 → Run workflow**，勾選「測試模式」再執行。程式會用最近一場已完賽的比賽產生通知內容，印在 Log 裡，不會推送。

> ⚠️ GitHub 的排程只會在 repo 的**預設分支**上執行。如果這個分支不是預設分支，要先 merge 進預設分支（或在 Settings 把它設成預設分支），排程才會自動跑。

## 運作方式

- 每週二、三、五、六、日的台灣時間 20:30～隔天 06:30，每 30 分鐘檢查一次曼城今天和前一天（UTC）有沒有比賽。也就是涵蓋台灣週三、四清晨（歐冠／英超週間賽）、週六清晨（英超週五晚場）、週末晚上到週一清晨（英超週末賽）。
- 前一天也查，是為了補推在時段外完場的比賽。例如英超偶爾在週一晚上（台灣週二清晨）踢，這種比賽會在台灣週二晚上 20:30 補推。
- **每場比賽只推一則**終場報告，檢查頻率只影響終場後多快收到通知。
- 比賽結束後，抓完整比賽資料，組成通知推送。
- 已經推送過的比賽會記錄在 `state/notified.json`，不會重複通知。
- 每週跑 105 次（5 個時段 × 21 次）。

## 自訂

`notify.py` 開頭的設定區可以修改：

- `LEAGUES`：要追蹤的賽事，例如加上 `"eng.fa": "足總盃"`、`"eng.league_cup": "聯賽盃"`。
- `PLAYER_NAME_KEYWORDS`：換成你要追蹤的球員。
- `TEAM_ID`：換成你要追蹤的球隊。

本機測試（只印出內容，不會推送）：

```bash
DRY_RUN=1 python football_notify/notify.py        # 檢查今天的比賽，只印不推
TEST_LATEST=1 python football_notify/notify.py    # 用最近一場完賽的比賽測試
```
