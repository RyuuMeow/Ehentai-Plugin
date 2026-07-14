# E-Hentai / ExHentai 插件

為 [CLI-Downloader](https://github.com/RyuuMeow/CLI-Downloader) 提供 E-Hentai 與 ExHentai 畫廊下載及列表瀏覽功能的外掛插件。

## 支援的 URL 格式

### 單個畫廊（Gallery）

| URL 範例 | 輸入類型 | 操作 |
|---|---|---|
| `https://e-hentai.org/g/1234567/a1b2c3d4e5/` | 單個 | `single_download` |
| `https://exhentai.org/g/1234567/a1b2c3d4e5/` | 單個 | `single_download` |

### 列表/搜尋（Listing）

| 路徑 | 說明 |
|---|---|
| `/` 或 `/?f_search=...` | 首頁或搜尋結果 |
| `/tag/<tag>` | 標籤列表 |
| `/uploader/<uploader>` | 上傳者列表 |
| `/favorites` | 收藏列表 |
| `/watched` | 觀看記錄 |
| `/popular` | 熱門畫廊 |
| `/toplists` | 排行榜 |

列表 URL 使用 `batch_download` 操作，會回傳可供挑選的畫廊清單。

### 不支援的 URL

- 單張圖片頁面：`https://e-hentai.org/s/<token>/<gid>-<page>/` — 已識別但 `page_download` 操作尚未實作。
- `exhentai.org` 的列表瀏覽 — 需要有效的 ExHentai cookie 認證才能存取。

## 使用範例

### CLI 下載

```bash
# 下載單個畫廊（使用自動策略）
clid download "https://e-hentai.org/g/1234567/a1b2c3d4e5/"

# 使用 torrent 策略下載
clid download "https://e-hentai.org/g/1234567/a1b2c3d4e5/" --param strategy=torrent

# 使用直接下載策略
clid download "https://e-hentai.org/g/1234567/a1b2c3d4e5/" --param strategy=direct

# 預覽模式 — 確認路由與參數，不發送網路請求
clid download "https://e-hentai.org/g/1234567/a1b2c3d4e5/" --dry-run --json
```

### 列表選擇與下載

```bash
# 瀏覽搜尋結果（每頁最多顯示 50 個畫廊）
clid download "https://e-hentai.org/?f_search=artist_name"

# 瀏覽特定標籤
clid download "https://e-hentai.org/tag/language:chinese"

# 從列表頁面選擇特定項目下載
clid download "https://e-hentai.org/uploader/uploader_name" --select <item-id>
```

## 認證

ExHentai 需要認證才能存取。

### 設定 Cookie

插件透過 `secrets` 設定來傳入認證 cookie：

- `cookies.ipb_member_id`：您的 IPB 會員 ID
- `cookies.ipb_pass_hash`：您的 IPB 密碼雜湊值

這兩個值可以從瀏覽器的 E-Hentai / ExHentai cookie 中取得。設定方式請參考 CLI-Downloader 的 secrets 管理機制。

### 內容存取限制

- 未登入時僅能存取非成人內容畫廊。
- ExHentai (`exhentai.org`) 必須備有效的 `ipb_member_id` 和 `ipb_pass_hash` cookie 才能瀏覽與下載。

## 設定

所有設定使用 `plugins.ehentai` 命名空間。

| 設定名稱 | 類型 | 預設值 | 範圍 | 說明 |
|---|---|---|---|---|
| `http.user_agent` | string | `CLI-Downloader/0.1` | — | HTTP 請求的 User-Agent 標頭 |
| `http.timeout_seconds` | number | `30.0` | ≥ 0.01 | HTTP 請求逾時秒數 |
| `http.retry_attempts` | integer | `2` | ≥ 0 | 請求失敗時的重試次數 |
| `http.delay_seconds` | number | `1.5` | 0–30 | 請求之間的延遲秒數 |

## 下載策略

插件支援三種下載策略：

| 策略 | 值 | 說明 |
|---|---|---|
| 自動 | `auto` | 若已設定 torrent 客戶端且畫廊有 torrent，則優先使用 torrent；否則回退為直接下載 |
| 直接 | `direct` | 逐一爬取畫廊圖片頁面，解析原始圖片 URL 並下載 |
| Torrent | `torrent` | 下載畫廊提供的 torrent 檔案，需設定 torrent 客戶端（如 qBittorrent） |

### 策略選擇行為

- `auto`：若 `torrent.client` 設定為 `qbittorrent` 且該畫廊有 torrent 候選，則選擇 torrent；否則使用 direct。
- `direct`：強制使用圖片頁面逐頁下載。
- `torrent`：僅下載 torrent 檔案。若畫廊無 torrent 候選，操作會失敗。

## 輸出範本變數

下載目錄使用以下範本變數來命名，來源為 `ResolvedItem.metadata`：

| 變數 | 說明 |
|---|---|
| `{gallery_id}` | 畫廊 ID（數字） |
| `{title}` | 畫廊標題（優先使用日文標題，否則使用英文標題） |
| `{artist}` | 作者名稱（取自 `artist` 標籤，多個以逗號分隔，無作者時為 `unknown`） |
| `{gid}` | 畫廊原始 ID |
| `{token}` | 畫廊 token |
| `{site}` | 站點標識（`e-hentai` 或 `exhentai`） |
| `{gallery_url}` | 畫廊完整 URL |
| `{title_jpn}` | 日文標題 |
| `{category}` | 畫廊分類 |
| `{uploader}` | 上傳者名稱 |
| `{file_count}` | 圖片數量 |
| `{filesize}` | 檔案總大小 |
| `{posted}` | 發布時間 |
| `{rating}` | 評分 |
| `{torrent_count}` | torrent 數量 |
| `{requested_strategy}` | 請求時選擇的下載策略 |

預設輸出目錄範本：`{gallery_id}-{title}`

範例：

- `{uploader}/{gallery_id}-{title}` — 依上傳者分目錄
- `{artist}/{gallery_id}-{title}` — 依作者分目錄（無作者時自動使用 `unknown`）
- `{category}/{gallery_id}-{title_jpn}` — 依分類分目錄並使用日文標題
- `[{gid}]{title}` — 使用原始 gid 作為前綴

## 網路與速率限制

插件實作保守的網路策略以避免觸發站方限制：

| 參數 | 值 | 說明 |
|---|---|---|
| 最大並行請求數 | 2 | 同時進行的 HTTP 請求數上限 |
| 最小請求間隔 | 1.5 秒 | 連續請求之間的最小間隔 |
| 可重試狀態碼 | 429, 502, 503 | 觸發自動重試的 HTTP 狀態碼 |
| 最大重試次數 | 5 | 每次請求的最大重試次數 |
| 最大退避時間 | 300 秒 | 重試時的最大指數退避時間 |

透過 `http.delay_seconds` 設定可進一步調整請求間隔（上限 30 秒）。

## 限制與已知問題

- **圖片頁面下載（`page_download`）尚未實作**：`/s/<token>/<gid>-<page>/` 的單頁下載路由已識別但操作尚未支援。
- **列表篩選器（`include_tags` / `exclude_tags`）尚未實作**：`batch_download` 操作中的標籤篩選參數已宣告但標記為待實作。
- **ExHentai 列表需要認證**：`exhentai.org` 的列表瀏覽（搜尋、標籤、上傳者等）必須先設定有效的 ExHentai cookie。
- **ExHentai API 限制**：ExHentai 不提供公開 API，metadata 查詢可能因網域而受限。
- **圖檔來源依賴圖片頁面 HTML**：直接下載模式需先取得每個圖片頁面的 HTML，再從中解析原始圖片 URL。圖片頁面結構變更可能導致解析失敗。

## 本機測試

插件包含使用模擬 HTTP 傳輸層的單元測試，不會實際連線至 E-Hentai：

```bash
# 從插件根目錄執行測試
python -m unittest discover -s tests -t .
```

> 測試使用假資料（fixtures）與模擬網路層，執行測試不會消耗任何網路流量。

## 疑難排解

### URL 未被插件識別

確認 URL 格式符合上述支援的格式。可使用 `--dry-run --json` 檢查路由結果：

```bash
clid download "你的URL" --dry-run --json
```

### 下載失敗或內容為空

1. 確認已正確設定認證 cookie（若畫廊為成人內容或位於 ExHentai）。
2. 檢查網路連線是否可正常存取 E-Hentai（部分地區可能需要 VPN）。
3. 確認 `http.timeout_seconds` 未設定過低（預設 30 秒通常足夠）。

### Torrent 策略回退至 direct

若設定 `torrent` 但最終仍使用 direct：
- 確認畫廊本身是否提供 torrent 下載選項（`torrent_count` > 0）。
- 確認 `torrent.client` 設定為 `qbittorrent` 且服務正常運作。

## 免責聲明（Disclaimer）

**本插件僅供學術研究、網路協定與程式設計技術之教學示範用途使用，不得
用於任何商業用途或違反目標網站服務條款、當地法規之行為。**

本插件為 [CLI-Downloader](https://github.com/RyuuMeow/CLI-Downloader) 之社群擴充元件，示範如何解析特定網站之公開
頁面結構與 API 回應，作為網路請求、資料解析與自動化技術之程式設計
參考範例，不具持續性服務屬性。

- **關於目標網站**：本插件僅為技術層面的介接工具，**對目標網站之
  營運主體、內容來源合法性、著作權歸屬、內容分級或其提供服務是否
  符合當地法規，不做任何調查、保證、背書或評論**。使用者應自行判斷
  並確認該網站及其內容來源之合法性，開發者不因插件支援特定網站而
  暗示或保證該網站之正當性。
- **關於付費／限制內容存取**：本插件不含任何繞過付費牆、破解驗證或
  規避存取控制之機制。若使用者選擇存取需登入或付費之內容，前提為
  使用者本身**已具備合法帳號權限**（如已登入、已訂閱、已付費），
  插件僅代為載入使用者**自行於官方網站登入**取得之 Session／Cookie，
  其存取範圍完全對應該帳號原有之權限，插件本身不擴大、不繞過任何
  平台既有的存取限制。
- 透過本插件存取或下載之任何內容，其著作權、授權與合法性歸屬於原
  網站或原著作權人，本插件與其開發者**不擁有、不主張、不轉移**任何
  相關權利，亦不對內容本身之真實性、合法性負責。**嚴禁將下載內容
  用於商業用途、公開散布、二次上傳或大量轉載。**
- 使用者應自行確認其使用行為符合目標網站服務條款（Terms of Service）
  及所在地區之相關法規。因使用本插件所生之任何後果——包括但不限於
  帳號限制／停權、著作權爭議、法律責任或其他任何損失——**概由使用者
  自行承擔**，與插件開發者、貢獻者無關。
- 本插件依現狀（AS IS）提供，不保證其功能正確性、完整性，亦不保證
  於目標網站政策或結構變更後仍可持續運作。

**若您無法確認目標網站之合法性、無法保證您的使用行為符合當地法規與
目標網站服務條款，請勿安裝或使用本插件。使用本插件即代表您已閱讀、
理解並同意上述所有條款。**
