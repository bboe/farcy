"""Farcy handlers test file."""

from __future__ import print_function
import farcy.handlers
import os
import unittest


class ExtHandlerTest(unittest.TestCase):

    """Tests common Farcy handler extension methods."""

    def setUp(self):
        self.cls = farcy.handlers.ExtHandler
        self.cls.BINARY_VERSION = '1.0'
        self.cls.BINARY = 'FOOBAR'

    def test_constructor__binary_not_installed(self):
        CLS2 = type('CLS2', (farcy.handlers.ExtHandler,), {})
        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.instance = CLS2()
        self.assertEqual('FOOBAR is not installed.',
                         str(cm.exception))

    def test_constructor__binary_permission_denied(self):
        CLS2 = type('CLS2', (farcy.handlers.ExtHandler,), {})
        CLS2.BINARY = '/tmp'
        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.instance = CLS2()
        self.assertEqual('/tmp cannot be executed.',
                         str(cm.exception))

    def test_constructor__binary_required(self):
        CLS2 = type('CLS2', (farcy.handlers.ExtHandler,), {})
        CLS2.BINARY = None
        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.instance = CLS2()
        self.assertEqual('CLS2 does not have a binary specified.',
                         str(cm.exception))

    def test_constructor__subclass_required(self):
        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.instance = self.cls()
        self.assertEqual('Base class `ExtHandler` must be extended.',
                         str(cm.exception))

    def test_verify_version(self):
        self.assertEqual(None, self.cls.verify_version('1.0'))
        self.assertEqual(None, self.cls.verify_version('1.0', True))
        self.assertEqual(None, self.cls.verify_version('1.0.0'))
        self.assertEqual(None, self.cls.verify_version('1.0.1'))
        self.assertEqual(None, self.cls.verify_version('1.1.1'))
        self.assertEqual(None, self.cls.verify_version('2'))

    def test_verify_version__expected_too_small(self):
        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.cls.verify_version('0.9')
        self.assertEqual('Expected FOOBAR >= 1.0, found 0.9',
                         str(cm.exception))

        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.cls.verify_version('1.0 ')  # Contains space
        self.assertEqual('Expected FOOBAR >= 1.0, found 1.0 ',
                         str(cm.exception))

    def test_verify_version__not_exact_match(self):
        with self.assertRaises(farcy.exceptions.HandlerException) as cm:
            self.cls.verify_version('1.0.1', True)
        self.assertEqual('Expected FOOBAR 1.0, found 1.0.1',
                         str(cm.exception))


class FarcyTest(unittest.TestCase):

    """Provides helpers for various FarcyTest classes."""

    def shortDescription(self):
        """Disable the short description (docstring) output."""
        return None

    def path(self, filename):
        """Return a path to the example file."""
        return os.path.join(os.path.dirname(__file__), 'examples', filename)

    def config(self, linter):
        """Return config path for linter."""
        return os.path.join(
            os.path.dirname(__file__), 'configs',
            'handler_{0}.conf'.format(linter.__class__.__name__.lower()))


class ESLintTest(FarcyTest):

    """Tests for the ESLint Handler."""

    def setUp(self):
        """Set up helpers used for each test case."""
        self.linter = farcy.handlers.ESLint()
        self.linter.config_file_path = self.config(self.linter)

    def test_perfect_file(self):
        """There should be no issues."""
        errors = self.linter.process(self.path('no_issue.js'))
        self.assertEqual({}, errors)

    def test_single_error(self):
        """A single error should be returned."""
        errors = self.linter.process(self.path('single_issue.js'))
        self.assertEqual({3: ['Unexpected console statement. (no-console)']},
                         errors)


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
        self.assertEqual({3: [('D203: 1 blank line required before class '
                               'docstring (found 0)')]},
                         errors)


class RubocopTest(FarcyTest):

    """Tests for the Rubocop Handler."""

    def setUp(self):
        """Set up helpers used for each test case."""
        self.linter = farcy.handlers.Rubocop()
        self.linter.config_file_path = self.config(self.linter)

    def test_perfect_file(self):
        """There should be no issues."""
        errors = self.linter.process(self.path('no_issue.rb'))
        self.assertEqual({}, errors)

    def test_single_error(self):
        """A single error should be returned.

           Uses config to disable 1 issue.
        """
        errors = self.linter.process(self.path('single_issue.rb'))
        self.assertEqual({3: [('Style/DefWithParentheses: Omit the parentheses'
                               ' in defs when the method doesn\'t accept any '
                               'arguments.')]},
                         errors)
