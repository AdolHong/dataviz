"""Process boundaries and transaction failures, with synthetic local databases."""
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

from dataviz.execution import action_journal
from dataviz.execution.action_journal import ActionJournal


def _claim_in_process(path):
    journal = ActionJournal(Path(path))
    receipt, claimed = journal.claim('scope', 'same-id', 'same-payload', deadline=time.time() + 60)
    if claimed:
        journal.finish('scope', 'same-id', {'status': 'succeeded', 'invalidations': ['source:labels']},
                       dashboard_id='dashboard')
    return claimed


def test_independent_processes_claim_once_and_invalidate_once(tmp_path):
    path = tmp_path / 'receipts.sqlite'
    ActionJournal(path)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
        results = list(pool.map(_claim_in_process, [str(path)] * 16))
    assert sum(results) == 1
    assert ActionJournal(path).get('scope', 'same-id')['status'] == 'succeeded'
    with sqlite3.connect(path) as connection:
        assert connection.execute('select version from source_epochs').fetchall() == [(1,)]


def test_write_committed_before_process_exit_is_unknown_not_replayed(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    code = '''
import os, sqlite3, sys, time
from pathlib import Path
from dataviz.execution.action_journal import ActionJournal
root=Path(sys.argv[1])
journal=ActionJournal(root/'receipts.sqlite')
_, claimed=journal.claim('scope','write','payload',deadline=time.time()+60)
assert claimed
with sqlite3.connect(root/'business.sqlite') as connection:
    connection.execute('create table labels(item integer)')
    connection.execute('insert into labels values (42)')
os._exit(23)
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], cwd=root,
                            env={**os.environ, 'PYTHONPATH': str(root / 'src')}, timeout=15)
    assert result.returncode == 23
    journal = ActionJournal(tmp_path / 'receipts.sqlite')
    assert journal.get('scope', 'write')['status'] == 'running'
    future = time.time() + 120
    monkeypatch.setattr(action_journal.time, 'time', lambda: future)
    receipt, claimed = journal.claim('scope', 'write', 'payload', deadline=future + 60)
    assert not claimed
    assert receipt['status'] == 'unknown'
    assert receipt['error']['code'] == 'action_outcome_unknown'
    with sqlite3.connect(tmp_path / 'business.sqlite') as connection:
        assert connection.execute('select item from labels').fetchall() == [(42,)]


def test_failed_receipt_serialization_rolls_back_mutation_epoch(tmp_path):
    path = tmp_path / 'receipts.sqlite'
    journal = ActionJournal(path)
    journal.claim('scope', 'write', 'payload', deadline=time.time() + 60)
    with pytest.raises(ValueError):
        journal.finish('scope', 'write', {
            'status': 'succeeded', 'invalidations': ['source:labels'], 'result': float('nan'),
        }, dashboard_id='dashboard')
    assert journal.get('scope', 'write')['status'] == 'running'
    with sqlite3.connect(path) as connection:
        assert connection.execute('select * from source_epochs').fetchall() == []
