"""Helper methods and classes."""

from github3 import GitHub
from github3.exceptions import GitHubError
import os
import sys
from .const import NUMBER_RE, CONFIG_DIR
from .exceptions import FarcyException

if sys.version_info >= (3, 0):
    basestring = str


def added_lines(patch):
    """Return a mapping of added line numbers to the patch line numbers."""
    added = {}
    lineno = None
    position = 0
    for line in patch.split('\n'):
        if line.startswith('@@'):
            lineno = int(NUMBER_RE.match(line.split('+')[1]).group(1))
        elif line.startswith(' '):
            lineno += 1
        elif line.startswith('+'):
            added[lineno] = position
            lineno += 1
        elif line == "\ No newline at end of file":
            continue
        else:
            assert line.startswith('-')
        position += 1
    return added


def ensure_config_dir():
    """Ensure Farcy config dir exists."""
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, mode=0o700)


def get_session():
    """Fetch and/or load API authorization token for GITHUB."""
    ensure_config_dir()
    credential_file = os.path.join(CONFIG_DIR, 'github_auth')
    if os.path.isfile(credential_file):
        with open(credential_file) as fd:
            token = fd.readline().strip()
        gh = GitHub(token=token)
        try:  # Test connection before starting
            gh.is_starred('github', 'gitignore')
            return gh
        except GitHubError as exc:
            raise_unexpected(exc.code)
            sys.stderr.write('Invalid saved credential file.\n')

    from getpass import getpass
    from github3 import authorize

    user = prompt('GITHUB Username')
    try:
        auth = authorize(
            user, getpass('Password for {0}: '.format(user)), 'repo',
            'Farcy Code Reviewer',
            two_factor_callback=lambda: prompt('Two factor token'))
    except GitHubError as exc:
        raise_unexpected(exc.code)
        raise FarcyException(exc.message)

    with open(credential_file, 'w') as fd:
        fd.write('{0}\n{1}\n'.format(auth.token, auth.id))
    return GitHub(token=auth.token)


def parse_bool(value):
    """Return whether or not value represents a True or False value."""
    if isinstance(value, basestring):
        return value.lower() in ['1', 'on', 't', 'true', 'y', 'yes']
    return bool(value)


def parse_set(item_or_items, normalize=False):
    """Return a set of unique tokens in item_or_items.

    :param item_or_items: Can either be a string, or an iterable of strings.
      Each string can contain one or more items separated by commas, these
      items will be expanded, and empty tokens will be removed.
    :param normalize: When true, lowercase all tokens.

    """
    if isinstance(item_or_items, basestring):
        item_or_items = [item_or_items]

    items = set()
    for item in item_or_items:
        for token in (x.strip() for x in item.split(',') if x.strip()):
            items.add(token.lower() if normalize else token)
    return items if items else None


def plural(items, word):
    """Return number of items followed by the right form  of ``word``.

    ``items`` can either be an int or an object whose cardinality can be
    discovered via `len(items)`.

    The plural of ``word`` is assumed to be made by adding an ``s``.

    """
    item_count = items if isinstance(items, int) else len(items)
    word = word if item_count == 1 else word + 's'
    return '{0} {1}'.format(item_count, word)


def prompt(msg):
    """Output message and return striped input."""
    sys.stdout.write('{0}: '.format(msg))
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def raise_unexpected(code):
    """Called from with in an except block.

    Re-raises the exception if we don't know how to handle it.

    """
    if code != 401:
        raise
