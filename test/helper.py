"""Farcy test helpers."""


class Struct(object):
    """A dynamic class with attributes based on the input dictionary."""

    def __init__(self, iterable=None, **attrs):
        """Create an instance of the Struct class."""
        self.__dict__.update(attrs)
        self._iterable = iterable or []

    def __getitem__(self, index):
        """Return the value of the attribute ``index``."""
        return self._iterable[index]

    def refresh(self):
        """Dummy function to reload this instance"""
        return self
