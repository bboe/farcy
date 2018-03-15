"""Defines handlers for various file types."""

from __future__ import print_function
from collections import defaultdict
from subprocess import CalledProcessError, STDOUT, check_output
from update_checker import parse_version
import json
import logging
import os
import re
from .const import CONFIG_DIR
from .exceptions import HandlerException, HandlerNotReady


# src: http://stackoverflow.com/a/11270665/176978
try:
    from subprocess import DEVNULL
except ImportError:
    DEVNULL = open(os.devnull, 'wb')


class ExtHandler(object):
    """An abstract class that provides the file handler interface.

    Subclasses must define the extension(s) that the class provides feedback
    upon via the ``EXTENSIONS`` class method.

    ``BINARY`` is the name of an executable binary to look for.
    ``BINARY_VERSION`` is version of the binary expected.

    """

    BINARY = None
    BINARY_VERSION = None
    EXTENSIONS = []
    OUTPUT = 'stdout'

    @staticmethod
    def execute(args, stderr=DEVNULL):
        """Return output of argument execution ignoring status code."""
        try:
            return check_output(args, stderr=stderr).decode('utf-8')
        except CalledProcessError as exc:
            return exc.output.decode('utf-8')

    @classmethod
    def verify_version(cls, installed, exact=False):
        """Raise HandlerException if the installed version does not match.

        :param installed: The installed version number.
        :param exact: Raise HandlerException when there is not an exact
            match. Note that 0.27.0 is considered exact to 0.27.

        """
        exp = parse_version(cls.BINARY_VERSION)
        inp = parse_version(installed)
        op = None
        if exact and exp != inp:
            op = ''
        elif exp > inp:
            op = '>= '
        if op is not None:
            raise HandlerException(
                'Expected {0} {1}{2}, found {3}'
                .format(cls.BINARY, op, cls.BINARY_VERSION, installed))

    def __init__(self, on_demand=False):
        """A handler's constructor is called only once upon farcy start-up.

        :param on_demand: When true, plugins that are not usable on start-up
            are still loaded, and will be tested for use on-demand.

        By default this method only calls the ``assert_usable`` instance method
        to see if the plugin's dependencies are available.

        """
        self._logger = logging.getLogger(__name__)
        self.name = type(self).__name__
        try:
            self.assert_usable()
            self._plugin_ready = True
        except HandlerNotReady as exc:
            if on_demand:
                self._logger.warning('{0} is not ready: {1}'
                                     .format(self.name, str(exc)))
            else:
                raise
            self._plugin_ready = False
        path = os.path.join(
            CONFIG_DIR, 'handler_{0}.conf'.format(self.name.lower()))
        self.config_file_path = path if os.path.isfile(path) else None

    def _regex_parse(self, binary_args, stderr=None):
        """Use the sublcasses RE value to parse the returned data."""
        retval = defaultdict(list)
        for (lineno, msg) in self.RE.findall(self.execute(
                [self.BINARY] + binary_args, stderr=stderr)):
            retval[int(lineno)].append(msg)
        return retval

    def assert_usable(self):
        """Raise HandlerException if the handler is not ready for use."""
        if self.name == 'ExtHandler':
            raise HandlerException('Base class `ExtHandler` must be extended.')
        if not self.BINARY:
            raise HandlerException('{0} does not have a binary specified.'
                                   .format(self.name))
        try:
            version = (check_output([self.BINARY, '--version'], stderr=STDOUT)
                       .decode('utf-8'))
        except OSError as exc:
            if exc.errno == 2:
                raise HandlerNotReady('{0} is not installed.'
                                      .format(self.BINARY))
            elif exc.errno == 13:
                raise HandlerException('{0} cannot be executed.'
                                       .format(self.BINARY))
            raise  # Unexpected and unhandled exception
        self.verify_version(self.version_callback(version))

    def process(self, filename):
        """Return a dictionary mapping line numbers to errors.

        The value for each line number in the dictionary should be a list where
        each item of the list is a string containing an error that occurred on
        the line.

        :param filename: The filename to analyze.

        """
        # This method should not be implemented by a subclass. Use _process
        # instead.
        if not self._plugin_ready:
            try:
                self.assert_usable()
                self._plugin_ready = True
            except HandlerNotReady as exc:
                self._logger.warning('{0} is not ready: {1}'
                                     .format(self.name, exc.message))
                return {}
        return self._process(filename)

    def version_callback(self, version):
        """Return a parsed version string for the binary version."""
        return version.strip()


