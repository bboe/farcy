"""Farcy class test file."""

from __future__ import print_function
from farcy import Farcy
import unittest


class FarcyTest(unittest.TestCase):
    def test_added_lines(self):
        self.assertEqual({}, Farcy.added_lines('@@+15'))
        self.assertEqual({1: 1}, Farcy.added_lines('@@+1\n+wah'))
        self.assertEqual({15: 1}, Farcy.added_lines('@@+15\n+wah'))
        self.assertEqual({16: 2}, Farcy.added_lines('@@+15\n \n+wah'))
        self.assertEqual({1: 2}, Farcy.added_lines('@@+1\n-\n+wah'))
        self.assertEqual({15: 2}, Farcy.added_lines('@@+15\n-\n+wah'))
        self.assertEqual({16: 3}, Farcy.added_lines('@@+15\n-\n \n+wah'))
        self.assertEqual({1: 1, 15: 3},
                         Farcy.added_lines('@@+1\n+wah\n@@+15\n+foo'))
