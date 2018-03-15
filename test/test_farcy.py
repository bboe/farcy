"""Farcy class test file."""

from __future__ import print_function
from collections import namedtuple
from datetime import datetime
from farcy import (Config, FARCY_COMMENT_START, Farcy, FarcyException, UTC,
                   main, no_handler_debug_factory)
from mock import MagicMock, call, patch
from requests import ConnectionError
import farcy as farcy_module
import logging
import unittest
from .helper import Struct

Config.PATH = '/dev/null'  # Don't allow the system config file to load.
farcy_module.APPROVAL_PHRASES = ['Dummy Approval']  # Provide only one option.

PFILE_ATTRS = ['contents', 'filename', 'patch', 'status']

MockInfo = namedtuple('Info', ['decoded'])
MockPFile = namedtuple('PFile', PFILE_ATTRS)


def assert_calls(method, *calls):
    method.assert_has_calls(list(calls))
    assert method.call_count == len(calls), "{0} != {1}".format(
        list(calls), method.mock_calls)


def assert_status(farcy, failures=0):
    if failures:
        call2 = call('dummy', 'failure', context='farcy',
                     description='found {0} issue{1}'.format(
                         failures, 's' if failures > 1 else ''))
    else:
        call2 = call('dummy', 'success', context='farcy',
                     description='approves! Dummy Approval!')
    assert_calls(farcy.repo.create_status,
                 call('dummy', 'pending', context='farcy',
                      description='started investigation'), call2)


def mockpfile(**kwargs):
    for attr in PFILE_ATTRS:
        kwargs.setdefault(attr, None)
    return MockPFile(**kwargs)


