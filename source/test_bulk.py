"""100 disposable PDFs: mixed success/failure/skip and unchanged input hashes."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time

from core import Qpdf, process_batch
from test_core import create_fixture


def run():
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='bulk-', dir=os.environ.get('PDF_UNLOCKER_TEST_ROOT')) as temporary:
        folder = Path(temporary)
        restricted = create_fixture(folder, 'template.pdf')
        qpdf = Qpdf()
        plain, _ = qpdf.decrypt(restricted, '')
        paths = []
        for number in range(100):
            target = folder / f'批次_日本語 & [{number:03}].pdf'
            if number % 10 == 0:
                target.write_bytes(b'broken fixture')
            else:
                shutil.copyfile(plain if number % 10 == 1 else restricted, target)
            paths.append(target)
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in paths}
        results = []
        current = []
        def emit(event, value):
            if event == 'result':
                results.append(value)
            if event == 'current':
                current.append(value[1])
        process_batch(paths, '', threading.Event(), lambda *_: None, emit, qpdf)
        counts = Counter(r.state for r in results)
        assert counts == {'success': 80, 'fail': 10, 'skip': 10}, counts
        assert current == paths
        assert all(hashlib.sha256(p.read_bytes()).digest() == before[p] for p in paths)
        assert all(qpdf.kind(r.output) == 'plain' for r in results if r.output)
        print(json.dumps({'ok': True, 'files': 100, 'counts': dict(counts),
                          'seconds': round(time.monotonic() - start, 2),
                          'input_order_preserved': True, 'original_hashes_unchanged': True}, indent=2))


if __name__ == '__main__':
    run()
