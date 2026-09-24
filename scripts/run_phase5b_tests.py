from pathlib import Path
import unittest,json,sys
ROOT=Path(__file__).resolve().parents[1]
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/"tests")))
report={"tests_run":result.testsRun,"passed":result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
"failed":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped)}
(ROOT/"reports/metrics/phase5b_test_results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
sys.exit(0 if result.wasSuccessful() else 1)
