"""Defines handlers for various file types."""

from subprocess import CalledProcessError, check_output
import json
import logging
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
    upon via the ``EXTS`` class method.
    """

    EXTS = []

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
        raise HandlerException('Base class `ExtHandler` is never usable.')

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


class Rubocop(ExtHandler):

    """Provides feedback for ruby files using rubocop."""

    EXTS = ['.rb']

    def assert_usable(self):
        """Test that rubocop is available and its version is sufficient."""
        try:
            version = check_output(['rubocop', '--version'], stderr=DEVNULL)
        except OSError as exc:
            if exc.errno == 2:
                raise HandlerException('rubocop is not installed')
            raise  # Unexpected and unhandled exception
        if version:
            raise HandlerException('Invalid version of rubocop: {0}'
                                   .format(version))

    def _process(self, filename):
        try:
            output = check_output(['rubocop', '-f', 'j', filename])
        except CalledProcessError as exc:
            output = exc.output
        return json.loads(output)
