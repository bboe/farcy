"""Constants used throughout Farcy."""
import re

__version__ = '0.1b'
NUMBER_RE = re.compile('(\d+)')
VERSION_STR = 'farcy v{0}'.format(__version__)
MD_VERSION_STR = ('[{0}](https://github.com/appfolio/farcy)'
                  .format(VERSION_STR))
PR_ISSUE_COMMENT_FORMAT = '_{0}_ {{0}}'.format(MD_VERSION_STR)
COMMIT_STATUS_FORMAT = '{0} {{0}}'.format(VERSION_STR)

FARCY_COMMENT_START = '_{}_'.format(MD_VERSION_STR)
