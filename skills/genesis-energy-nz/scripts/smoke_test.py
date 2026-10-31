#!/usr/bin/env python3
"""Run meaningful synthetic source checks, never a live personal-data probe."""
import sys
import unittest
from unittest.mock import patch
from test_contract import SourceTests


def main():
    with patch("socket.create_connection", side_effect=AssertionError("Network forbidden in smoke tests")):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SourceTests)
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    if not result.wasSuccessful():
        print("[FAIL] fixture Genesis synthetic behaviour")
        return 1
    print("[PASS] fixture synthetic electricity/gas parsing, precision, gaps and DST")
    print("[PASS] contract optional gas isolation, fixed destinations, bounded chunks and safe errors")
    print("[SKIP] live Genesis verification requires owner-authorised personal credentials; never run in CI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
