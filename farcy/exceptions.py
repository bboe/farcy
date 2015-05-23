"""Defines the exceptions used in the farcy package."""

from __future__ import print_function


class FarcyException(Exception):

    """Farcy root exception class."""


class HandlerException(FarcyException):

    """Farcy handler primary exception."""


class HandlerNotReady(HandlerException):

    """Exception indicating that a handler is not ready for use."""
