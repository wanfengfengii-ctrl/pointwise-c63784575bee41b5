"""Run this project's full unittest suite and the linked transfer check."""
import sys
import unittest


def main():
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    transfer_ok = True
    try:
        from transfer_check import verify as verify_transfer
        checked = verify_transfer()
        print(f'TRANSFER CHECK samples={len(checked)} result=PASS')
    except Exception as exc:  # noqa: BLE001 - report any verification failure
        transfer_ok = False
        print(f'TRANSFER CHECK result=FAIL {type(exc).__name__}: {exc}', file=sys.stderr)
    successful = result.testsRun > 0 and result.wasSuccessful()
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'result={"PASS" if successful else "FAIL"}')
    if not successful:
        return 1
    return 0 if transfer_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
