# PDFUnlocker v1.0.2 免設定分享版：驗收報告

日期：2026-10-30（台北）。Windows x64、Python 3.13.17（source\.venv）、PyInstaller 6.22.3、qpdf 12.4.2。

## v1.0.2 變更

- 授權：本程式以 MIT License 釋出（Copyright (c) 2026 Kaido-MSVC）；新增 LICENSE 與 THIRD_PARTY_NOTICES.txt，
  列出隨附第三方元件的名稱、版本、授權與網址。檢查結果無 GPL/AGPL 衝突（PyInstaller 有 bootloader 例外）。
- UI：主視窗新增選單「說明 > 關於」，顯示程式名稱、版本（讀取 app.py 的 VERSION）、作者／發行者、MIT 授權、
  「檢視 LICENSE 全文」按鈕，以及可捲動的第三方元件授權清單。版本升為 1.0.2。
- 建置：build.ps1 固定使用 source\.venv 的 Python 3.13（缺少或版本不符即報錯停止），
  並將 LICENSE、THIRD_PARTY_NOTICES.txt 打包進 _internal；排除未使用的 numpy、psutil、PyYAML、charset-normalizer
  （v1.0.1 由全域環境混入），包內 PDFUnlocker 資料夾檔案總量由 86.7 MB 降為 57.4 MB。
- 新增 source\requirements.lock.txt，記錄 Python 版本與全部建置套件的固定版本；requirements.txt 為頂層相依。
- licenses 資料夾移除 numpy（17 檔），因 v1.0.2 已不隨附 numpy；THIRD_PARTY_NOTICES 與 licenses 均未列
  已排除的 numpy、psutil、PyYAML、charset-normalizer。
- 與 v1.0.1 分享包逐檔雜湊比對：source 內僅 app.py、build.ps1、requirements.txt 變更；core.py、測試與 qpdf 二進位
  （source/tools/qpdf 與 _internal/tools/qpdf 共 10 檔）完全相同；licenses 僅移除 numpy，其餘檔案未變更。

## 驗收結果

- 原始碼單元測試 30/30 通過（source\.venv 的 Python 3.13.17），見 驗收紀錄/v1.0.2/unit-tests.log。
- 建置日誌確認使用 Python 3.13.17、環境為 source\.venv；系統 PATH 的 python 指向 3.14 時仍正確使用 .venv。
  另在沒有 .venv 的位置執行 build.ps1，確認會顯示錯誤並以結束碼 1 停止。
- 建置成品 EXE 冒煙測試（PATH 清空）：成功 2／失敗 1／跳過 1，使用包內 qpdf，見 exe-smoke.json。
- 分享 ZIP 解壓到「解壓驗收_日本語 & [分享]」路徑，PATH 清空執行冒煙測試：成功 2／失敗 1／跳過 1，
  使用解壓包內 qpdf，見 zip-exe-smoke.json。此 ZIP 與最終 ZIP 的程式檔案相同，最終版僅另含本報告與紀錄。
- 「關於」視窗：原始碼與 EXE 均實際開啟，選單「說明 > 關於」、版本 1.0.2、作者、MIT 授權、LICENSE 全文視窗、
  第三方清單均正常顯示；重複開啟會沿用同一視窗。
- 包內 _internal 已含 LICENSE、THIRD_PARTY_NOTICES.txt，且無 numpy、psutil、yaml、charset_normalizer。

## 限制

- 測試使用自建可拋棄 PDF，未讀寫使用者 PDF。未另做全新 Windows 虛擬機或全版本 Windows 相容性測試。
- qpdf 二進位與 v1.0.1 逐位元相同，未重做 PE／DLL 相依檢查；該檢查與官方雜湊比對見 v1.0.1 紀錄。
- 驗收紀錄資料夾最上層的檔案為 v1.0.1 的紀錄，v1.0.2 的紀錄在 驗收紀錄/v1.0.2。
- 原始碼 GUI 測試可能出現既有 CustomTkinter 字型警告，沿用 polygon_shapes 處理，實際 GUI 驗收均通過。

使用：完整解壓分享 ZIP，執行 PDFUnlocker/PDFUnlocker.exe；保留 _internal。無須安裝 qpdf 或設定 PATH。
原始碼與建置腳本位於 source。詳細機器可讀紀錄見分享包內「驗收紀錄」。v1.0.1 的 ZIP 保留在 archives。