class ESLint(ExtHandler):
    """Provides feedback for JavaScript files using ESLint."""

    BINARY = 'eslint'
    BINARY_VERSION = '1.1.0'
    EXTENSIONS = ['.js', '.jsx']

    def _process(self, filename):
        command = [self.BINARY, '--format', 'json']
        config_path = self.config_file_path
        if config_path:
            command += ['--config', config_path]

        data = json.loads(self.execute(command + [filename]))[0]
        retval = defaultdict(list)

        for offense in data['messages']:
            message = offense['message']
            if offense.get('ruleId'):
                message += ' ({})'.format(offense['ruleId'])
            retval[offense['line']].append(message)
        return retval

    def version_callback(self, version):
        """Remove the 'v' prefix and trailing space."""
        return version[1:].strip()


class Flake8(ExtHandler):
    """Provides feedback for python files using flake8."""

    BINARY = 'flake8'
    BINARY_VERSION = '2.4.1'
    EXTENSIONS = ['.py']
    RE = re.compile('[^:]+:(\d+):([^\n]+)\n')

    def _process(self, filename):
        config_path = self.config_file_path
        command = ['--config', config_path] if config_path else []
        return self._regex_parse(command + [filename])

    def version_callback(self, version):
        """Remove the extra version information."""
        return version.split(' ', 1)[0]


class JSXHint(ExtHandler):
    """Provides feedback for JS/JSX files using jsxhint."""

    BINARY = 'jsxhint'
    BINARY_VERSION = '0.15.0'
    EXTENSIONS = ['.jsx', '.js']
    RE = re.compile('.*:(\d+):\d+: (.*)\n')

    def _process(self, filename):
        command = ['--reporter', 'unix']
        config_path = self.config_file_path
        if config_path:
            command += ['--config', config_path]
        return self._regex_parse(command + [filename])

    def version_callback(self, version):
        """Return a parsed version string for the binary version."""
        return version.split(' ')[1][1:] if ' ' in version else ''


class Pep257(ExtHandler):
    """Provides feedback for python files using pep257."""

    BINARY = 'pep257'
    BINARY_VERSION = '0.5.0'
    EXTENSIONS = ['.py']
    RE = re.compile('[^:]+:(\d+)[^\n]+\n\s+([^\n]+)\n')

    def _process(self, filename):
        return self._regex_parse([filename], stderr=STDOUT)


class Rubocop(ExtHandler):
    """Provides feedback for ruby files using rubocop."""

    BINARY = 'rubocop'
    BINARY_VERSION = '0.50'
    EXTENSIONS = ['.rb']

    def _process(self, filename):
        command = [self.BINARY, '-f', 'j']
        config_path = self.config_file_path
        if config_path:
            command += ['-c', config_path]

        data = json.loads(self.execute(command + [filename]))
        retval = defaultdict(list)
        for offense in data.get('files', [{}])[0].get('offenses', []):
            retval[offense['location']['line']].append(offense['message'])
        return retval


class SCSSLint(ExtHandler):
    """Provides feedback for css and scss files using scss-lint."""

    BINARY = 'scss-lint'
    BINARY_VERSION = '0.43.2'
    EXTENSIONS = ['.css', '.scss']

    def _process(self, filename):
        command = [self.BINARY, '-f', 'JSON']
        config_path = self.config_file_path
        if config_path:
            command += ['-c', config_path]

        data = json.loads(self.execute(command + [filename]))

        retval = defaultdict(list)
        if not data.values():
            return retval
        for offense in next(iter(data.values())):
            if 'linter' not in offense:
                exception_message = (
                    "Error occurred during linting: {reason} "
                    "(line {line}, column {column})"
                ).format(**offense)
                raise HandlerException(exception_message)
            retval[offense['line']].append(
                '{linter}: {reason}'.format(**offense)
            )

        return retval

    def version_callback(self, version):
        """
        Return a parsed version string for the binary version.

        This returns just the semantic versioned portion of the version string.
        """
        return version.split()[1]
