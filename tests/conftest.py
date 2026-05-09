"""Shared pytest fixtures for SmartFork v2 tests."""

import pytest
from pathlib import Path

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"

# Fixture directories will be populated by individual test modules
