"""Sequential qpdf backend. Never log raw subprocess output or passwords."""
from __future__ import annotations

import os
from contextlib import contextmanager, ExitStack
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from collections.abc import Callable

from windows_files import hold_path, is_link, native_path, read_zone, write_zone

TIMEOUT = 300
QPDF_FILES = ('qpdf.exe', 'qpdf30.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')


def bundled_qpdf() -> Path:
    root = Path(__file__).absolute().parent
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).absolute().parent / '_internal'
        if not getattr(sys, '_MEIPASS', None) or Path(sys._MEIPASS) != root:
            raise ProcessingError('封裝位置不正確，請重新下載或完整解壓分享包。')
    return root / 'tools' / 'qpdf' / 'qpdf.exe'


class ProcessingError(Exception):
    pass


class Cancelled(ProcessingError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('取消後跳過')


@dataclass(frozen=True)
class QpdfResult:
    returncode: int
    has_stderr: bool = False


@dataclass
class Result:
    path: Path
    state: str
    detail: str
    output: Path | None = None


class Qpdf:
    def __init__(self, executable: str | None = None):
        if executable is not None and getattr(sys, 'frozen', False):
            raise ProcessingError('封裝版只能使用隨附的 qpdf。')
        self._bundled = executable is None
        path = bundled_qpdf() if self._bundled else Path(executable)
        if not path.is_absolute() or path.suffix.lower() != '.exe':
            raise ProcessingError('開發用 qpdf 必須是 .exe 的絕對路徑。')
        self.executable = str(path)
        with self._hold_executable():
            pass

    @contextmanager
    def _hold_executable(self):
        path = Path(self.executable)
        files = [path.parent / name for name in QPDF_FILES] if self._bundled else [path]
        with ExitStack() as stack:
            try:
                for file in files:
                    stack.enter_context(hold_path(file))
            except OSError:
                if self._bundled:
                    raise ProcessingError('隨附的 qpdf 或 DLL 無法使用，請重新下載或完整解壓分享包。') from None
                raise ProcessingError('開發用 qpdf 路徑無法使用。') from None
            yield

    def run(self, args: list[str], password: str = '', *, cancel=None) -> QpdfResult:
        check_cancel(cancel)
        if any(c in password for c in ('\r', '\n', '\x00')):
            raise ProcessingError('密碼不能包含換行或 NUL 字元。')
        try:
            password_line = (password + '\n').encode('utf-8')
        except UnicodeError:
            raise ProcessingError('密碼含有無法轉換的字元。') from None
        try:
            with self._hold_executable(), ExitStack() as stack:
                check_cancel(cancel)
                env = dict(os.environ)
                env['PATH'] = ''
                if os.name == 'nt' and any(arg.startswith('\\\\?\\') for arg in args):
                    # 官方 Windows qpdf 的命令列會改寫部分長路徑。參數檔只存選項與路徑。
                    if any(c in arg for arg in args for c in ('\r', '\n', '\x00')):
                        raise ProcessingError('無法處理含控制字元的檔案路徑。')
                    temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='pdfunlocker-'))
                    argfile = Path(temporary) / 'args.txt'
                    argfile.write_text('\n'.join(args) + '\n', encoding='utf-8', newline='\n')
                    stack.enter_context(hold_path(argfile))
                    args = ['@' + str(argfile)]
                check_cancel(cancel)
                process = subprocess.Popen(
                    [self.executable, '--password-file=-', *args],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    cwd=Path(self.executable).parent, env=env,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), shell=False,
                )
                with process:
                    return self._wait(process, password_line, cancel)
        except OSError:
            raise ProcessingError('無法執行 qpdf，請確認封裝完整及檔案可存取。') from None

    @staticmethod
    def _wait(process, password_line, cancel):
        has_stderr = False
        stderr_failed = False

        def drain_stderr():
            nonlocal has_stderr, stderr_failed
            try:
                while process.stderr.read1(4096):
                    has_stderr = True
            except OSError:
                stderr_failed = True

        def send_password():
            try:
                with process.stdin:
                    process.stdin.write(password_line)
            except OSError:
                # 子程序可能在讀取密碼前就結束。以結束代碼判斷結果。
                pass

        reader = threading.Thread(target=drain_stderr)
        writer = threading.Thread(target=send_password)
        started = []
        deadline = time.monotonic() + TIMEOUT
        try:
            for thread in (reader, writer):
                thread.start()
                started.append(thread)
            while True:
                check_cancel(cancel)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProcessingError('qpdf 操作逾時，已終止該次操作。')
                try:
                    code = process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            for thread in started:
                thread.join()
        check_cancel(cancel)
        if stderr_failed or code not in (0, 2, 3):
            raise ProcessingError(f'qpdf 非預期結束或讀取失敗（代碼 {code}）。')
        return QpdfResult(code, has_stderr)

    def kind(self, path: Path, password: str = '', *, cancel=None) -> str:
        path = path.absolute()
        with hold_path(path):
            return self._kind(path, password, cancel)

    def _kind(self, path, password, cancel):
        filename = str(native_path(path))
        probe = self.run(['--requires-password', filename], password, cancel=cancel)
        if probe.returncode == 0:
            return 'locked'
        if probe.returncode == 3:
            return 'encrypted'
        # qpdf uses 2 for BOTH unencrypted and operational errors.
        if probe.returncode == 2:
            check = self.run(['--check', filename], password, cancel=cancel)
            if check.returncode in (0, 3):
                return 'plain'
        raise ProcessingError('無法讀取 PDF：檔案損壞、格式不支援或無存取權限。')

    def decrypt(self, path: Path, password: str, *, cancel=None) -> tuple[Path, bool]:
        check_cancel(cancel)
        path = path.absolute()
        folder = path.parent / 'Unlocked'
        with hold_path(path) as source:
            try:
                marker = read_zone(path, source)
            except OSError:
                raise ProcessingError('無法讀取原檔的網路來源標記，未輸出 PDF。') from None
            native_path(folder).mkdir(exist_ok=True)
            with hold_path(folder, directory=True):
                with tempfile.TemporaryDirectory(prefix='.unlock-', dir=native_path(folder)) as temporary:
                    staging = Path(temporary)
                    with hold_path(staging, directory=True):
                        return self._decrypt(path, folder, staging / 'output.pdf', password, marker, cancel)

    def _decrypt(self, path, folder, temp, password, marker, cancel):
        temp_name = str(native_path(temp))
        proc = self.run(['--decrypt', str(native_path(path)), temp_name], password, cancel=cancel)
        if proc.returncode not in (0, 3):
            raise ProcessingError('解鎖失敗：PDF 無法處理或輸出位置無法寫入。')
        check_cancel(cancel)
        verified = self.run(['--check', temp_name], cancel=cancel)
        if verified.returncode not in (0, 3):
            raise ProcessingError('輸出驗證失敗，未保留不完整結果。')
        check_cancel(cancel)
        encryption = self.run(['--is-encrypted', temp_name], cancel=cancel)
        if encryption.returncode != 2 or encryption.has_stderr:
            raise ProcessingError('輸出驗證失敗，未保留不完整結果。')
        check_cancel(cancel)
        if marker is not None:
            try:
                write_zone(temp, marker)
            except OSError:
                raise ProcessingError('無法保留網路來源標記，未輸出 PDF。') from None
        for n in range(1, 100000):
            check_cancel(cancel)
            name = path.name if n == 1 else f'{path.stem} ({n}){path.suffix}'
            target = folder / name
            try:
                if os.name == 'nt':
                    os.rename(native_path(temp), native_path(target))
                else:
                    os.link(temp, target)
                    temp.unlink()
                return target, proc.returncode == 3 or verified.returncode == 3
            except FileExistsError:
                continue
        raise ProcessingError('同名輸出檔案過多。')


