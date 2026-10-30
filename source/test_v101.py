"""Targeted scan fault and worker-to-GUI event regression tests (no Tk window)."""
import os
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app
from core import Result, discover


class DiscoveryFaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_file_errors_keep_prior_and_later_results(self):
        for operation in ('is_symlink', 'resolve', 'absolute'):
            for error_type in (PermissionError, FileNotFoundError):
                with self.subTest(operation=operation, error=error_type):
                    paths = [self.root / name for name in ('a.pdf', 'b.pdf', 'c.PDF')]
                    for path in paths:
                        path.touch()
                    original = getattr(Path, operation)

                    def fail_one(path, *args, **kwargs):
                        if path == paths[1]:
                            raise error_type('injected')
                        return original(path, *args, **kwargs)

                    with patch.object(Path, operation, fail_one):
                        for items in ([self.root], paths):
                            found, ignored = discover(items)
                            self.assertEqual(found, [paths[0], paths[2]])
                            self.assertEqual(ignored, 1)

    def test_directory_errors_prune_only_bad_child(self):
        for operation in ('is_symlink', 'is_junction'):
            with self.subTest(operation=operation):
                for name in ('bad', 'good', 'Unlocked'):
                    folder = self.root / name
                    folder.mkdir(exist_ok=True)
                    (folder / 'inside.pdf').touch()
                top = self.root / 'top.pdf'
                top.touch()
                original = getattr(Path, operation)

                def fail_one(path, *args, **kwargs):
                    if path == self.root / 'bad':
                        raise PermissionError('injected')
                    return original(path, *args, **kwargs)

                with patch.object(Path, operation, fail_one):
                    found, ignored = discover([self.root, top])
                self.assertEqual(found, [top, self.root / 'good' / 'inside.pdf'])
                self.assertEqual(ignored, 1)

    def test_top_level_error_continues_to_next_input(self):
        bad, good = self.root / 'bad', self.root / 'good.pdf'
        good.touch()
        original = Path.is_dir

        def fail_one(path):
            if path == bad:
                raise PermissionError('injected')
            return original(path)

        with patch.object(Path, 'is_dir', fail_one):
            self.assertEqual(discover([bad, good]), ([good], 1))

    def test_walk_error_and_cancellation(self):
        good = self.root / 'good.pdf'
        good.touch()

        def walk(root, **kwargs):
            kwargs['onerror'](PermissionError('injected'))
            yield str(root), [], [good.name]

        with patch('core.os.walk', walk):
            self.assertEqual(discover([self.root]), ([good], 1))
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(discover([self.root], cancel), ([], 0))


class FakeTree:
    def __init__(self, paths):
        self.rows = {n: (p.name, '待處理', str(p.parent)) for n, p in enumerate(paths)}

    def item(self, row, option=None, **kwargs):
        if 'values' in kwargs:
            self.rows[row] = kwargs['values']
        return self.rows[row] if option == 'values' else {'values': self.rows[row]}


class InlineThread:
    def __init__(self, target, args=(), **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class WorkerOutcomeTests(unittest.TestCase):
    def run_batch(self, outcome, cancel_on_error=False):
        paths = [Path(f'{n}.pdf') for n in range(3)]
        gui = SimpleNamespace(
            paths=paths, row_by_path={p: n for n, p in enumerate(paths)},
            tree=FakeTree(paths), events=queue.Queue(), cancel_event=threading.Event(),
            password=Mock(), progress=Mock(), status=Mock(), counts=dict(success=0, fail=0, skip=0),
            update_counts=Mock(), after=Mock(), poll=Mock(), set_busy=Mock(), closing=False,
        )
        gui.password.get.return_value = ''

        def process(paths, secret, cancel, ask, emit, engine):
            emit('current', (1, paths[0]))
            emit('result', Result(paths[0], 'success', '完成'))
            if outcome == 'error':
                emit('current', (2, paths[1]))
                if cancel_on_error:
                    cancel.set()
                raise RuntimeError('secret must not appear in GUI')
            if outcome == 'cancelled':
                cancel.set()
            for path in paths[1:]:
                emit('result', Result(path, 'skip', '取消後跳過' if cancel.is_set() else '未加密'))

        with patch.object(app, 'Qpdf'), patch.object(app, 'process_batch', process), patch.object(app.threading, 'Thread', InlineThread):
            app.App.start(gui)
        events = list(gui.events.queue)
        self.assertEqual(events[-1], ('done', outcome))
        # Keep poll deterministic, including its 20 ms bound.
        with patch.object(app.time, 'monotonic', return_value=0), patch.object(app.messagebox, 'showerror') as dialog:
            app.App.poll(gui)
        gui.set_busy.assert_called_with(False)
        self.assertEqual(dialog.call_count, int(outcome == 'error'))
        return gui

    def test_normal_completion(self):
        gui = self.run_batch('completed')
        self.assertIn('批次完成', gui.status.configure.call_args.kwargs['text'])
        self.assertEqual(gui.counts, dict(success=1, fail=0, skip=2))

    def test_cancellation(self):
        gui = self.run_batch('cancelled')
        self.assertIn('已取消', gui.status.configure.call_args.kwargs['text'])
        self.assertEqual(gui.counts, dict(success=1, fail=0, skip=2))

    def test_exception_preserves_results_and_marks_unfinished(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                gui = self.run_batch('error', cancelled)
                texts = [call.kwargs['text'] for call in gui.status.configure.call_args_list]
                self.assertIn('批次異常中止', texts[-1])
                self.assertFalse(any('批次完成' in text for text in texts))
                self.assertFalse(any('secret' in text for text in texts))
                self.assertEqual([v[1] for v in gui.tree.rows.values()], ['成功', '未完成', '未處理'])
                self.assertEqual(gui.counts, dict(success=1, fail=0, skip=0))
                gui.progress.set.assert_called_with(1 / 3)

    def test_failure_before_first_file_marks_all_pending(self):
        # Qpdf construction in start succeeds, then the worker fails immediately.
        original = app.process_batch
        try:
            def fail(*args):
                raise RuntimeError('injected')
            app.process_batch = fail
            paths = [Path('pending.pdf')]
            gui = SimpleNamespace(paths=paths, row_by_path={paths[0]: 0}, tree=FakeTree(paths),
                                  events=queue.Queue(), cancel_event=threading.Event(), password=Mock(),
                                  progress=Mock(), status=Mock(), counts=dict(success=0, fail=0, skip=0),
                                  update_counts=Mock(), set_busy=Mock(), after=Mock(), poll=Mock(), closing=False)
            gui.password.get.return_value = ''
            with patch.object(app, 'Qpdf'), patch.object(app.threading, 'Thread', InlineThread):
                app.App.start(gui)
            with patch.object(app.time, 'monotonic', return_value=0), patch.object(app.messagebox, 'showerror'):
                app.App.poll(gui)
            self.assertEqual(gui.tree.rows[0][1], '未處理')
            self.assertIn('1 個', gui.status.configure.call_args.kwargs['text'])
            self.assertEqual(sum(gui.counts.values()), 0)
        finally:
            app.process_batch = original


if __name__ == '__main__':
    unittest.main(verbosity=2)
