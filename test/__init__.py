"""Farcy test file."""

import farcy.handlers
import os
import unittest


class FarcyTest(unittest.TestCase):

    """Provides helpers for various FarcyTest classes."""

    def shortDescription(self):
        """Disable the short description (docstring) output."""
        return None

    def path(self, filename):
        """Return a path to the example file."""
        return os.path.join(os.path.dirname(__file__), 'examples', filename)


class Flake8Test(FarcyTest):

    """Tests for the Flake8 Handler."""

    def setUp(self):
        """Set up helpers used for each test case."""
        self.process = farcy.handlers.Flake8().process

    def test_perfect_file(self):
        """There should be no issues."""
        errors = self.process(self.path('no_issue.py'))
        self.assertEqual({}, errors)

    def test_single_error(self):
        """A single error should be returned."""
        errors = self.process(self.path('single_issue.py'))
        self.assertEqual({3: ['1: E302 expected 2 blank lines, found 1']},
                         errors)


class Pep257Test(FarcyTest):

    """Tests for the Pep257 Handler."""

    def setUp(self):
        """Set up helpers used for each test case."""
        self.process = farcy.handlers.Pep257().process

    def test_perfect_file(self):
        """There should be no issues."""
        errors = self.process(self.path('no_issue.py'))
        self.assertEqual({}, errors)

    def test_single_error(self):
        """A single error should be returned."""
        errors = self.process(self.path('single_issue.py'))
        self.assertEqual({3: [('D203: Expected 1 blank line *before* class '
                               'docstring, found 0')]},
                         errors)
