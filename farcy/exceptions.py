"""Defines the exceptions used in the farcy package."""


class FarcyException(Exception):
    """Farcy root exception class."""

    def __str__(self):
        """Return the exception's class name."""
        retval = super(FarcyException, self).__str__()
        return retval or self.__class__.__name__


class HandlerException(FarcyException):
    """Farcy handler primary exception."""


class HandlerNotReady(HandlerException):
    """Exception indicating that a handler is not ready for use."""
