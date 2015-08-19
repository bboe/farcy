"""Farcy test file."""

from __future__ import print_function
import tempfile
import unittest
import farcy.exceptions as exceptions
import farcy.helpers as helpers


class MockComment(object):
    """Imitates a review comment."""

    def __init__(self, body=None, path=None, position=None, issues=None):
        if issues:
            body = '\n'.join([helpers.FARCY_COMMENT_START] +
                             ['* ' + issue for issue in issues])
        self.body = body
        self.path = path
        self.position = position


class ConfigTest(unittest.TestCase):
    """Tests Config helper."""
    def setUp(self):
        self.config = helpers.Config()
        self.tempdir = None

    def test_dirty_checking(self):
        self.config.debug = not self.config.debug
        self.assertEqual(set(['debug']), self.config._dirty)

    def test_not_mark_dirty_if_same_value(self):
        self.config.debug = self.config.debug
        self.assertEqual(set(), self.config._dirty)

    def test_default_repo_from_config(self):
        config = """
[default]
repository: appfolio/farcy
        """

        self._setup_config_file(config)
        self.assertEqual('appfolio/farcy', self.config.repository)

    def test_default_repo_from_config_raise_on_invalid(self):
        config = """
[default]
repository: invalid_repo
        """

        with self.assertRaises(exceptions.FarcyException):
            self._setup_config_file(config)

    def test_config_file_values(self):
        config = """
[default]
repository: appfolio/farcy
start_event: 10
debug: true
exclude_paths: node_modules,vendor
limit_users: balloob,bboe
log_level: DEBUG
pr_issue_report_limit: 100
        """

        self._setup_config_file(config)
        self.assertEqual('appfolio/farcy', self.config.repository)
        self.assertEqual(10, self.config.start_event)
        self.assertEqual(True, self.config.debug)
        self.assertEqual(['node_modules', 'vendor'], self.config.exclude_paths)
        self.assertEqual(set(['balloob', 'bboe']), self.config.limit_users)
        self.assertEqual('DEBUG', self.config.log_level)
        self.assertEqual(100, self.config.pr_issue_report_limit)

    def test_config_file_default_works(self):
        config = """
[default]
start_event: 5
        """

        self._setup_config_file(config)
        self.assertEqual(5, self.config.start_event)

    def test_config_file_repo_specific_works(self):
        config = """
[appfolio/farcy]
start_event: 5
        """

        self.config.repository = 'appfolio/farcy'
        self._setup_config_file(config)
        self.assertEqual(5, self.config.start_event)

    def test_config_file_repo_specific_inherits_default(self):
        config = """
[default]
limit_users: balloob

[appfolio/farcy]
start_event: 5
        """

        self.config.repository = 'appfolio/farcy'
        self._setup_config_file(config)
        self.assertEqual(set(['balloob']), self.config.limit_users)
        self.assertEqual(5, self.config.start_event)

    def test_config_file_only_sets_not_dirty(self):
        config = """
[appfolio/farcy]
start_event: 5
        """

        self.config.start_event = 10
        self._setup_config_file(config)
        self.assertEqual(10, self.config.start_event)

    def test_user_whitelisted_passes_if_not_set(self):
        self.assertTrue(self.config.user_whitelisted('balloob'))

    def test_user_whitelisted_works_if_set(self):
        self.config.limit_users = ['bboe', 'balloob']
        self.assertTrue(self.config.user_whitelisted('balloob'))
        self.assertFalse(self.config.user_whitelisted('appfolio'))

    def test_setting_repo(self):
        repo = 'appfolio/farcy'
        self.config.repository = repo
        self.assertEqual(repo, self.config.repository)

    def test_raise_if_invalid_repository(self):
        with self.assertRaises(exceptions.FarcyException):
            self.config.repository = 'invalid_repo'

    def test_raise_if_invalid_log_level(self):
        with self.assertRaises(exceptions.FarcyException):
            self.config.log_level = 'invalid_log_level'

    def test_cant_change_log_level_if_debug(self):
        self.config.debug = True
        self.assertEqual('DEBUG', self.config.log_level)
        self.config.log_level = 'WARNING'
        self.assertEqual('DEBUG', self.config.log_level)

    def test_setting_values_via_dict(self):
        data = {
            'repository': 'appfolio/farcy',
            'start_event': 1000,
            'debug': False,
            'exclude_paths': ['npm_modules', 'vendor'],
            'limit_users': ['balloob', 'bboe'],
            'log_level': 'WARNING',
            'pr_issue_report_limit': 100
        }

        self.config.load_dict(data)

        for attr, value in data.items():
            self.assertEqual(value, getattr(self.config, attr))


    def _setup_config_file(self, content):
        with tempfile.NamedTemporaryFile() as fil:
            fil.write(content.encode('utf-8'))
            fil.flush()

            self.config._config_path = fil.name
            self.config.load_config_file()


