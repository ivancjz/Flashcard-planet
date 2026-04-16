from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from pathlib import Path


def _parse_args(argv: list[str]) -> tuple[list[str], int]:
    targets: list[str] = []
    verbosity = 1
    for arg in argv:
        if arg == "-v":
            verbosity = 2
            continue
        if arg.startswith("--tb="):
            continue
        if arg.startswith("-q"):
            verbosity = 0
            continue
        if arg.startswith("-"):
            continue
        targets.append(arg)
    return targets or ["tests"], verbosity


def _load_module_from_path(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plain_suite_from_file(path: Path) -> unittest.TestSuite:
    """Build a TestSuite from plain (non-TestCase) test classes in a file."""
    suite = unittest.TestSuite()
    try:
        mod = _load_module_from_path(path)
    except Exception as exc:
        # Surface import errors as a test failure
        class _ImportErrorTest(unittest.TestCase):
            def runTest(self):
                raise exc
        _ImportErrorTest.__name__ = f"import_{path.stem}"
        suite.addTest(_ImportErrorTest())
        return suite

    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if not name.startswith("Test"):
            continue
        if issubclass(obj, unittest.TestCase):
            continue  # already picked up by unittest discovery
        # Wrap each test method in a TestCase
        for method_name in sorted(dir(obj)):
            if not method_name.startswith("test"):
                continue
            instance = obj()
            method = getattr(instance, method_name)
            if not callable(method):
                continue

            class _WrappedTest(unittest.TestCase):
                pass

            _WrappedTest.__name__ = f"{name}.{method_name}"
            _WrappedTest.__qualname__ = f"{name}.{method_name}"

            # Capture via default arg to avoid closure issues
            def make_test(m=method):
                def test_body(self):
                    m()
                return test_body

            setattr(_WrappedTest, method_name, make_test())
            suite.addTest(_WrappedTest(method_name))

    return suite


def _collect_test_files(target: str) -> list[Path]:
    path = Path(target)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob("test*.py"))
    return []


def _suite_for_target(target: str) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    files = _collect_test_files(target)
    for file in files:
        # Standard unittest discovery for TestCase subclasses
        std = unittest.defaultTestLoader.discover(
            str(file.parent), pattern=file.name
        )
        suite.addTest(std)
        # Plain class discovery
        suite.addTest(_plain_suite_from_file(file))
    if not files:
        # Fallback
        suite.addTest(
            unittest.defaultTestLoader.discover("tests", pattern="test*.py")
        )
    return suite


def main(argv: list[str] | None = None) -> int:
    targets, verbosity = _parse_args(list(sys.argv[1:] if argv is None else argv))
    suite = unittest.TestSuite(_suite_for_target(target) for target in targets)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
