"""Farcy objects test file."""

from __future__ import print_function
from farcy import objects
from mock import patch
import unittest
import farcy.exceptions as exceptions
from .helper import Struct


class ConfigTest(unittest.TestCase):
    """Tests Config helper."""

    @patch('farcy.objects.ConfigParser')
    @patch('os.path.isfile')
    def _config_instance(self, callback, mock_is_file, mock_config, repo=None,
                         post_callback=None, **overrides):
        mock_is_file.called_with(objects.Config.PATH).return_value = True

        if callback:
            callback(mock_config.return_value)
        config = objects.Config(repo, **overrides)
        if post_callback:
            post_callback(mock_config.return_value)
        self.assertTrue(mock_config.called)
        return config

    def test_cant_change_log_level_if_debug(self):
        config = self._config_instance(None, repo='a/b')
        self.assertNotEqual('DEBUG', config.log_level)
        config.debug = True
        self.assertEqual('DEBUG', config.log_level)
        config.log_level = 'WARNING'
        self.assertEqual('DEBUG', config.log_level)

    def test_config_file_is_overridable(self):
        def callback(mock_config):
            mock_config.items.return_value = {'start_event': '1337'}
        config = self._config_instance(callback, repo='a/b')
        self.assertEqual(1337, config.start_event)
        config.start_event = 10
        self.assertEqual(10, config.start_event)

    def test_config_file_repo_specific_works(self):
        def callback(mock_config):
            mock_config.has_section.return_value = True
            mock_config.items.return_value = {'start_event': '1337'}

        def post_callback(mock_config):
            mock_config.items.assert_called_with('a/b')
        config = self._config_instance(callback, repo='a/b',
                                       post_callback=post_callback)
        self.assertEqual('a/b', config.repository)
        self.assertEqual(1337, config.start_event)

    def test_config_file_values(self):
        def callback(mock_config):
            mock_config.has_section.return_value = False
            mock_config.items.return_value = {
                'start_event': '10', 'debug': True,
                'exclude_paths': 'node_modules,vendor',
                'limit_users': 'balloob,bboe', 'log_level': 'DEBUG',
                'pr_issue_report_limit': '100'}

        def post_callback(mock_config):
            mock_config.items.assert_called_with('DEFAULT')
        config = self._config_instance(callback, repo='a/b',
                                       post_callback=post_callback)
        self.assertEqual('a/b', config.repository)
        self.assertEqual(10, config.start_event)
        self.assertEqual(True, config.debug)
        self.assertEqual({'node_modules', 'vendor'}, config.exclude_paths)
        self.assertEqual({'balloob', 'bboe'}, config.limit_users)
        self.assertEqual('DEBUG', config.log_level)
        self.assertEqual(100, config.pr_issue_report_limit)

    def test_config__overrides(self):
        config = self._config_instance(None, repo='a/b', start_event=1337,
                                       limit_users='bboe')
        self.assertEqual('a/b', config.repository)
        self.assertEqual(1337, config.start_event)
        self.assertEqual({'bboe'}, config.limit_users)

    def test_config__repr(self):
        config = self._config_instance(None, repo='a/b')
        repr_str = ("Config('a/b', comment_group_threshold=3, debug=False, "
                    "exclude_paths=None, exclude_users=None, "
                    "limit_users=None, log_level='ERROR', "
                    "pr_issue_report_limit=128, pull_requests=None, "
                    "start_event=None)")
        self.assertEqual(repr_str, repr(config))

    def test_default_repo_from_config(self):
        def callback(mock_config):
            mock_config.get.return_value = 'appfolio/farcy'
        config = self._config_instance(callback)
        self.assertEqual('appfolio/farcy', config.repository)

    def test_default_repo_from_config_raise_on_invalid(self):
        def callback(mock_config):
            mock_config.get.return_value = 'invalid_repo'
        with self.assertRaises(exceptions.FarcyException):
            self._config_instance(callback)

    def test_raise_if_invalid_log_level(self):
        config = self._config_instance(None, repo='a/b')
        with self.assertRaises(exceptions.FarcyException):
            config.log_level = 'invalid_log_level'

    def test_raise_if_invalid_repository(self):
        config = self._config_instance(None, repo='a/b')
        with self.assertRaises(exceptions.FarcyException):
            config.repository = 'invalid_repo'

    def test_raise_if_setting_blacklist_with_whitelist_already_set(self):
        config = self._config_instance(None, limit_users=['a'], repo='a/b')
        with self.assertRaises(exceptions.FarcyException):
            config.exclude_users = ['b']

    def test_raise_if_setting_whitelist_with_blacklist_already_set(self):
        config = self._config_instance(None, exclude_users=['a'], repo='a/b')
        with self.assertRaises(exceptions.FarcyException):
            config.limit_users = ['b']

    def test_setting_repo(self):
        config = self._config_instance(None, repo='a/b')
        self.assertEqual('a/b', config.repository)
        config.repository = 'appfolio/farcy'
        self.assertEqual('appfolio/farcy', config.repository)

    def test_setting_values_via_dict(self):
        config = self._config_instance(None, repo='appfolio/farcy')
        data = {
            'start_event': 1000,
            'debug': False,
            'exclude_paths': {'npm_modules', 'vendor'},
            'limit_users': {'balloob', 'bboe'},
            'log_level': 'WARNING',
            'pr_issue_report_limit': 100
        }

        config.override(**data)
        for attr, value in data.items():
            self.assertEqual(value, getattr(config, attr))

    def test_user_allowed_with_no_lists_set(self):
        config = self._config_instance(None, repo='a/b')
        self.assertTrue(config.user_allowed('balloob'))

    def test_user_allowed_when_not_blacklisted(self):
        config = self._config_instance(None, exclude_users=['a'], repo='a/b')
        self.assertTrue(config.user_allowed('balloob'))

    def test_user_allowed_when_whitelisted(self):
        config = self._config_instance(None, repo='a/b')
        config.limit_users = ['bboe', 'balloob']
        self.assertTrue(config.user_allowed('balloob'))
        self.assertFalse(config.user_allowed('appfolio'))

    def test_user_not_allowed_when_blacklisted(self):
        config = self._config_instance(None, exclude_users=['balloob'],
                                       repo='a/b')
        self.assertFalse(config.user_allowed('balloob'))

    def test_user_not_allowed_when_not_whitelisted(self):
        config = self._config_instance(None, limit_users=['a'],
                                       repo='a/b')
        self.assertFalse(config.user_allowed('balloob'))