class FarcyBaseTest(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.logger = logging.getLogger('farcy')

    @patch('farcy.UpdateChecker')
    @patch('farcy.objects.get_session')
    def _farcy_instance(self, mock_get_session, mock_update_checker,
                        config=None):
        if config is None:
            config = Config(None)
        if config.repository is None:
            config.repository = 'dummy/dummy'
        farcy = Farcy(config)
        self.assertTrue(mock_get_session.called)
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
        stats = {}
        with patch.object(self.logger, 'critical') as mock_critical:
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


class FarcyHandlePrTest(FarcyBaseTest):
    DUMMY_COMMENT = Struct(body='_[farcy \n* MatchingError', path='DummyFile',
                           position=16)

    @patch('farcy.Farcy.get_issues')
    @patch('farcy.added_lines')
    def test_handle_pr__exception_from_get_issues(self, mock_added_lines,
                                                  mock_get_issues):
        def side_effect():
            raise Exception()

        mock_added_lines.return_value = {16: 16}
        mock_get_issues.side_effect = side_effect

        pr = MagicMock(number=180, state='open', user=Struct(login='Dummy'))
        pr.commits.return_value = [Struct(sha='dummy')]
        pfile = mockpfile(patch='', status='added')
        pr.files.return_value = [pfile]

        farcy = self._farcy_instance()
        with patch.object(self.logger, 'info') as mock_info:
            farcy.handle_pr(pr)
            assert_calls(mock_info, call('Handling PR#180 by Dummy'),
                         call('PR#180 STATUS: encountered an exception in '
                              'handler. Check log.'))

        mock_added_lines.assert_called_with('')
        mock_get_issues.assert_called_once_with(pfile)
        assert_calls(farcy.repo.create_status,
                     call('dummy', 'pending', context='farcy',
                          description='started investigation'),
                     call('dummy', 'error', context='farcy',
                          description=('encountered an exception in handler. '
                                       'Check log.')))

    def test_handle_pr__pr_closed(self):
        pr = MagicMock(number=180, state='closed')
        farcy = self._farcy_instance()
        with patch.object(self.logger, 'debug') as mock_debug:
            farcy.handle_pr(pr)
            mock_debug.assert_called_with(
                'Skipping PR#180: invalid state (closed)')
        pr.refresh.assert_called_with()

    @patch('farcy.Farcy.get_issues')
    @patch('farcy.added_lines')
    def test_handle_pr__single_failure(self, mock_added_lines,
                                       mock_get_issues):
        mock_added_lines.return_value = {16: 16}
        mock_get_issues.return_value = {16: ['Dummy Failure']}

        pr = MagicMock(number=180, state='open', user=Struct(login='Dummy'))
        pr.commits.return_value = [Struct(sha='dummy')]
        pfile = mockpfile(filename='DummyFile', patch='', status='added')
        pr.files.return_value = [pfile]

        farcy = self._farcy_instance()
        with patch.object(self.logger, 'info') as mock_info:
            farcy.handle_pr(pr)
            assert_calls(mock_info,
                         call('Handling PR#180 by Dummy'),
                         call('PR#180 STATUS: found 1 issue'))

        mock_added_lines.assert_called_with('')
        mock_get_issues.assert_called_once_with(pfile)
        assert_calls(pr.create_review_comment, call(
            '{0}\n* Dummy Failure'.format(FARCY_COMMENT_START),
            'dummy', 'DummyFile', 16))
        assert_status(farcy, failures=1)

    @patch('farcy.Farcy.get_issues')
    @patch('farcy.added_lines')
    def test_handle_pr__single_failure__limit_exceeded(self, mock_added_lines,
                                                       mock_get_issues):
        mock_added_lines.return_value = {16: 16}
        mock_get_issues.return_value = {16: ['Dummy Failure']}

        pr = MagicMock(number=180, state='open', user=Struct(login='Dummy'))
        pr.commits.return_value = [Struct(sha='dummy')]
        pr.review_comments.return_value = [self.DUMMY_COMMENT] * 128

        pfile = mockpfile(filename='DummyFile', patch='', status='added')
        pr.files.return_value = [pfile]

        farcy = self._farcy_instance()
        with patch.object(self.logger, 'debug') as mock_debug:
            with patch.object(self.logger, 'info') as mock_info:
                farcy.handle_pr(pr)
                assert_calls(mock_info,
                             call('Handling PR#180 by Dummy'),
                             call('PR#180 STATUS: found 1 issue'))
            assert_calls(mock_debug,
                         call('PR#180      added_files: 1'),
                         call('PR#180      added_lines: 1'),
                         call('PR#180           issues: 1'),
                         call('PR#180   skipped_issues: 1'))

        mock_added_lines.assert_called_with('')
        mock_get_issues.assert_called_once_with(pfile)
        assert_calls(pr.create_review_comment)
        assert_status(farcy, failures=1)

    @patch('farcy.Farcy.get_issues')
    @patch('farcy.added_lines')
    def test_handle_pr__success(self, mock_added_lines, mock_get_issues):
        mock_added_lines.return_value = {16: 16}
        mock_get_issues.return_value = {3: ['Failure on non-modified line.']}

        pr = MagicMock(number=180, state='open', user=Struct(login='Dummy'))
        pr.commits.return_value = [Struct(sha='dummy')]
        pfile = mockpfile(patch='', status='added')
        pr.files.return_value = [pfile]

        farcy = self._farcy_instance()
        with patch.object(self.logger, 'info') as mock_info:
            farcy.handle_pr(pr)
            assert_calls(mock_info,
                         call('Handling PR#180 by Dummy'),
                         call('PR#180 STATUS: approves! Dummy Approval!'))

        mock_added_lines.assert_called_with('')
        mock_get_issues.assert_called_once_with(pfile)
        assert_calls(pr.create_review_comment)
        assert_status(farcy)

    def test_handle_pr__success_without_any_changed_files(self):
        pr = MagicMock(number=180, state='open', user=Struct(login='Dummy'))
        pr.commits.return_value = [Struct(sha='dummy')]
        pr.files.return_value = [mockpfile()]
        farcy = self._farcy_instance()
        with patch.object(self.logger, 'info') as mock_info:
            farcy.handle_pr(pr)
            assert_calls(mock_info,
                         call('Handling PR#180 by Dummy'),
                         call('PR#180 STATUS: approves! Dummy Approval!'))
        assert_status(farcy)

    def test_handle_pr__success_without_files(self):
        pr = MagicMock(number=180, state='open', user=Struct(login='Dummy'))
        pr.commits.return_value = [Struct(sha='dummy')]
        farcy = self._farcy_instance()
        with patch.object(self.logger, 'info') as mock_info:
            farcy.handle_pr(pr)
            assert_calls(mock_info,
                         call('Handling PR#180 by Dummy'),
                         call('PR#180 STATUS: approves! Dummy Approval!'))
        assert_status(farcy)

    def test_handle_pr__user_blacklisted(self):
        pr = Struct(number=180, user=Struct(login='Dummy'))
        farcy = self._farcy_instance()
        farcy.config.exclude_users = ['dummy']
        with patch.object(self.logger, 'debug') as mock_debug:
            farcy.handle_pr(pr)
            mock_debug.assert_called_with(
                'Skipping PR#180: Dummy is not allowed')

    def test_handle_pr__user_not_whitelisted(self):
        pr = Struct(number=180, user=Struct(login='Dummy'))
        farcy = self._farcy_instance()
        farcy.config.limit_users = ['bboe']
        with patch.object(self.logger, 'debug') as mock_debug:
            farcy.handle_pr(pr)
            mock_debug.assert_called_with(
                'Skipping PR#180: Dummy is not allowed')


class FarcyEventCallbackTest(FarcyBaseTest):
    @patch('farcy.Farcy.handle_pr')
    def test_PullRequestEvent__closed_existing(self, mock_handle_pr):
        instance = self._farcy_instance()
        instance.open_prs = {'DUMMY_BRANCH': None}

        pull_request = Struct(head=Struct(ref='DUMMY_BRANCH'), number=1337)
        event = Struct(payload={'action': 'closed',
                                'pull_request': pull_request})

        instance.PullRequestEvent(event)
        self.assertEqual({}, instance.open_prs)
        self.assertFalse(mock_handle_pr.called)

    @patch('farcy.Farcy.handle_pr')
    def test_PullRequestEvent__closed_non_existing(self, mock_handle_pr):
        instance = self._farcy_instance()
        instance.log = MagicMock()
        self.assertEqual({}, instance.open_prs)

        pull_request = Struct(head=Struct(ref='DUMMY_BRANCH'), number=1337)
        event = Struct(payload={'action': 'closed',
                                'pull_request': pull_request})

        instance.PullRequestEvent(event)
        self.assertEqual({}, instance.open_prs)
        self.assertFalse(mock_handle_pr.called)
        self.assertTrue(instance.log.warning.called)

    @patch('farcy.Farcy.handle_pr')
    def test_PullRequestEvent__opened(self, mock_handle_pr):
        instance = self._farcy_instance()
        self.assertEqual({}, instance.open_prs)

        pull_request = Struct(head=Struct(ref='DUMMY_BRANCH'), number=1337)
        event = Struct(payload={'action': 'opened',
                                'pull_request': pull_request})

        instance.PullRequestEvent(event)
        self.assertEqual({'DUMMY_BRANCH': pull_request}, instance.open_prs)
        self.assertTrue(mock_handle_pr.called)

    @patch('farcy.Farcy.handle_pr')
    def test_PullRequestEvent__reopened(self, mock_handle_pr):
        instance = self._farcy_instance()
        self.assertEqual({}, instance.open_prs)

        pull_request = Struct(head=Struct(ref='DUMMY_BRANCH'), number=1337)
        event = Struct(payload={'action': 'reopened',
                                'pull_request': pull_request})

        instance.PullRequestEvent(event)
        self.assertEqual({'DUMMY_BRANCH': pull_request}, instance.open_prs)
        self.assertFalse(mock_handle_pr.called)

    @patch('farcy.Farcy.handle_pr')
    def test_PushEvent__pr_does_not_exist(self, mock_handle_pr):
        event = Struct(payload={'ref': 'refs/heads/DUMMY_BRANCH'})
        self._farcy_instance().PushEvent(event)
        self.assertFalse(mock_handle_pr.called)

    @patch('farcy.Farcy.handle_pr')
    def test_PushEvent__pr_exists(self, mock_handle_pr):
        instance = self._farcy_instance()
        instance.open_prs['DUMMY_BRANCH'] = 0xDEADBEEF
        instance.PushEvent(Struct(payload={'ref': 'refs/heads/DUMMY_BRANCH'}))
        mock_handle_pr.assert_called_with(0xDEADBEEF)


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

    @patch('farcy.Farcy.events')
    @patch('farcy.Farcy.PushEvent')
    def test_run(self, mock_callback, mock_events):
        event1 = Struct(type='PushEvent', uniq=1)
        event2 = Struct(type='PushEvent', uniq=2)
        self.assertEqual(event1, event1)
        self.assertNotEqual(event1, event2)

        mock_events.return_value = [event1, event2]

        self._farcy_instance().run()
        assert_calls(mock_callback, call(event1), call(event2))
        mock_callback.assert_called_with(event2)

    @patch('farcy.Farcy.handle_pr')
    def test_run__single_pull_request(self, mock_handle_pr):
        farcy = self._farcy_instance()
        farcy.repo.pull_request.side_effect = lambda x: x
        farcy.config.pull_requests = '418'
        farcy.run()
        assert_calls(mock_handle_pr, call(418, force=True))

    @patch('farcy.Farcy.handle_pr')
    def test_run__multiple_pull_requests(self, mock_handle_pr):
        farcy = self._farcy_instance()
        farcy.repo.pull_request.side_effect = lambda x: x
        farcy.config.pull_requests = '360,180,720'
        farcy.run()
        assert_calls(mock_handle_pr, call(180, force=True),
                     call(360, force=True), call(720, force=True))


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
        assert_calls(self.farcy.log.debug, *calls)

    def test_no_handler_factory__multiple_calls(self):
        func = no_handler_debug_factory(1)
        func(self.farcy, '.js')
        func(self.farcy, '.css')
        assert_calls(self.farcy.log.debug,
                     call('No handlers for extension .js'),
                     call('No handlers for extension .css'))
