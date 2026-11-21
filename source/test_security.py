"""只使用受控暫存資料驗證 Windows 安全修正。"""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import core
from core import Cancelled, ProcessingError, Qpdf, QpdfResult, discover, process_batch
from test_core import create_fixture
from windows_files import hold_path, read_zone


def zone(path):
    return Path(f'{path}:Zone.Identifier')


@unittest.skipUnless(os.name == 'nt', '需要 Windows 檔案系統')
class WindowsSecurityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.engine = Qpdf()
        self.marker = b'[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://example.invalid/a\r\n'

    def test_motw_with_and_without_marker(self):
        marked = create_fixture(self.root, '標記 測試.pdf', '密碼')
        unmarked = create_fixture(self.root, '一般 PDF.pdf')
        zone(marked).write_bytes(self.marker)
        original = marked.read_bytes()
        output, _ = self.engine.decrypt(marked, '密碼')
        second, _ = self.engine.decrypt(unmarked, '')
        self.assertEqual(zone(output).read_bytes(), self.marker)
        self.assertEqual(zone(marked).read_bytes(), self.marker)
        self.assertEqual(marked.read_bytes(), original)
        self.assertEqual(self.engine.kind(output), 'plain')
        self.assertEqual(self.engine.kind(second), 'plain')
        with self.assertRaises(FileNotFoundError):
            zone(second).read_bytes()

    def test_marker_write_failure_never_publishes(self):
        path = create_fixture(self.root)
        original = path.read_bytes()
        zone(path).write_bytes(self.marker)
        with patch('core.write_zone', side_effect=PermissionError('blocked')):
            with self.assertRaisesRegex(ProcessingError, '無法保留'):
                self.engine.decrypt(path, '')
        self.assertEqual(list((self.root / 'Unlocked').iterdir()), [])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(zone(path).read_bytes(), self.marker)

    def test_marker_volume_without_named_streams(self):
        path = create_fixture(self.root)
        with hold_path(path) as handle, patch('windows_files._get_volume', return_value=True):
            self.assertIsNone(read_zone(path, handle))

    def test_motw_read_access_error_never_publishes(self):
        path = create_fixture(self.root)
        with patch('core.read_zone', side_effect=PermissionError('blocked')):
            with self.assertRaisesRegex(ProcessingError, '無法讀取'):
                self.engine.decrypt(path, '')
        self.assertFalse((self.root / 'Unlocked').exists())

    def test_cancel_after_decrypt_skips_both_verifications(self):
        path = create_fixture(self.root)
        cancel = threading.Event()
        run = self.engine.run
        calls = []

        def cancel_after_first_phase(args, *positional, **keywords):
            calls.append(args[0])
            result = run(args, *positional, **keywords)
            cancel.set()
            return result

        with patch.object(self.engine, 'run', side_effect=cancel_after_first_phase):
            with self.assertRaises(Cancelled):
                self.engine.decrypt(path, '', cancel=cancel)
        self.assertEqual(calls, ['--decrypt'])
        self.assertEqual(list((self.root / 'Unlocked').iterdir()), [])

    def test_junctions_at_selected_root_nested_and_output(self):
        from _winapi import CreateJunction

        outside = self.root / 'outside'
        inside = self.root / 'picked'
        for folder in (outside, inside):
            folder.mkdir()
        external_pdf = create_fixture(outside, '外部.pdf')
        selected = create_fixture(inside, '選取.pdf')
        nested = inside / 'nested-junction'
        output = inside / 'Unlocked'
        for junction in (nested, output):
            CreateJunction(str(outside), str(junction))
            self.assertTrue(junction.is_junction())
        self.assertEqual(discover([inside, nested, nested / external_pdf.name]), ([selected], 2))
        with self.assertRaises(OSError):
            self.engine.decrypt(selected, '')
        self.assertEqual(list(outside.iterdir()), [external_pdf])

    def test_symbolic_links_at_selected_root_file_and_output(self):
        outside = self.root / 'outside'
        inside = self.root / 'picked'
        for folder in (outside, inside):
            folder.mkdir()
        external_pdf = create_fixture(outside)
        selected = create_fixture(inside)
        root_link = self.root / 'link'
        file_link = inside / 'linked.pdf'
        output_link = inside / 'Unlocked'
        try:
            root_link.symlink_to(outside, target_is_directory=True)
            file_link.symlink_to(external_pdf)
            output_link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if exc.winerror in (5, 1314):
                self.skipTest(f'Windows 不允許建立符號連結（WinError {exc.winerror}）')
            raise
        self.assertEqual(discover([inside, root_link, file_link]), ([selected], 2))
        with self.assertRaises(OSError):
            self.engine.decrypt(selected, '')
        self.assertEqual(list(outside.iterdir()), [external_pdf])

    def test_path_components_cannot_move_during_qpdf_write(self):
        picked = self.root / 'picked'
        picked.mkdir()
        path = create_fixture(picked)
        original = path.read_bytes()
        output_folder = picked / 'Unlocked'
        run = self.engine.run
        checked = []

        def check_windows_sharing(args, *positional, **keywords):
            if args[0] == '--decrypt':
                staging = Path(args[-1]).parent
                for item in (path, picked, output_folder, staging):
                    with self.assertRaises(PermissionError) as error:
                        item.rename(item.with_name(item.name + '-moved'))
                    self.assertIn(error.exception.winerror, (5, 32))
                    checked.append(item.name)
            return run(args, *positional, **keywords)

        with patch.object(self.engine, 'run', side_effect=check_windows_sharing):
            output, _ = self.engine.decrypt(path, '')
        self.assertEqual(len(checked), 4)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(output_folder.iterdir()), [output])

    def test_permission_denied_by_windows_acl(self):
        path = create_fixture(self.root)
        output_folder = self.root / 'Unlocked'
        output_folder.mkdir()
        system = Path(os.environ['SystemRoot']) / 'System32'
        identity = subprocess.check_output([str(system / 'whoami.exe'), '/user', '/fo', 'csv', '/nh'],
                                           timeout=10)
        sid = re.search(rb'S-1-[0-9-]+', identity).group().decode('ascii')
        command = [str(system / 'icacls.exe'), str(output_folder)]
        subprocess.run([*command, '/deny', f'*{sid}:(AD,WD)'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        try:
            with self.assertRaises(PermissionError):
                self.engine.decrypt(path, '')
            results = []
            process_batch([path], '', threading.Event(), lambda *_: None,
                          lambda event, value: results.append(value) if event == 'result' else None,
                          self.engine)
            self.assertEqual(results[0].state, 'fail')
            self.assertEqual(list(output_folder.iterdir()), [])
        finally:
            subprocess.run([*command, '/remove:d', f'*{sid}'], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)

    def test_windows_long_path_with_unicode_and_spaces(self):
        folder = self.root
        while len(str(folder)) < 265:
            folder /= '繁中 測試路徑' * 3
            folder.mkdir()
        path = create_fixture(folder, '加密 檔案.pdf', '正確密碼')
        zone(path).write_bytes(self.marker)
        self.assertGreater(len(str(path)), 260)
        self.assertEqual(discover([self.root]), ([path], 0))
        output, _ = self.engine.decrypt(path, '正確密碼')
        self.assertEqual(self.engine.kind(output), 'plain')
        self.assertEqual(zone(output).read_bytes(), self.marker)


class SubprocessSecurityTests(unittest.TestCase):
    def run_child(self, script, *, cancel=None, timeout=5):
        engine = Qpdf()
        start = subprocess.Popen
        children = []

        def launch(_command, **kwargs):
            child = start([sys.executable, '-I', '-S', '-c', script], **kwargs)
            children.append(child)
            return child

        try:
            with patch('core.subprocess.Popen', side_effect=launch), patch('core.TIMEOUT', timeout):
                return engine.run(['--check', 'fixture.pdf'], 'dummy-secret', cancel=cancel)
        finally:
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll())
            self.assertTrue(children[0].stdin.closed)
            self.assertTrue(children[0].stderr.closed)

    def test_large_stdout_and_stderr_are_drained(self):
        result = self.run_child(
            'import sys; secret = sys.stdin.buffer.readline(); '
            'sys.stderr.buffer.write(secret * 200000); sys.stdout.buffer.write(b"x" * 2000000)')
        self.assertEqual(result, QpdfResult(0, True))
        self.assertNotIn('dummy-secret', repr(result))

    def test_real_child_timeout_and_cleanup(self):
        with self.assertRaisesRegex(ProcessingError, '逾時') as error:
            self.run_child('import sys,time; sys.stderr.write(sys.stdin.readline()); time.sleep(8)',
                           timeout=0.35)
        self.assertNotIn('dummy-secret', str(error.exception))

    def test_real_child_cancellation_and_cleanup(self):
        cancel = threading.Event()
        timer = threading.Timer(0.5, cancel.set)
        timer.start()
        try:
            with self.assertRaises(Cancelled):
                self.run_child('import time; time.sleep(8)', cancel=cancel)
        finally:
            timer.cancel()
            timer.join()

    def test_abnormal_exit_uses_only_status_code(self):
        with self.assertRaisesRegex(ProcessingError, '代碼 17') as error:
            self.run_child('import sys; sys.stderr.write(sys.stdin.readline()); sys.exit(17)')
        self.assertNotIn('dummy-secret', str(error.exception))
