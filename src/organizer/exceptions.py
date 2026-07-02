"""Organizer-specific exception types."""

from __future__ import annotations


class OrganizerError(Exception):
    """Base error for organizer workflows."""


class AnalyzerReportMissingError(OrganizerError):
    """Raised when analyzer output report cannot be found."""


class AnalyzerReportFormatError(OrganizerError):
    """Raised when analyzer output report has invalid structure."""
