"""Run an actual GUI + qpdf workflow in source or frozen executable."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import traceback


def run(report: Path):
    from app import App
    from test_core import create_fixture
    from core import Qpdf
    import customtkinter as ctk
    import tkinter as tk

    data = {'ok': False, 'frozen': bool(getattr(__import__('sys'), 'frozen', False))}
    app = None
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='GUI-驗證-', dir=report.parent) as temporary:
            folder = Path(temporary)
            restricted = create_fixture(folder, '繁中 日本語 & [#] 😀.pdf')
            locked = create_fixture(folder, '開啟密碼.pdf', '測試密碼')
            qpdf = Qpdf()
            from core import bundled_qpdf
            assert Path(qpdf.executable) == bundled_qpdf()
            data.update(qpdf_executable=qpdf.executable, path=__import__('os').environ.get('PATH'),
                        qpdf_version='12.4.2')
            plain, _ = qpdf.decrypt(restricted, '')
            broken = folder / '損壞.pdf'
            broken.write_bytes(b'not a pdf')
            hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (restricted, locked, plain, broken)}
            ctk.set_appearance_mode('dark')
            app = App()
            errors = []
            app.report_callback_exception = lambda *exc: errors.append(str(exc[1]))
            ticks = [0]
            def heartbeat():
                ticks[0] += 1
                app.after(15, heartbeat)
            app.after(15, heartbeat)
            app.add_paths([restricted, locked, plain, broken])
            app.password.insert(0, 'wrong-common')
            app.start_button.invoke()
            assert app.password.get() == ''
            deadline = time.monotonic() + 30
            dialog_tested = False
            while app.running and time.monotonic() < deadline:
                app.update()
                if app.dialog is not None:
                    app.dialog.entry.insert(0, '測試密碼')
                    app.dialog.finish(app.dialog.entry.get())
                    dialog_tested = True
                time.sleep(.01)
            assert not app.running, 'GUI worker did not finish'
            assert not errors, errors
            assert app.counts == {'success': 2, 'fail': 1, 'skip': 1}, app.counts
            assert '批次完成' in app.status.cget('text')
            assert dialog_tested
            assert ticks[0] > 3, 'GUI event loop did not tick'
            for path, digest in hashes.items():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            app.update_idletasks()
            assert app.start_button.winfo_ismapped()
            assert app.start_button.winfo_rootx() + app.start_button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            first_counts = app.counts.copy()
            app.geometry('860x620')
            app.update()
            assert app.start_button.winfo_ismapped()
            assert app.start_button.winfo_rootx() + app.start_button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            assert app.start_button.winfo_rooty() + app.start_button.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            # Cancel while the individual password dialog is open.
            app.clear_button.invoke()
            app.add_paths([locked, restricted])
            app.start_button.invoke()
            deadline = time.monotonic() + 30
            cancelled_dialog = False
            while app.running and time.monotonic() < deadline:
                app.update()
                if app.dialog is not None:
                    app.dialog.cancel_all()
                    cancelled_dialog = True
                time.sleep(.01)
            assert not app.running
            assert cancelled_dialog
            assert app.counts == {'success': 0, 'fail': 0, 'skip': 2}, app.counts
            assert '已取消' in app.status.cget('text')
            assert not errors, errors
            # Exercise the asynchronous folder selector's scan path without a native file dialog.
            app.clear_button.invoke()
            app.scan([folder])
            deadline = time.monotonic() + 30
            while app.running and time.monotonic() < deadline:
                app.update()
                time.sleep(.01)
            assert not app.running
            assert len(app.paths) == 3, app.paths
            # Real worker + Tk polling: preserve completed rows on an unexpected exception.
            from unittest.mock import patch
            from core import Result
            app.clear()
            app.add_paths([restricted, locked, broken])
            def fail_batch(paths, secret, cancel, ask, emit, engine):
                emit('result', Result(paths[0], 'skip', '測試已處理結果'))
                emit('current', (2, paths[1]))
                raise RuntimeError('injected test error')
            with patch('app.process_batch', fail_batch), patch('app.messagebox.showerror') as error_dialog:
                app.start()
                deadline = time.monotonic() + 30
                while app.running and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.01)
                assert not app.running
                assert '批次異常中止' in app.status.cget('text')
                assert '批次完成' not in app.status.cget('text')
                assert [app.tree.item(app.row_by_path[p], 'values')[1] for p in app.paths] == ['跳過', '未完成', '未處理']
                assert app.counts == {'success': 0, 'fail': 0, 'skip': 1}
                assert abs(app.progress.get() - 1 / 3) < .001
                error_dialog.assert_called_once()
            assert not errors, errors
            data.update(ok=True, counts=first_counts, gui_heartbeat_ticks=ticks[0],
                        individual_password_dialog=True, original_hashes_unchanged=True,
                        cancel_dialog_counts={'success': 0, 'fail': 0, 'skip': 2}, async_folder_scan=True,
                        abnormal_worker_status=True, unfinished_rows_marked=True,
                        minimum_window=[app.winfo_width(), app.winfo_height()],
                        window_icon_configured=app._iconbitmap_method_called)
    except BaseException:
        data['error'] = traceback.format_exc()
    finally:
        if app:
            app.destroy()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    if not data['ok']:
        raise SystemExit(1)
