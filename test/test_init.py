"""Farcy test file."""

from __future__ import print_function
import unittest
import farcy


class MockComment(object):
    """Imitates a review comment."""

    def __init__(self, body=None, path=None, position=None, issues=None):
        if issues:
            body = '\n'.join([farcy.FARCY_COMMENT_START] +
                             ['* ' + issue for issue in issues])
        self.body = body
        self.path = path
        self.position = position


class CommentFunctionTest(unittest.TestCase):

    """Tests common Farcy handler extension methods."""
    def test_is_farcy_comment_detects_farcy_comment(self):
        self.assertTrue(farcy.is_farcy_comment(MockComment(
            issues=['Hello issue']).body))

    def test_is_farcy_comment_detects_if_not_farcy_comment(self):
        self.assertFalse(farcy.is_farcy_comment(MockComment(
            'Just a casual remark by not Farcy').body))

    def test_filter_comments_from_farcy(self):
        farcy_comment = MockComment(issues=['A issue'])
        normal_comment = MockComment('Casual remark')

        self.assertEqual(
            [farcy_comment],
            list(farcy.filter_comments_from_farcy(
                [normal_comment, farcy_comment])))

    def test_filter_comments_by_path(self):
        comment = MockComment('Casual remark', path='this/path')
        comment2 = MockComment('Why not like this', path='that/path')

        self.assertEqual(
            [comment2],
            list(farcy.filter_comments_by_path(
                [comment, comment2], 'that/path')))

    def test_extract_issues(self):
        issues = ['Hello', 'World']
        comment = MockComment(issues=issues)

        self.assertEqual(issues, farcy.extract_issues(comment.body))

    def test_issues_by_line_filters_non_farcy_comments(self):
        issues = ['Hello', 'World']
        issues2 = ['More', 'Issues']
        comment = MockComment(issues=issues, path='test.py', position=1)
        comment2 = MockComment(issues=issues2, path='test.py', position=1)
        comment3 = MockComment('hello world', path='test.py', position=1)

        self.assertEqual(
            {1: issues+issues2},
            farcy.issues_by_line([comment, comment2, comment3], 'test.py'))

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
            farcy.subtract_issues_by_line(issues, existing))
