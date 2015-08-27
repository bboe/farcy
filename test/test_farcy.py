"""Farcy class test file."""

from __future__ import print_function
from collections import namedtuple
from datetime import datetime
from farcy import Farcy, FarcyException, main, no_handler_debug_factory
from farcy.helpers import Config, UTC
from mock import MagicMock, call, patch
from requests import ConnectionError
import logging
import unittest

PFILE_ATTRS = ['contents', 'filename', 'patch', 'status']

MockInfo = namedtuple('Info', ['decoded'])
MockPFile = namedtuple('PFile', PFILE_ATTRS)


class Struct(object):
    def __init__(self, iterable=None, **attrs):
        self.__dict__.update(attrs)
        self._iterable = iterable or []

    def __getitem__(self, index):
            return self._iterable[index]


def mockpfile(**kwargs):
    for attr in PFILE_ATTRS:
        kwargs.setdefault(attr, None)
    return MockPFile(**kwargs)


class FarcyBaseTest(unittest.TestCase):
    @patch('farcy.helpers.get_session')
    @patch('farcy.UpdateChecker')
    def _farcy_instance(self, mock_update_checker, mock_get_session,
                        config=Config(None)):
        if config.repository is None:
            config.repository = 'dummy/dummy'
        farcy = Farcy(config)
        self.assertTrue(mock_update_checker.called)
        return farcy


class FarcyTest(FarcyBaseTest):
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
        config = Config(None)
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
        config = Config(None)
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


class FarcyEventTest(FarcyBaseTest):
    def test_event_loop__ignore_events_before_start(self):
        event = Struct(actor=Struct(login=None), type='PushEvent',
                       created_at=datetime.now(UTC()), id=1)
        farcy = self._farcy_instance()  # Must have its time set second.

        events = []
        newest_id = farcy._event_loop([event], events)
        self.assertEqual(None, newest_id)
        self.assertEqual([], events)

    def test_event_loop__ignore_old_events(self):
        farcy = self._farcy_instance()  # Must have its time set first.
        farcy.last_event_id = 1

        event = Struct(actor=Struct(login=None), type='PushEvent',
                       created_at=datetime.now(UTC()), id=1)

        events = []
        newest_id = farcy._event_loop([event], events)
        self.assertEqual(None, newest_id)
        self.assertEqual([], events)

    def test_event_loop__multiple_events(self):
        farcy = self._farcy_instance()  # Must have its time set first.

        event_1 = Struct(actor=Struct(login=None), type='PushEvent',
                         created_at=datetime.now(UTC()), id=1)
        event_2 = Struct(actor=Struct(login=None), type='ForkEvent',
                         created_at=datetime.now(UTC()), id=2)
        event_3 = Struct(actor=Struct(login=None), type='PullRequestEvent',
                         created_at=datetime.now(UTC()), id=3)
        event_4 = Struct(actor=Struct(login=None), type='MemberEvent',
                         created_at=datetime.now(UTC()), id=4)

        events = []
        newest_id = farcy._event_loop([event_4, event_3, event_2, event_1],
                                      events)
        self.assertEqual(4, newest_id)
        self.assertEqual([event_1, event_3], events)

    def test_event_loop__no_events(self):
        events = []
        newest_id = self._farcy_instance()._event_loop([], events)
        self.assertEqual(None, newest_id)
        self.assertEqual([], events)

    def test_event_loop__single_event(self):
        farcy = self._farcy_instance()  # Must have its time set first.
        event = Struct(actor=Struct(login=None), type='PushEvent',
                       created_at=datetime.now(UTC()), id=0xDEADBEEF)

        events = []
        newest_id = farcy._event_loop([event], events)
        self.assertEqual(0xDEADBEEF, newest_id)
        self.assertEqual([event], events)

    def test_events__end_loop(self):
        farcy = self._farcy_instance()
        self.assertEqual(None, farcy.last_event_id)

        event = Struct(actor=Struct(login=None), type='PushEvent',
                       created_at=datetime.now(UTC()), id=0xDEADBEEF)
        farcy.repo.events.return_value = Struct(
            [event], etag='DUMMY_ETAG',
            last_response=Struct(headers={'X-Poll-Interval': 100}))

        event_itr = farcy.events()
        self.assertEqual(event, next(event_itr))
        farcy.running = False
        self.assertRaises(StopIteration, next, event_itr)

    @patch('farcy.Farcy._event_loop')
    @patch('time.sleep')
    def test_events__network_exception(self, mock_sleep, mock_event_loop):
        farcy = self._farcy_instance()
        event = Struct(actor=Struct(login=None), type='PushEvent',
                       created_at=datetime.now(UTC()), id=0xDEADBEEF)

        call_count = [0]

        def side_effect(_, events):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError('Foo')
            else:
                events.append(event)
                return event.id

        mock_event_loop.side_effect = side_effect
        self.assertEqual(event, next(farcy.events()))
        self.assertEqual(0xDEADBEEF, farcy.last_event_id)
        self.assertTrue(mock_sleep.called_with(1))

    def test_events__prevent_duplicate_calls(self):
        farcy = self._farcy_instance()
        self.assertEqual(None, farcy.last_event_id)

        event = Struct(actor=Struct(login=None), type='PushEvent',
                       created_at=datetime.now(UTC()), id=0xDEADBEEF)
        farcy.repo.events.return_value = Struct([event], etag='DUMMY_ETAG')

        self.assertEqual(event, next(farcy.events()))
        self.assertEqual(0xDEADBEEF, farcy.last_event_id)

        self.assertRaises(FarcyException, next, farcy.events())


class MainTest(unittest.TestCase):
    @patch('farcy.Farcy')
    @patch('farcy.Config')
    def test_main__farcy_exception_in_run(self, mock_config, mock_farcy):
        def side_effect():
            raise FarcyException
        mock_farcy.return_value.run.side_effect = side_effect
        self.assertEqual(1, main())

    @patch('farcy.Farcy')
    @patch('farcy.Config')
    def test_main__keyboard_interrupt_in_farcy(self, mock_config, mock_farcy):
        def side_effect(_):
            raise KeyboardInterrupt
        mock_farcy.side_effect = side_effect
        self.assertEqual(0, main())

    @patch('farcy.Farcy')
    @patch('farcy.Config')
    def test_main__keyboard_interrupt_in_run(self, mock_config, mock_farcy):
        def side_effect():
            raise KeyboardInterrupt
        mock_farcy.return_value.run.side_effect = side_effect
        self.assertEqual(0, main())

    @patch('farcy.Config')
    def test_main__no_repo_specified(self, mock_config):
        mock_config.return_value.repository = None
        self.assertEqual(2, main())

    @patch('farcy.Farcy')
    @patch('farcy.Config')
    def test_main__no_exception(self, mock_config, mock_farcy):
        self.assertEqual(None, main())
        self.assertTrue(mock_config.called)
        self.assertTrue(mock_farcy.called)
        self.assertTrue(mock_farcy.return_value.run.called)


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
