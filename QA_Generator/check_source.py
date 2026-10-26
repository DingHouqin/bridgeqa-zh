"""Run shipped-source tests, explicitly skipping unshipped historical data.

See [source quick start](START_HERE.md). No network or model calls.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ('multi_agent_v0','deletion_review_v2','quality_v3')
HISTORICAL = (
    'test_external_relations.',
    'test_scoring_review_v7.ActualFrozenRegressionTests.',
    'test_scoring_semantics_v10.ActualFrozenRawDiagnostics.',
    'test_support_contract.RequestTests.test_r3_legacy_inventory_inputs_construct_without_history_changes',
)

def flatten(suite):
    for case in suite:
        if isinstance(case,unittest.TestSuite):
            yield from flatten(case)
        else:
            yield case

def historical_skip(name):
    def skip():
        raise unittest.SkipTest('Historical frozen/runtime data is outside the source publication: '+name)
    return unittest.FunctionTestCase(skip,description=name)

def worker(group):
    suite=unittest.defaultTestLoader.discover(str(ROOT/'src'/group),pattern='test_*.py')
    selected=unittest.TestSuite()
    for case in flatten(suite):
        name=case.id()
        selected.addTest(historical_skip(name) if name.startswith(HISTORICAL) else case)
    return unittest.TextTestRunner(verbosity=1).run(selected).wasSuccessful()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',choices=GROUPS)
    args=parser.parse_args()
    if args.worker:
        raise SystemExit(0 if worker(args.worker) else 1)
    codes=[subprocess.run([sys.executable,__file__,'--worker',group],cwd=ROOT).returncode for group in GROUPS]
    raise SystemExit(0 if all(code==0 for code in codes) else 1)
