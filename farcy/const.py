"""Constants used throughout Farcy."""
import os
import re

__version__ = '0.1'

VERSION_STR = 'farcy v{0}'.format(__version__)

CONFIG_DIR = os.path.expanduser('~/.config/farcy')

MD_VERSION_STR = ('[{0}](https://github.com/appfolio/farcy)'
                  .format(VERSION_STR))

FARCY_COMMENT_START = '_{0}_'.format(MD_VERSION_STR)

NUMBER_RE = re.compile('(\d+)')

STATUS_FORMAT = '{0} {{0}}'.format(VERSION_STR)
