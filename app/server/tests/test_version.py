"""Tests for the version module."""

import version


def test_version_line() -> None:
    assert version.version_line() == "Bar Tab 0.0.0"


def test_constants() -> None:
    assert version.APP_NAME == "Bar Tab"
    assert version.VERSION == "0.0.0"
