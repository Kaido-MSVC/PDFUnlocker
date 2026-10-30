"""Integration tests create only disposable fixtures, never use existing PDFs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from core import Qpdf, ProcessingError, discover, process_batch


def create_fixture(folder, name='限制.pdf', password='', bits=256):
    q = Qpdf()
    target = folder / name
    # One page with text, to verify content is retained after decryption.
    stream = b'BT /F1 18 Tf 40 100 Td (PDF Unlocker fixture) Tj ET\n'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream']
    pdf = bytearray(b'%PDF-1.7\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010} 00000 n \n'.encode())
    pdf.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    base = folder / '_fixture_base.tmp'
    base.write_bytes(pdf)
    # @- is qpdf's documented argument-file stdin interface (one argument per line).
    arguments = [str(base), '--encrypt', f'--user-password={password}',
                 '--owner-password=fixture-owner', f'--bits={bits}',
                 '--print=none', '--extract=n']
    if bits == 128:
        arguments.append('--use-aes=y')
    arguments.extend(['--', str(target)])
    try:
        result = subprocess.run([q.executable, '@-'],
                                input=('\n'.join(arguments) + '\n').encode('utf-8'),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    finally:
        base.unlink(missing_ok=True)
    if result.returncode not in (0, 3):
        raise RuntimeError('Fixture creation failed')
    return target


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='PDF-測試-', dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT'))
        self.folder = Path(self.tmp.name)
        self.q = Qpdf()

    def tearDown(self):
        self.tmp.cleanup()

    def batch(self, paths, common='', answers=()):
        events = []
        replies = iter(answers)
        calls = []
        def ask(path, reason):
            calls.append(reason)
            return next(replies)
        process_batch(paths, common, threading.Event(), ask,
                      lambda e, v: events.append((e, v)), self.q)
        return [v for e, v in events if e == 'result'], calls

    def test_types_unicode_and_original_hashes(self):
        restricted = create_fixture(self.folder, '繁中 日本語 & 特殊 # [1] 😀.pdf')
        locked = create_fixture(self.folder, '開啟.pdf', ' 密碼 日本語 & # ')
        plain, _ = self.q.decrypt(restricted, '')
        self.assertEqual(self.q.kind(restricted), 'encrypted')
        self.assertEqual(self.q.kind(locked), 'locked')
        self.assertEqual(self.q.kind(plain), 'plain')
        originals = {p: hashlib.sha256(p.read_bytes()).digest() for p in (restricted, locked, plain)}
        result, calls = self.batch([restricted, locked, plain], ' 密碼 日本語 & # ')
        self.assertEqual([r.state for r in result], ['success', 'success', 'skip'])
        self.assertEqual(calls, [])
        for r in result[:2]:
            self.assertEqual(self.q.kind(r.output), 'plain')
            self.assertEqual(self.q.run(['--show-npages', str(r.output)]).stdout.strip(), b'1')
            self.assertIn(b'PDF Unlocker fixture', self.q.run(['--qdf', '--stream-data=uncompress', str(r.output), '-']).stdout)
        for path, digest in originals.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)

    def test_wrong_common_retry_then_success(self):
        path = create_fixture(self.folder, password='正解')
        result, calls = self.batch([path], '錯誤', ['再錯', '正解'])
        self.assertEqual(result[0].state, 'success')
        self.assertEqual(len(calls), 2)

    def test_individual_skip_and_no_password_file(self):
        path = create_fixture(self.folder, password='secret')
        result, _ = self.batch([path], answers=[None])
        self.assertEqual(result[0].state, 'skip')
        self.assertFalse((self.folder / 'Unlocked').exists())
        self.assertEqual(list(self.folder.iterdir()), [path])

    def test_collision_preserves_existing(self):
        path = create_fixture(self.folder)
        first, _ = self.q.decrypt(path, '')
        first_bytes = first.read_bytes()
        second, _ = self.q.decrypt(path, '')
        self.assertNotEqual(first, second)
        self.assertEqual(second.name, '限制 (2).pdf')
        self.assertEqual(first.read_bytes(), first_bytes)
        self.assertFalse(list(first.parent.glob('.unlock-*')))

    def test_corrupt_and_missing_continue(self):
        broken = self.folder / '損壞.pdf'
        broken.write_bytes(b'not a pdf')
        valid = create_fixture(self.folder)
        result, _ = self.batch([broken, self.folder / 'missing.pdf', valid])
        self.assertEqual([r.state for r in result], ['fail', 'fail', 'success'])

    def test_recursive_deduplicate_exclude_output(self):
        path = create_fixture(self.folder)
        self.q.decrypt(path, '')
        sub = self.folder / '子資料夾'
        sub.mkdir()
        other = create_fixture(sub, '大寫.PDF')
        files, unreadable = discover([self.folder, path])
        self.assertEqual(set(files), {path, other})
        self.assertEqual(unreadable, 0)

    def test_cancel_remaining_finishes_current(self):
        paths = [create_fixture(self.folder, f'{n}.pdf') for n in range(3)]
        cancel = threading.Event()
        results = []
        def emit(event, value):
            if event == 'result':
                results.append(value)
                cancel.set()
        process_batch(paths, '', cancel, lambda *_: None, emit, self.q)
        self.assertEqual([r.state for r in results], ['success', 'skip', 'skip'])

    def test_cancel_during_prompt(self):
        paths = [create_fixture(self.folder, f'{n}.pdf', 'secret') for n in range(2)]
        cancel = threading.Event()
        results = []
        def ask(*_):
            cancel.set()
            return None
        process_batch(paths, '', cancel, ask, lambda e, v: results.append(v) if e == 'result' else None, self.q)
        self.assertEqual([r.state for r in results], ['skip', 'skip'])

    def test_password_only_in_pipe_and_no_shell(self):
        fake = subprocess.CompletedProcess([], 0, b'', b'')
        with patch('core.subprocess.run', return_value=fake) as run:
            self.q.run(['--requires-password', str(self.folder / 'input.pdf')], '測試 Secret #')
        args, kwargs = run.call_args
        self.assertNotIn('測試 Secret #', ' '.join(args[0]))
        self.assertIn('--password-file=-', args[0])
        self.assertEqual(kwargs['input'], '測試 Secret #\n'.encode())
        self.assertFalse(kwargs['shell'])

    def test_timeout_is_sanitized(self):
        with patch('core.subprocess.run', side_effect=subprocess.TimeoutExpired(['qpdf'], 300, stderr=b'SECRET')):
            with self.assertRaises(ProcessingError) as caught:
                self.q.run(['--check', 'test.pdf'], 'SECRET')
        self.assertNotIn('SECRET', str(caught.exception))

    def test_output_failure_cleans_temp(self):
        path = create_fixture(self.folder)
        fake = subprocess.CompletedProcess([], 2, b'', b'SECRET')
        with patch.object(self.q, 'run', return_value=fake):
            with self.assertRaises(ProcessingError):
                self.q.decrypt(path, '')
        self.assertEqual(list((self.folder / 'Unlocked').iterdir()), [])

    def test_bad_password_characters(self):
        for password in ('a\nb', 'a\rb', 'a\0b'):
            with self.assertRaises(ProcessingError):
                self.q.run([], password)

    def test_128_bit_encryption(self):
        path = create_fixture(self.folder, password='legacy', bits=128)
        result, _ = self.batch([path], 'legacy')
        self.assertEqual(result[0].state, 'success')

    def test_owner_password_accepted(self):
        path = create_fixture(self.folder, password='user-password')
        result, calls = self.batch([path], 'fixture-owner')
        self.assertEqual(result[0].state, 'success')
        self.assertEqual(calls, [])

    def test_output_folder_is_file(self):
        path = create_fixture(self.folder)
        blocked = self.folder / 'Unlocked'
        blocked.write_bytes(b'keep this existing file')
        result, _ = self.batch([path])
        self.assertEqual(result[0].state, 'fail')
        self.assertEqual(blocked.read_bytes(), b'keep this existing file')

    def test_missing_qpdf(self):
        with patch('core.bundled_qpdf', return_value=self.folder / 'missing-qpdf.exe'), patch('core.shutil.which', return_value=None):
            with self.assertRaises(ProcessingError):
                Qpdf()

    def test_failed_verification_never_publishes(self):
        path = create_fixture(self.folder)
        good = subprocess.CompletedProcess([], 0, b'', b'')
        bad = subprocess.CompletedProcess([], 2, b'', b'')
        with patch.object(self.q, 'run', side_effect=[good, bad, bad]):
            with self.assertRaises(ProcessingError):
                self.q.decrypt(path, '')
        self.assertEqual(list((self.folder / 'Unlocked').iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
