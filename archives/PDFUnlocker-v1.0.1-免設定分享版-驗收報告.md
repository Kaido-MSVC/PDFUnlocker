# PDFUnlocker v1.0.1 免設定分享版：驗收報告

日期：2026-10-23（台北）。Windows x64、Python 3.13、PyInstaller 6.22.3、qpdf 12.4.2。

已找回先前完成的 v1.0.1 原始碼與 Windows ZIP；來源為同日工作區 -11 的 outputs/PDFUnlocker-v1.0.1。
原始 Python 檔均與其既有 SHA256SUMS.json 比對一致，非以 v1.0 替代。

變更僅限包內 qpdf 優先尋找、缺檔／啟動錯誤提示、建置時收入官方 qpdf 與必要 DLL，以及對應測試／說明。
app.py、test_v101.py、windowed_runtime.py、make_icon.py 均與 v1.0.1 逐位元相同；discover 與 process_batch AST 相同。
原有 P2/P3 掃描容錯、異常中止狀態、密碼管線與原檔安全流程保留。差異見包內 patch。

驗收結果：
- PATH 清空的原始碼測試 30/30 通過：既有 25 項加 5 項隨附引擎測試。
- 原始碼 GUI、PyInstaller EXE GUI、ZIP 解壓後 EXE GUI 均通過；三者 PATH 均為空。
- ZIP 解壓到「解壓驗收_日本語 & [分享]」路徑，確認使用解壓包內 qpdf；不依賴 PATH 中 qpdf 或 Python。
- 實際 Tk 視窗與工作執行緒處理加密 PDF，GUI 結果 2 成功／1 損壞失敗／1 未加密跳過；個別密碼對話框、取消、掃描、860×620 視窗與異常中止狀態均通過。
- 中日文、空白、符號、emoji 檔名；含中日文／前後空白／符號的 UTF-8 密碼；128/256 位元、owner 密碼、錯誤共用密碼及重試均通過。
- 原檔 SHA256 不變、既有輸出不覆蓋、同名加 (2)、驗證失敗不發布、暫存清理、密碼只走標準輸入等測試通過。
- PE 檢查五個 qpdf 相關檔案均為 AMD64；非系統 DLL 相依完整，執行時四個 DLL 實際由包內載入。
- 官方 ZIP、原始碼 tar.gz、vcpkg.zip 雜湊比對一致；附 Apache、Microsoft 與靜態相依授權資料。

限制：測試使用自建可拋棄 PDF，未讀寫使用者 PDF；本機已安裝系統 qpdf，但三次 GUI 測試 PATH 清空，選用路徑明確指向包內，DLL 載入位置亦已核對。
未另做全新 Windows 虛擬機或全版本 Windows 相容性測試。保留 sigstore 資料，未驗證其簽章身分。
原始碼測試曾出現既有 CustomTkinter 字型警告，沿用原本 polygon_shapes 處理，實際 GUI 驗收均通過。

使用：完整解壓分享 ZIP，執行 PDFUnlocker/PDFUnlocker.exe；保留 _internal。無須安裝 qpdf 或設定 PATH。
原始碼與建置腳本位於 source，分享包也附必要來源；獨立 source ZIP 方便另存。
詳細機器可讀紀錄、原版來源雜湊、建置日誌與 DLL 相依表見分享包內「驗收紀錄」。
