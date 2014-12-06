"""Defines handlers for various file types."""

from subprocess import CalledProcessError, check_output
import json
import logging
from update_checker import parse_version
from .exceptions import HandlerException


# src: http://stackoverflow.com/a/11270665/176978
try:
    from subprocess import DEVNULL
except ImportError:
    import os
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

    @staticmethod
    def execute(args):
        """Return output of argument execution ignoring status code."""
        try:
            return check_output(args, stderr=DEVNULL).decode('utf-8')
        except CalledProcessError as exc:
            return exc.output

    @classmethod
    def verify_version(cls, installed, exact=False):
        """Raise HandlerException if the installed version does not match.

        :param installed: The installed version number.
        :param exact: Raise HandlerException when there is not an exact
            match. Note that 0.27.0 is considered exact to 0.27.
        """
        if ' ' in installed:
            logging.getLogger(__name__).debug(
                'Version string contains space: {0}'.format(installed))
        exp = parse_version(cls.BINARY_VERSION)
        inp = parse_version(installed)
        op = None
        if exact and exp != inp:
            op = ''
        elif exp > inp:
            op = '>= '
        if op is not None:
            raise HandlerException(
                'Expected {0} {1}{2}, found {installed}'
                .format(cls.BINARY, op, cls.BINARY_VERSION, installed))

    def __init__(self, on_demand=False):
        """A handler's constructor is called only once upon farcy start-up.

        :param on_demand: When true, plugins that are not usable on start-up
            will are still loaded, and will be tested for use on-demand.

        By default this method only calls the ``assert_usable`` instance method
        to see if the plugin's dependencies are available.
        """
        self._logger = logging.getLogger(__name__)
        self.name = type(self).__name__
        try:
            self.assert_usable()
            self._plugin_ready = True
        except HandlerException as exc:
            if not on_demand:
                self._logger.warn('{0} is not ready: {1}'
                                  .format(self.name, exc.message))
                raise
            self._plugin_ready = False

    def assert_usable(self):
        """Raise HandlerException if the handler is not ready for use."""
        if self.name == 'ExtHandler':
            raise HandlerException('Base class `ExtHandler` is never usable.')
        if not self.BINARY:
            raise HandlerException('{0} does not have a binary specified.'
                                   .format(self.name))
        try:
            version = (check_output([self.BINARY, '--version'], stderr=DEVNULL)
                       .decode('utf-8'))
        except OSError as exc:
            if exc.errno == 2:
                raise HandlerException('{0} is not installed'
                                       .format(self.BINARY))
            raise  # Unexpected and unhandled exception
        self.verify_version(self.version_callback(version))

    def process(self, filename):
        """Return the complete results of the handler against the file.

        :param filename: The filename to analyze.
        """
        # This method should not be implemented by a subclass. Use _process
        # instead.
        if not self._plugin_ready:
            try:
                self.assert_usable()
                self._plugin_ready = True
            except HandlerException as exc:
                self._logger.warn('{0} is not ready: {1}'
                                  .format(self.name, exc.message))
                return {}
        return self._process(filename)

    def version_callback(self, version):
        """Return a parsed version string for the binary version."""
        return version.strip()


class Flake8(ExtHandler):

    """Provides feedback for python files using flake8."""

    BINARY = 'flake8'
    BINARY_VERSION = '2.2.3'
    EXTENSIONS = ['.py']

    def _process(self, filename):
        return self.execute([self.BINARY, filename])

    def version_callback(self, version):
        """Remove the extra version information."""
        return version.split(' ', 1)[0]


class Pep257(ExtHandler):

    """Provides feedback for python files using pep257."""

    BINARY = 'pep257'
    BINARY_VERSION = '0.3.2'
    EXTENSIONS = ['.py']

    def _process(self, filename):
        return self.execute([self.BINARY, filename])


class Rubocop(ExtHandler):

    """Provides feedback for ruby files using rubocop."""

    BINARY = 'rubocop'
    BINARY_VERSION = '0.27'
    EXTENSIONS = ['.rb']

    def _process(self, filename):
        return json.loads(self.execute([self.BINARY, '-f', 'j', filename]))