class CommentFunctionTest(unittest.TestCase):

    """Tests common Farcy handler extension methods."""
    def test_is_farcy_comment_detects_farcy_comment(self):
        self.assertTrue(helpers.is_farcy_comment(MockComment(
            issues=['Hello issue']).body))

    def test_is_farcy_comment_detects_if_not_farcy_comment(self):
        self.assertFalse(helpers.is_farcy_comment(MockComment(
            'Just a casual remark by not Farcy').body))

    def test_filter_comments_from_farcy(self):
        farcy_comment = MockComment(issues=['A issue'])
        normal_comment = MockComment('Casual remark')

        self.assertEqual(
            [farcy_comment],
            list(helpers.filter_comments_from_farcy(
                [normal_comment, farcy_comment])))

    def test_filter_comments_by_path(self):
        comment = MockComment('Casual remark', path='this/path')
        comment2 = MockComment('Why not like this', path='that/path')

        self.assertEqual(
            [comment2],
            list(helpers.filter_comments_by_path(
                [comment, comment2], 'that/path')))

    def test_extract_issues(self):
        issues = ['Hello', 'World']
        comment = MockComment(issues=issues)

        self.assertEqual(issues, helpers.extract_issues(comment.body))

    def test_issues_by_line_filters_non_farcy_comments(self):
        issues = ['Hello', 'World']
        issues2 = ['More', 'Issues']
        comment = MockComment(issues=issues, path='test.py', position=1)
        comment2 = MockComment(issues=issues2, path='test.py', position=1)
        comment3 = MockComment('hello world', path='test.py', position=1)

        self.assertEqual(
            {1: issues+issues2},
            helpers.issues_by_line([comment, comment2, comment3], 'test.py'))

    def test_subtract_issues_by_line(self):
        issues = {
            1: ['Hello', 'World'],
            5: ['Line 5', 'Issue'],
            6: ['All', 'Existing']
        }
        existing = {
            1: ['World'],
            2: ['Another existing'],
            5: ['Line 5', 'Beer'],
            6: ['All', 'Existing'],
        }

        self.assertEqual(
            {1: ['Hello'], 5: ['Issue']},
            helpers.subtract_issues_by_line(issues, existing))


class PatchFunctionTest(unittest.TestCase):
    def test_added_lines(self):
        self.assertEqual({}, helpers.added_lines('@@+15'))
        self.assertEqual({1: 1}, helpers.added_lines('@@+1\n+wah'))
        self.assertEqual({15: 1}, helpers.added_lines('@@+15\n+wah'))
        self.assertEqual({16: 2}, helpers.added_lines('@@+15\n \n+wah'))
        self.assertEqual({1: 2}, helpers.added_lines('@@+1\n-\n+wah'))
        self.assertEqual({15: 2}, helpers.added_lines('@@+15\n-\n+wah'))
        self.assertEqual({16: 3}, helpers.added_lines('@@+15\n-\n \n+wah'))
        self.assertEqual({1: 1, 15: 3},
                         helpers.added_lines('@@+1\n+wah\n@@+15\n+foo'))

    def test_added_lines_works_with_github_no_newline_message(self):
        patch = """@@ -0,0 +1,5 @@
+class SomeClass
+  def yo(some_unused_param)
+    puts 'hi'
+  end
+end
\ No newline at end of file"""
        try:
            helpers.added_lines(patch)
        except AssertionError:
            self.fail('added_lines() raised AssertionError')


class PluralTest(unittest.TestCase):
    def test_plural__with_one__int(self):
        self.assertEqual('1 unit', helpers.plural(1, 'unit'))

    def test_plural__with_one__list(self):
        self.assertEqual('1 unit', helpers.plural([1], 'unit'))

    def test_plural__with_two__int(self):
        self.assertEqual('2 units', helpers.plural(2, 'unit'))

    def test_plural__with_two__list(self):
        self.assertEqual('2 units', helpers.plural([1, 2], 'unit'))

    def test_plural__with_zero__int(self):
        self.assertEqual('0 units', helpers.plural(0, 'unit'))

    def test_plural__with_zero__list(self):
        self.assertEqual('0 units', helpers.plural([], 'unit'))


class ProcessUserListTest(unittest.TestCase):
    def test_process_user_list__comma_separated(self):
        self.assertEqual(set(['bar', 'baz', 'foo']),
                         helpers.process_user_list(['foo, bar ,baz']))

    def test_process_user_list__convert_to_lower(self):
        self.assertEqual(set(['hello']), helpers.process_user_list(['HELLO']))

    def test_process_user_list__empty_input(self):
        self.assertEqual(None, helpers.process_user_list([]))

    def test_process_user_list__separate_items(self):
        self.assertEqual(set(['bar', 'foo']),
                         helpers.process_user_list(['foo', 'bar']))


class SplitDictTest(unittest.TestCase):
    def test_split_dict(self):
        test_dict = {1: 'a', 2: 'b', 3: 'c'}

        with_keys, without_keys = helpers.split_dict(test_dict, [1, 2, 3])
        self.assertEqual(test_dict, with_keys)
        self.assertEqual({}, without_keys)

        with_keys, without_keys = helpers.split_dict(test_dict, [])
        self.assertEqual({}, with_keys)
        self.assertEqual(test_dict, without_keys)

        with_keys, without_keys = helpers.split_dict(test_dict, [2, 3])
        self.assertEqual({2: 'b', 3: 'c'}, with_keys)
        self.assertEqual({1: 'a'}, without_keys)
