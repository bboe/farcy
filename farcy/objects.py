"""Defines the standard objects used by Farcy."""

try:
    from configparser import ConfigParser  # PY3
except ImportError:
    from ConfigParser import SafeConfigParser as ConfigParser  # PY2

from datetime import timedelta, tzinfo
import logging
import os
import re
from .const import CONFIG_DIR, FARCY_COMMENT_START
from .exceptions import FarcyException
from .helpers import get_session, parse_bool, parse_set


class Config(object):

    """Holds configuration for Farcy."""

    ATTRIBUTES = {'debug', 'exclude_paths', 'limit_users', 'log_level',
                  'pr_issue_report_limit', 'pull_requests', 'start_event'}
    LOG_LEVELS = {'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'}
    PATH = os.path.join(CONFIG_DIR, 'farcy.conf')

    @property
    def log_level_int(self):
        """Int value of the log level."""
        return getattr(logging, self.log_level)

    @property
    def session(self):
        """Return GitHub session. Create if necessary."""
        if self._session is None:
            self._session = get_session()
        return self._session

    def __init__(self, repository, **overrides):
        """Initialize a config with default values."""
        self._session = None
        self.repository = repository
        self.set_defaults()
        self.load_config_file()
        self.override(**overrides)

    def __repr__(self):
        """String representation of the config."""
        keys = sorted(x for x in self.__dict__ if not x.startswith('_')
                      and x != 'repository')
        arg_fmt = ', '.join(['{0}={1!r}'.format(key, getattr(self, key))
                             for key in keys])
        return 'Config({0!r}, {1})'.format(self.repository, arg_fmt)

    def __setattr__(self, attr, value):
        """
        Set new config attribute.

        Validates new attribute values and tracks if changed from default.

        """
        if attr == 'debug' and parse_bool(value):
            # Force log level when in debug mode
            setattr(self, 'log_level', 'DEBUG')
        elif attr in ('exclude_paths', 'pull_requests'):
            if value is not None:
                value = parse_set(value)
        elif attr == 'limit_users':
            if value:
                value = parse_set(value, normalize=True)
        elif attr == 'log_level' and self.debug:
            return  # Don't change level in debug mode
        elif attr == 'log_level' and value is not None:
            value = value.upper()
            if value not in self.LOG_LEVELS:
                raise FarcyException('Invalid log level: {0}'.format(value))
        elif attr == 'repository' and value is not None:
            repo_parts = value.split('/')
            if len(repo_parts) != 2:
                raise FarcyException('Invalid repository: {0}'.format(value))
        elif attr in ('pr_issue_report_limit', 'start_event'):
            if value is not None:
                value = int(value)
        super(Config, self).__setattr__(attr, value)

    def load_config_file(self):
        """Load value overrides from configuration file."""
        if not os.path.isfile(self.PATH):
            return

        config_file = ConfigParser()
        config_file.read(self.PATH)

        if not self.repository and \
                config_file.has_option('DEFAULT', 'repository'):
            self.repository = config_file.get('DEFAULT', 'repository')

        self.override(**dict(config_file.items(
            self.repository if config_file.has_section(self.repository)
            else 'DEFAULT')))

    def override(self, **overrides):
        """Override the config values passed as keyword arguments."""
        for attr, value in overrides.items():
            if attr in self.ATTRIBUTES and value:
                setattr(self, attr, value)

    def set_defaults(self):
        """Set the default config values."""
        self.debug = False
        self.exclude_paths = None
        self.limit_users = None
        self.log_level = 'ERROR'
        self.pr_issue_report_limit = 128
        self.pull_requests = None
        self.start_event = None

    def user_whitelisted(self, user):
        """Return if user is whitelisted."""
        return self.limit_users is None or user.lower() in self.limit_users


class ErrorMessage(object):

    """An error message keeps track the lines a single error appears on."""

    GROUP_THRESHOLD = 3  # lines

    def __init__(self, message):
        """Initialize an ErrorMessage object."""
        self.groups = set()
        self.lines = {}  # Value is true when it's on github
        self.message = message

    def messages(self):
        """Yield a tuple containing (line, message).

        Messages near each other will be grouped and the message will indicate
        how many lines are covered by the message.

        """
        def output(start, count, span):
            if count > 1:
                return (start, '{0} <sub>{1}x spanning {2} lines</sub>'
                        .format(self.message, count, span + 1))
            return (start, self.message)

        start = last = None
        count = 0
        for line, skip in sorted(self.lines.items()):
            if skip:
                continue
            if start is None:
                start = last = line
            if line - last >= self.GROUP_THRESHOLD:
                if (start, count) not in self.groups:
                    yield output(start, count, last - start)
                count = 0
                start = line
            count += 1
            last = line
        if start and (start, count) not in self.groups:
            yield output(start, count, last - start)

    def track(self, line, on_github=False):
        """Track the line and return self."""
        self.lines[line] = self.lines.get(line, False) or on_github
        return self

    def track_group(self, line, count):
        """Record a grouping for this message that is on github."""
        self.groups.add((line, count))
        return self


class ErrorTracker(object):

    """Track ErrorMessages across multiple files."""

    FARCY_PREFIX = FARCY_COMMENT_START.split('v')[0]
    GROUP_MATCH = re.compile('(.+) <sub>(\d+)x spanning \d+ lines</sub>')

    @classmethod
    def _parse_group_message(cls, message):
        match = cls.GROUP_MATCH.match(message)
        return match.groups() if match else None

    def __init__(self, github_comments):
        """Initialize an ErrorTracker object."""
        self.by_file = {}
        self.github_message_count = 0
        self.new_issue_count = 0
        self.from_github_comments(github_comments)

    def errors(self, filename):
        """Generate tuples containing (line, [errors...])."""
        by_line = {}
        for error in self.by_file.get(filename, {}).values():
            for line, message in error.messages():
                by_line.setdefault(line, []).append(message)
        for line in sorted(by_line):
            yield (line, sorted(by_line[line]))

    def from_github_comments(self, comments):
        """Populate the error tracker with Farcy comments from github."""
        for comment in comments:
            if not comment.body.startswith(self.FARCY_PREFIX):
                continue
            self.github_message_count += 1
            for issue in comment.body.split('\n')[1:]:
                self.track(issue[2:], comment.path, comment.position, True)

    def track(self, message, filename, line, is_github=False):
        """Track message in filename on line."""
        parts = self._parse_group_message(message)
        if parts:
            message = parts[0]

        error_message = self.by_file.setdefault(filename, {}).setdefault(
            message, ErrorMessage(message))

        if parts:
            error_message.track_group(line, parts[1])
        else:
            if not is_github:
                self.new_issue_count += 1
            error_message.track(line, is_github)


class UTC(tzinfo):

    """Provides a simple UTC timezone class.

    Source: http://docs.python.org/release/2.4.2/lib/datetime-tzinfo.html

    """

    dst = lambda x, y: timedelta(0)
    tzname = lambda x, y: 'UTC'
    utcoffset = lambda x, y: timedelta(0)
