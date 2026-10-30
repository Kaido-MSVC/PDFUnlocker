# PDFUnlocker v1.0.2 — Windows x64

離線 PDF 批次解鎖桌面工具，支援多檔、資料夾掃描與個別密碼詢問。作者與發布者：**Kaido-MSVC**。

## 下載與使用

正式下載見 [GitHub Release v1.0.2](https://github.com/Kaido-MSVC/PDFUnlocker/releases/tag/v1.0.2)。

- [免安裝分享版 ZIP](https://github.com/Kaido-MSVC/PDFUnlocker/releases/download/v1.0.2/PDFUnlocker-v1.0.2-Portable-Windows-x64.zip)：完整解壓後，執行 `PDFUnlocker-v1.0.2-Portable/PDFUnlocker/PDFUnlocker.exe`。
- [SHA256SUMS.txt](https://github.com/Kaido-MSVC/PDFUnlocker/releases/download/v1.0.2/SHA256SUMS.txt)：本次正式 ZIP 的 SHA-256。
- 原始碼可 clone 本倉庫或使用 Release 的 Source code 下載；ZIP 亦含 `source/`、授權與驗收紀錄。

適用目標為 Windows 10/11 x64。Python、qpdf 與所需執行階段隨附，不必另行安裝或設定 PATH。請保留完整資料夾，尤其 `_internal` 與 `licenses`，不要只複製 EXE。詳細操作見 [使用說明](使用說明.md)。

1. 加入 PDF 或資料夾，可包含子目錄。
2. 可選填共用密碼；個別檔案密碼不同時會詢問，可重試、跳過或取消剩餘工作。
3. 按「開始解鎖」，結果存到各原檔旁的 `Unlocked` 資料夾。同名自動加 `(2)`、`(3)`，不覆蓋原檔或既有輸出。

需要開啟密碼的 PDF 仍須提供有效密碼，本工具不猜測密碼。密碼透過標準輸入傳給 qpdf，不放進命令列、密碼檔或紀錄；換行與 NUL 不接受。資料夾掃描排除 `Unlocked` 與目錄連結。取消會等目前的 qpdf 操作結束，每次操作最多 5 分鐘。

## v1.0.2 變更

- 新增 MIT 授權、第三方元件聲明，以及「說明 > 關於」視窗，可查看版本、作者、LICENSE 全文與第三方清單。
- 建置固定使用 `source/.venv` 的 Python 3.13，加入固定版本相依清單。
- 移除未使用的建置相依與負載；沿用已驗收的 PDF 處理核心及 qpdf 二進位。

## 建置

Python 3.13.17 x64、CustomTkinter 6.0.0、Pillow 13.0.0、PyInstaller 6.22.3；內附 qpdf 12.4.2。完整建置套件版本見 [requirements.lock.txt](source/requirements.lock.txt)。

在 `source` 目錄執行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\build.ps1
```

建置腳本不下載 qpdf，使用 `source/tools/qpdf` 內已驗證的官方二進位；缺少 Python 3.13 虛擬環境時停止。建置輸出位於專案根目錄 `app/`，原始碼測試與冒煙測試入口在 `source/`。

## 授權

自有程式碼採 [MIT License](LICENSE)，Copyright (c) 2026 Kaido-MSVC。MIT 不取代第三方元件各自的授權。

| 元件 | 授權 |
|---|---|
| Python、Tcl/Tk | PSF 與 Tcl/Tk 原授權 |
| CustomTkinter、darkdetect、packaging、Pillow | MIT、BSD、Apache 等各自授權 |
| PyInstaller bootloader | GPL 與 Bootloader Exception |
| qpdf | Apache-2.0 |
| Microsoft Visual C++ runtime | Microsoft 再散布條款 |

完整元件版本與通知見 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)、[licenses](licenses) 及 [qpdf 來源與授權](licenses/qpdf/來源與授權.md)。分享時請保留授權全文與通知。This software is based in part on the work of the Independent JPEG Group.

## 驗證與限制

沿用 2026-10-30 v1.0.2 已驗收的程式與分享包：30 項單元測試通過，EXE 與解壓後分享包在清空 PATH 下完成冒煙測試，關於視窗已實際驗收。冒煙流程包含預期失敗與跳過案例，不代表所有輸入 PDF 都能成功。詳見 [v1.0.2 驗收報告](archives/PDFUnlocker-v1.0.2-免設定分享版-驗收報告.md) 及 [驗收紀錄](驗收紀錄/v1.0.2)。

本次 GitHub 發布核對既有 ZIP SHA-256、包內逐檔清單、原始碼與授權一致性，未重新編譯或重跑已通過且不受影響的整套測試。未另做乾淨 Windows 虛擬機或全版本 Windows 相容性測試。歷史報告與紀錄保留當時的本機路徑及發布前狀態；正式下載以 Release 附件為準。

`archives/*.zip` 已排除在 Git 版控外，正式 ZIP 透過 GitHub Releases 發布。倉庫內 `archives/SHA256SUMS.txt` 保留歷史封裝紀錄；Release 附件的同名清單僅列本次正式 ZIP。