class ErrorMessageTest(unittest.TestCase):
    def setUp(self):
        self.message = objects.ErrorMessage('Dummy Message', 2)

    def add_lines(self, on_github, *lines):
        for line in lines:
            self.message.track(line, on_github)

    def test_messages__group_consequtive(self):
        self.add_lines(False, 1, 2, 3)
        self.assertEqual([(1, 'Dummy Message <sub>3x spanning 3 lines</sub>')],
                         list(self.message.messages()))

    def test_messages__group_span(self):
        self.add_lines(False, 1, 3, 5)
        self.assertEqual([(1, 'Dummy Message <sub>3x spanning 5 lines</sub>')],
                         list(self.message.messages()))

    def test_messages__group_span__existing_group(self):
        self.add_lines(False, 1, 3, 5)
        self.message.track_group(1, 3)
        self.assertEqual([], list(self.message.messages()))

    def test_messages__no_grouping(self):
        self.add_lines(False, 1, 4, 100, 105)
        self.add_lines(True, 2, 4, 101, 106)
        self.assertEqual([(1, 'Dummy Message'), (100, 'Dummy Message'),
                          (105, 'Dummy Message')],
                         list(self.message.messages()))

    def test_messages__no_messages(self):
        self.assertEqual([], list(self.message.messages()))

    def test_track__return_value(self):
        self.assertEqual(self.message, self.message.track(16))

    def test_track_group__return_value(self):
        self.assertEqual(self.message, self.message.track_group(16, 2))


