"""驗證 qpdf 執行檔只取自預期位置。"""
from pathlib import Path
import tempfile
import os
import subprocess
import unittest
from unittest.mock import patch
import core


class PortableTests(unittest.TestCase):
    def test_bundle_exists(self):
        self.assertEqual(core.Qpdf().executable, str(core.bundled_qpdf()))

    def test_explicit_absolute_override(self):
        executable = str(core.bundled_qpdf())
        self.assertEqual(core.Qpdf(executable).executable, executable)

    def test_invalid_explicit_override(self):
        for path in ('qpdf.exe', str(core.bundled_qpdf().with_name('absent.exe')),
                     str(core.bundled_qpdf().parent)):
            with self.subTest(path=path), self.assertRaises(core.ProcessingError):
                core.Qpdf(path)

    def test_missing_bundle_rejects_path_and_cwd(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT')) as temp:
            folder = Path(temp)
            elsewhere = folder / 'path'
            elsewhere.mkdir()
            # 純文字標記只用於驗證搜尋行為。
            (folder / 'qpdf.exe').write_text('cwd', encoding='ascii')
            (elsewhere / 'qpdf.exe').write_text('path', encoding='ascii')
            before = Path.cwd()
            try:
                os.chdir(folder)
                with (patch.dict(os.environ, PATH=str(elsewhere)),
                      patch.object(core, 'bundled_qpdf', return_value=folder / 'absent' / 'qpdf.exe'),
                      patch('core.subprocess.Popen') as start):
                    with self.assertRaisesRegex(core.ProcessingError, '完整解壓'):
                        core.Qpdf()
                    start.assert_not_called()
            finally:
                os.chdir(before)

    def test_frozen_resource_location(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT')) as folder:
            root = Path(folder)
            internal = root / '_internal'
            with (patch.object(core.sys, 'frozen', True, create=True),
                  patch.object(core.sys, 'executable', str(root / 'PDFUnlocker.exe')),
                  patch.object(core.sys, '_MEIPASS', str(internal), create=True)):
                self.assertEqual(core.bundled_qpdf(), internal / 'tools/qpdf/qpdf.exe')
                with self.assertRaises(core.ProcessingError):
                    core.Qpdf(str(root / 'external.exe'))
                with patch.object(core.sys, '_MEIPASS', str(root / 'elsewhere')):
                    with self.assertRaises(core.ProcessingError):
                        core.bundled_qpdf()

    def test_bundle_runs_without_path(self):
        with patch.dict('os.environ', {'PATH': ''}):
            result = subprocess.run([core.Qpdf().executable, '--version'], capture_output=True,
                                    timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b'12.4.2', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
