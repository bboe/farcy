"""Farcy class test file."""

from __future__ import print_function
from collections import namedtuple
from farcy import Farcy, no_handler_debug_factory
from farcy.helpers import Config
from mock import MagicMock, call, patch
import logging
import unittest

PFILE_ATTRS = ['contents', 'filename', 'patch', 'status']

MockInfo = namedtuple('Info', ['decoded'])
MockPFile = namedtuple('PFile', PFILE_ATTRS)


def mockpfile(**kwargs):
    for attr in PFILE_ATTRS:
        kwargs.setdefault(attr, None)
    return MockPFile(**kwargs)


class FarcyTest(unittest.TestCase):

    @patch('farcy.helpers.get_session')
    @patch('farcy.UpdateChecker')
    def _farcy_instance(self, mock_update_checker, mock_get_session,
                        config=Config()):
        config.ensure_session()
        if config.repository is None:
            config.repository = 'dummy/dummy'
        farcy = Farcy(config)
        self.assertTrue(mock_update_checker.called)
        return farcy

    @patch('farcy.added_lines')
    def test_compute_pfile_stats__added(self, mock_added_lines):
        mock_added_lines.return_value = {13: 10, 15: 20, 18: 100}
        stats = {'added_files': 10, 'added_lines': 10}
        actual = self._farcy_instance()._compute_pfile_stats(
            mockpfile(patch='', status='added'), stats)
        self.assertTrue(mock_added_lines.called)
        self.assertEqual(mock_added_lines.return_value, actual)
        self.assertEqual({'added_files': 11, 'added_lines': 13}, stats)

    def test_compute_pfile_stats__excluded(self):
        stats = {'blacklisted_files': 10}
        config = Config()
        config.exclude_paths = ['tmp/*']
        farcy = self._farcy_instance(config=config)
        self.assertEqual(None, farcy._compute_pfile_stats(
            mockpfile(filename='tmp/foo'), stats))
        self.assertEqual({'blacklisted_files': 11}, stats)

    @patch('farcy.added_lines')
    def test_compute_pfile_stats__modified(self, mock_added_lines):
        mock_added_lines.return_value = {1: 1, 2: 2}
        for status in ['modified', 'renamed']:
            stats = {'modified_files': 10, 'modified_lines': 10}
            actual = self._farcy_instance()._compute_pfile_stats(
                mockpfile(patch='', status=status), stats)
            self.assertTrue(mock_added_lines.called)
            mock_added_lines.reset_mock()
            self.assertEqual(mock_added_lines.return_value, actual)
            self.assertEqual({'modified_files': 11, 'modified_lines': 12},
                             stats)

    def test_compute_pfile_stats__no_change(self):
        stats = {'unchanged_files': 10}
        self.assertEqual(None, self._farcy_instance()._compute_pfile_stats(
            mockpfile(status='added'), stats))
        self.assertEqual({'unchanged_files': 11}, stats)

    def test_compute_pfile_stats__removed(self):
        stats = {'deleted_files': 10}
        config = Config()
        config.exclude_paths = ['tmp/*']
        farcy = self._farcy_instance(config=config)
        self.assertEqual(None, farcy._compute_pfile_stats(
            mockpfile(filename='a/tmp/b', status='removed'), stats))
        self.assertEqual({'deleted_files': 11}, stats)

    def test_compute_pfile_stats__unexpected_status(self):
        logger = logging.getLogger('farcy')
        stats = {}
        with patch.object(logger, 'critical') as mock_critical:
            self.assertEqual(None, self._farcy_instance()._compute_pfile_stats(
                mockpfile(patch='', status='foobar'), stats))
            self.assertTrue(mock_critical.called)
        self.assertEqual({}, stats)

    def test_get_issues__simple_module(self):
        farcy = self._farcy_instance()
        pfile = mockpfile(contents=lambda: MockInfo(decoded=b'"""A."""\n'),
                          filename='a.py')
        self.assertEqual({}, farcy.get_issues(pfile))

    def test_get_issues__no_handlers(self):
        farcy = self._farcy_instance()
        self.assertEqual({}, farcy.get_issues(mockpfile(filename='')))


class NoHandlerDebugFactory(unittest.TestCase):
    def setUp(self):
        self.farcy = MagicMock()

    def test_no_handler_factory__cache_response(self):
        func = no_handler_debug_factory(1)
        func(self.farcy, '.js')
        func(self.farcy, '.js')
        self.farcy.log.debug.assert_called_once_with(
            'No handlers for extension .js')

    def test_no_handler_factory__output_when_cache_expired(self):
        func = no_handler_debug_factory(0)
        func(self.farcy, '.js')
        func(self.farcy, '.js')
        calls = [call('No handlers for extension .js')] * 2
        self.farcy.log.debug.assert_has_calls(calls)

    def test_no_handler_factory__multiple_calls(self):
        func = no_handler_debug_factory(1)
        func(self.farcy, '.js')
        func(self.farcy, '.css')
        calls = [call('No handlers for extension .js'),
                 call('No handlers for extension .css')]
        self.farcy.log.debug.assert_has_calls(calls)