class ErrorTrackerTest(unittest.TestCase):
    def setUp(self):
        self.tracker = objects.ErrorTracker([], 2)

    def test_initial_values(self):
        self.assertEqual(0, self.tracker.github_message_count)
        self.assertEqual(0, self.tracker.new_issue_count)

    def test_no_issues(self):
        self.assertEqual([], list(self.tracker.errors('DummyFile')))

        comment = Struct(body='Regular comment', path='DummyFile', position=16)
        self.tracker.from_github_comments([comment])

        self.assertEqual(0, self.tracker.github_message_count)
        self.assertEqual(0, self.tracker.hidden_issue_count)
        self.assertEqual(0, self.tracker.new_issue_count)
        self.assertEqual([], list(self.tracker.errors('DummyFile')))

    def test_grouped_issue(self):
        comment = Struct(body=('_[farcy \n* MatchingError <sub>3x spanning 4 '
                               'lines</sub>'), path='DummyFile', position=16)
        self.tracker.from_github_comments([comment])
        self.tracker.track('MatchingError', 'DummyFile', 16)
        self.tracker.track('MatchingError', 'DummyFile', 18)
        self.tracker.track('MatchingError', 'DummyFile', 19)

        self.assertEqual(1, self.tracker.github_message_count)
        self.assertEqual(0, self.tracker.hidden_issue_count)
        self.assertEqual(3, self.tracker.new_issue_count)
        self.assertEqual([], list(self.tracker.errors('DummyFile')))

    def test_one_issue_with_duplicate(self):
        self.assertEqual([], list(self.tracker.errors('DummyFile')))

        comment = Struct(body='_[farcy \n* MatchingError', path='DummyFile',
                         position=16)
        self.tracker.from_github_comments([comment])

        self.assertEqual(1, self.tracker.github_message_count)
        self.assertEqual(0, self.tracker.hidden_issue_count)
        self.assertEqual(0, self.tracker.new_issue_count)
        self.assertEqual([], list(self.tracker.errors('DummyFile')))

        self.tracker.track('MatchingError', 'DummyFile', 16)
        self.assertEqual(1, self.tracker.github_message_count)
        self.assertEqual(0, self.tracker.hidden_issue_count)
        self.assertEqual(1, self.tracker.new_issue_count)
        self.assertEqual([], list(self.tracker.errors('DummyFile')))

    def test_one_unique_issue__different_line(self):
        comment = Struct(body='_[farcy \n* MatchingError', path='DummyFile',
                         position=16)
        self.tracker.from_github_comments([comment])
        self.tracker.track('MatchingError', 'DummyFile', 16)
        self.tracker.track('Non MatchingError', 'DummyFile', 17)

        self.assertEqual(1, self.tracker.github_message_count)
        self.assertEqual(2, self.tracker.new_issue_count)
        self.assertEqual([(17, ['Non MatchingError'])],
                         list(self.tracker.errors('DummyFile')))

    def test_one_unique_issue__same_line(self):
        comment = Struct(body='_[farcy \n* MatchingError', path='DummyFile',
                         position=16)
        self.tracker.from_github_comments([comment])
        self.tracker.track('MatchingError', 'DummyFile', 16)
        self.tracker.track('Non MatchingError', 'DummyFile', 16)

        self.assertEqual(1, self.tracker.github_message_count)
        self.assertEqual(2, self.tracker.new_issue_count)
        self.assertEqual([(16, ['Non MatchingError'])],
                         list(self.tracker.errors('DummyFile')))

    def test_only_hidden_issues(self):
        comment = Struct(body='_[farcy \n* MatchingError', path='DummyFile',
                         position=0)
        self.tracker.from_github_comments([comment])

        self.assertEqual(0, self.tracker.github_message_count)
        self.assertEqual(1, self.tracker.hidden_issue_count)
        self.assertEqual(0, self.tracker.new_issue_count)
        self.assertEqual([], list(self.tracker.errors('DummyFile')))