def discover(items: list[Path], cancel: threading.Event | None = None) -> tuple[list[Path], int]:
    found: list[Path] = []
    seen: set[str] = set()
    ignored = 0

    def add(path: Path):
        if path.suffix.lower() != '.pdf':
            return
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            found.append(path)

    for item in items:
        if cancel and cancel.is_set():
            break
        item = item.absolute()
        try:
            info = native_path(item).lstat()
            if is_link(info):
                ignored += 1
                continue
            if stat.S_ISREG(info.st_mode):
                with hold_path(item):
                    add(item)
                continue
        except OSError:
            ignored += 1
            continue

        pending = [item]
        while pending and not (cancel and cancel.is_set()):
            folder = pending.pop()
            children = []
            try:
                with hold_path(folder, directory=True):
                    entries = sorted(native_path(folder).iterdir(), key=lambda p: p.name)
                    for entry in entries:
                        if cancel and cancel.is_set():
                            break
                        child = folder / entry.name
                        try:
                            info = entry.lstat()
                        except OSError:
                            ignored += 1
                            continue
                        if is_link(info):
                            continue
                        if stat.S_ISDIR(info.st_mode) and child.name.casefold() != 'unlocked':
                            children.append(child)
                        elif stat.S_ISREG(info.st_mode):
                            add(child)
            except OSError:
                ignored += 1
            pending.extend(reversed(children))
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
            with hold_path(path):
                kind = qpdf.kind(path, cancel=cancel)
                if kind == 'plain':
                    emit('result', Result(path, 'skip', '未加密，無須解鎖'))
                    continue
                label = '無開啟密碼的加密／權限限制'
                if kind == 'locked':
                    label = '需要開啟密碼'
                    password = common
                    accepted = bool(common) and qpdf.kind(path, password, cancel=cancel) == 'encrypted'
                    reason = '共用密碼不正確' if common else '請輸入此檔案的開啟密碼'
                    while not accepted and not cancel.is_set():
                        password = ask(path, reason)
                        if password is None:
                            break
                        accepted = qpdf.kind(path, password, cancel=cancel) == 'encrypted'
                        reason = '密碼不正確，請重試或跳過'
                    if not accepted:
                        emit('result', Result(path, 'skip', label + '；已跳過'))
                        continue
                output, warning = qpdf.decrypt(path, password, cancel=cancel)
            detail = label + ('；完成（qpdf 有修復警告）' if warning else '；完成')
            emit('result', Result(path, 'success', detail, output))
        except Cancelled as exc:
            emit('result', Result(path, 'skip', str(exc)))
        except (ProcessingError, OSError) as exc:
            detail = str(exc) if isinstance(exc, ProcessingError) else '檔案或輸出資料夾無法存取。'
            emit('result', Result(path, 'fail', detail))
        finally:
            password = ''
    common = ''
