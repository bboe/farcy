"""Farcy test helpers."""

class Struct(object):
    def __init__(self, iterable=None, **attrs):
        self.__dict__.update(attrs)
        self._iterable = iterable or []

    def __getitem__(self, index):
            return self._iterable[index]
