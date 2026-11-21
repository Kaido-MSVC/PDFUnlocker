# PDFUnlocker v1.0.3 Security Update — Windows x64

離線 PDF 批次解鎖桌面工具，支援多檔、資料夾掃描與個別密碼詢問。設有開啟密碼的 PDF 須提供有效密碼，同名輸出會另行編號。作者與發布者：**Kaido-MSVC**。

## 下載與使用

目前穩定版為 v1.0.3 Security Update，適用 Windows x64。 [GitHub Release v1.0.3](https://github.com/Kaido-MSVC/PDFUnlocker/releases/tag/v1.0.3)

- 下載免安裝分享版，完整解壓後執行 `PDFUnlocker-v1.0.3-Portable/PDFUnlocker/PDFUnlocker.exe`。 [Portable ZIP](https://github.com/Kaido-MSVC/PDFUnlocker/releases/download/v1.0.3/PDFUnlocker-v1.0.3-Portable-Windows-x64.zip)
- 以 PowerShell 計算 ZIP 的 SHA-256，再核對清單中同一個 ZIP 檔名對應的值。 [SHA256SUMS.txt](https://github.com/Kaido-MSVC/PDFUnlocker/releases/download/v1.0.3/SHA256SUMS.txt)
- ZIP 一併提供 `source/`、授權與驗收紀錄。也可從 Release 頁面的 Source code 下載原始碼。

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\PDFUnlocker-v1.0.3-Portable-Windows-x64.zip
```

適用目標為 Windows 10/11 x64。Python、qpdf 與所需執行階段隨附，不必另行安裝或設定 PATH。請保留完整資料夾，尤其 `_internal` 與 `licenses`，不要只複製 EXE。詳細操作見 [使用說明](使用說明.md)。

1. 加入 PDF 或資料夾，可包含子目錄。
2. 可選填共用密碼；個別檔案密碼不同時會詢問，可重試、跳過或取消剩餘工作。
3. 按「開始解鎖」，結果存到各原檔旁的 `Unlocked` 資料夾。同名自動加 `(2)`、`(3)`，不覆蓋原檔或既有輸出。

需要開啟密碼的 PDF 仍須提供有效密碼。密碼透過標準輸入傳給 qpdf。程式拒絕換行與 NUL，並略過掃描中的 `Unlocked`、符號連結與目錄接合點。取消會終止目前的 qpdf 子程序並清理暫存檔。各階段的 qpdf 子程序逾時上限為 5 分鐘。

## v1.0.3 安全變更

- 封裝版只使用隨附的 qpdf。若執行檔或必要 DLL 缺失，請重新下載或完整解壓。
- 保留有來源標記的 PDF 所帶的 Windows `Zone.Identifier`。標記無法讀取或保留時，該檔案處理失敗。解鎖後的 PDF 仍可能包含 JavaScript、附件等主動內容。
- 路徑檢查涵蓋掃描根目錄及交付輸出的各層目錄，並在處理時保留控制代碼。其他人可寫入的共用資料夾仍可能有競爭風險。
- 限制 qpdf 輸出占用的記憶體，並在取消或逾時時終止子程序。建置時驗證 Python 套件與內附 qpdf 檔案的 SHA-256。

完整變更見 [CHANGELOG](CHANGELOG.md)。

## 建置

Python 3.14.10 x64、CustomTkinter 6.0.0、Pillow 13.0.0、PyInstaller 6.22.3，內附 qpdf 12.4.2。完整建置套件版本與 Windows x64 wheel 雜湊見 [requirements.lock.txt](source/requirements.lock.txt)。

在 `source` 目錄執行：

```powershell
py -3.14 -m venv ../.venv-pdfunlocker-314
$python = '..\.venv-pdfunlocker-314\Scripts\python.exe'
& $python -m pip --isolated install --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -r requirements.lock.txt
.\build.ps1 -Python $python
```

建置前會驗證 `source/tools/qpdf` 中五個官方二進位檔的 SHA-256。檔案缺失或雜湊不符時會停止建置。預設輸出位於專案根目錄 `app/`，可用 `-DistPath` 指定獨立目錄。從 `source/` 可執行 `python -m unittest discover -v`。

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

安全回歸測試可核對 `Zone.Identifier` 的內容。檔案總管的預覽行為會依 Windows 版本、更新、原則及 PDF 預覽處理常式而異。歷史驗收詳見 [v1.0.2 發行說明](https://github.com/Kaido-MSVC/PDFUnlocker/releases/tag/v1.0.2)。
