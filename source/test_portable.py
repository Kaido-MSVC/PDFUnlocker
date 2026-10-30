"""Only executable selection changes; real processing is covered by test_core."""
from pathlib import Path
import tempfile
import os
import subprocess
import unittest
from unittest.mock import patch
import core


class PortableTests(unittest.TestCase):
    def test_bundle_beats_path(self):
        with patch('core.shutil.which', side_effect=AssertionError('PATH consulted')):
            self.assertEqual(core.Qpdf().executable, str(core.bundled_qpdf()))

    def test_explicit_override_retained(self):
        self.assertEqual(core.Qpdf('explicit-qpdf.exe').executable, 'explicit-qpdf.exe')

    def test_missing_bundle_uses_system(self):
        with patch('core.bundled_qpdf', return_value=Path('absent/qpdf.exe')), patch('core.shutil.which', return_value='system-qpdf.exe'):
            self.assertEqual(core.Qpdf().executable, 'system-qpdf.exe')

    def test_frozen_resource_location(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT')) as folder, patch.object(core.sys, '_MEIPASS', folder, create=True):
            self.assertEqual(core.bundled_qpdf(), Path(folder) / 'tools/qpdf/qpdf.exe')

    def test_bundle_runs_without_path(self):
        with patch.dict('os.environ', {'PATH': ''}):
            result = subprocess.run([core.Qpdf().executable, '--version'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b'12.4.2', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
