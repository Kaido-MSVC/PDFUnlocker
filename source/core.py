"""Sequential qpdf backend. Never log raw subprocess output or passwords."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from collections.abc import Callable

TIMEOUT = 300


def bundled_qpdf() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'tools' / 'qpdf' / 'qpdf.exe'


class ProcessingError(Exception):
    pass


@dataclass
class Result:
    path: Path
    state: str
    detail: str
    output: Path | None = None


class Qpdf:
    def __init__(self, executable: str | None = None):
        bundled = bundled_qpdf()
        self.executable = executable or (str(bundled) if bundled.is_file() else shutil.which('qpdf'))
        if not self.executable:
            raise ProcessingError('找不到 qpdf，請完整解壓分享包並保留 _internal 資料夾；亦可使用系統已安裝的 qpdf。')

    def run(self, args: list[str], password: str = '') -> subprocess.CompletedProcess:
        if any(c in password for c in ('\r', '\n', '\x00')):
            raise ProcessingError('密碼不能包含換行或 NUL 字元。')
        try:
            return subprocess.run(
                [self.executable, '--password-file=-', *args],
                input=(password + '\n').encode('utf-8'),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                timeout=TIMEOUT, check=False, shell=False,
            )
        except subprocess.TimeoutExpired:
            raise ProcessingError('qpdf 處理超過 5 分鐘，已終止該次操作。') from None
        except OSError:
            raise ProcessingError('無法啟動 qpdf，請確認分享包已完整解壓（含 DLL），並檢查存取權限。') from None

    def kind(self, path: Path, password: str = '') -> str:
        probe = self.run(['--requires-password', str(path)], password)
        if probe.returncode == 0:
            return 'locked'
        if probe.returncode == 3:
            return 'encrypted'
        # qpdf uses 2 for BOTH unencrypted and operational errors.
        if probe.returncode == 2:
            check = self.run(['--check', str(path)], password)
            if check.returncode in (0, 3):
                return 'plain'
        raise ProcessingError('無法讀取 PDF：檔案損壞、格式不支援或無存取權限。')

    def decrypt(self, path: Path, password: str) -> tuple[Path, bool]:
        folder = path.parent / 'Unlocked'
        folder.mkdir(exist_ok=True)
        if folder.is_symlink() or (hasattr(folder, 'is_junction') and folder.is_junction()):
            raise ProcessingError('Unlocked 不能是符號連結或目錄接合點。')
        fd, temporary = tempfile.mkstemp(prefix='.unlock-', suffix='.tmp', dir=folder)
        os.close(fd)
        temp = Path(temporary)
        try:
            proc = self.run(['--decrypt', str(path), str(temp)], password)
            if proc.returncode not in (0, 3):
                raise ProcessingError('解鎖失敗：PDF 無法處理或輸出位置無法寫入。')
            verified = self.run(['--check', str(temp)])
            encryption = self.run(['--is-encrypted', str(temp)])
            if verified.returncode not in (0, 3) or encryption.returncode != 2 or encryption.stderr:
                raise ProcessingError('輸出驗證失敗，未保留不完整結果。')
            # Windows rename refuses an existing destination, including a race.
            for n in range(1, 100000):
                name = path.name if n == 1 else f'{path.stem} ({n}){path.suffix}'
                target = folder / name
                try:
                    if os.name == 'nt':
                        os.rename(temp, target)
                    else:
                        os.link(temp, target)
                        temp.unlink()
                    return target, proc.returncode == 3 or verified.returncode == 3
                except FileExistsError:
                    continue
            raise ProcessingError('同名輸出檔案過多。')
        finally:
            temp.unlink(missing_ok=True)


def discover(items: list[Path], cancel: threading.Event | None = None) -> tuple[list[Path], int]:
    found: list[Path] = []
    seen: set[str] = set()
    ignored = 0

    def add(path: Path):
        nonlocal ignored
        try:
            if path.suffix.lower() != '.pdf' or path.is_symlink():
                return
            key = os.path.normcase(str(path.resolve()))
            absolute = path.absolute()
        except OSError:
            ignored += 1
            return
        if key not in seen:
            seen.add(key)
            found.append(absolute)

    def walk_error(_error):
        nonlocal ignored
        ignored += 1

    for item in items:
        if cancel and cancel.is_set():
            break
        try:
            is_dir = item.is_dir()
        except OSError:
            ignored += 1
            continue
        if is_dir:
            for root, dirs, files in os.walk(item, followlinks=False, onerror=walk_error):
                if cancel and cancel.is_set():
                    break
                readable_dirs = []
                for d in sorted(dirs):
                    if d.casefold() == 'unlocked':
                        continue
                    try:
                        child = Path(root, d)
                        if not child.is_symlink() and not child.is_junction():
                            readable_dirs.append(d)
                    except OSError:
                        ignored += 1
                dirs[:] = readable_dirs
                for name in sorted(files):
                    if cancel and cancel.is_set():
                        break
                    add(Path(root, name))
        else:
            add(item)
    return found, ignored


def process_batch(paths: list[Path], common: str, cancel: threading.Event,
                  ask: Callable[[Path, str], str | None], emit: Callable,
                  engine: Qpdf | None = None):
    qpdf = engine or Qpdf()
    for index, path in enumerate(paths):
        if cancel.is_set():
            for remaining in paths[index:]:
                emit('result', Result(remaining, 'skip', '取消後跳過'))
            break
        emit('current', (index + 1, path))
        password = ''
        try:
            kind = qpdf.kind(path)
            if kind == 'plain':
                emit('result', Result(path, 'skip', '未加密，無須解鎖'))
                continue
            label = '無開啟密碼的加密／權限限制'
            if kind == 'locked':
                label = '需要開啟密碼'
                password = common
                accepted = bool(common) and qpdf.kind(path, password) == 'encrypted'
                reason = '共用密碼不正確' if common else '請輸入此檔案的開啟密碼'
                while not accepted and not cancel.is_set():
                    password = ask(path, reason)
                    if password is None:
                        break
                    accepted = qpdf.kind(path, password) == 'encrypted'
                    reason = '密碼不正確，請重試或跳過'
                if not accepted or cancel.is_set():
                    emit('result', Result(path, 'skip', label + '；已跳過'))
                    continue
            if cancel.is_set():
                emit('result', Result(path, 'skip', '取消後跳過'))
                continue
            output, warning = qpdf.decrypt(path, password)
            detail = label + ('；完成（qpdf 有修復警告）' if warning else '；完成')
            emit('result', Result(path, 'success', detail, output))
        except (ProcessingError, OSError) as exc:
            detail = str(exc) if isinstance(exc, ProcessingError) else '檔案或輸出資料夾無法存取。'
            emit('result', Result(path, 'fail', detail))
        finally:
            password = ''
    common = ''
