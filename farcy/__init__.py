#!/usr/bin/env python

"""Farcy, a code review bot for github pull requests.

Usage: farcy.py [-D | --logging=LEVEL] WATCH_OWNER WATCH_REPOSITORY

Options:

  -D               Enable all log output (shortcut for: --logging=DEBUG).
  --logging=LEVEL  Specify the price log level to output.
  -h, --help       Show this screen.
  --version        Show the program's version.

"""

from __future__ import print_function
from collections import defaultdict
from datetime import datetime, timedelta, tzinfo
from docopt import docopt
from github3 import GitHub
from update_checker import UpdateChecker
import logging
import os
import re
import stat
import sys
import tempfile
import time
from .exceptions import FarcyException, HandlerException


"""
TODO:

* Don't comment if already commented
* Adjust rubocop settings

"""

__version__ = '0.1b'
NUMBER_RE = re.compile('(\d+)')
VERSION_STR = 'farcy v{0}'.format(__version__)


# Hack to be forward compatible with github3 v 1.0
# Delete once github3 v1.0 is released
from github3 import __version__ as gh_version
if gh_version.startswith('0'):
    from github3.repos import Repository
    Repository.pull_requests = Repository.iter_pulls
    Repository.events = Repository.iter_events
    del Repository
    from github3.pulls import PullRequest
    PullRequest.files = PullRequest.iter_files
    from github3.models import GitHubError
else:
    from github3.exceptions import GitHubError


class UTC(tzinfo):

    """Provides a simple UTC timezone class.

    Source: http://docs.python.org/release/2.4.2/lib/datetime-tzinfo.html

    """

    dst = lambda x, y: timedelta(0)
    tzname = lambda x, y: 'UTC'
    utcoffset = lambda x, y: timedelta(0)


START_TIME = datetime.now(UTC()) - timedelta(days=1)


class Farcy(object):

    """A bot to automate some code-review processes on GitHub pull requests."""

    EVENTS = {'PullRequestEvent', 'PushEvent'}
    _update_checked = False

    @staticmethod
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
            else:
                assert line.startswith('-')
            position += 1
        return added

    @staticmethod
    def get_session():
        """Fetch and/or load API authorization token for GITHUB."""
        credential_file = os.path.expanduser('~/.config/farcy')
        if os.path.isfile(credential_file):
            with open(credential_file) as fd:
                token = fd.readline().strip()
            gh = GitHub(token=token)
            try:  # Test connection before starting
                gh.is_starred('github', 'gitignore')
                return gh
            except GitHubError as exc:
                if exc.code != 401:
                    raise  # Unexpected and unhandled exception
                sys.stderr.write('Invalid saved credential file.\n')

        from getpass import getpass
        from github3 import authorize

        user = Farcy.prompt('GITHUB Username')
        try:
            auth = authorize(
                user, getpass('Password for {0}: '.format(user)), 'repo',
                'Farcy Code Reviewer',
                two_factor_callback=lambda: Farcy.prompt('Two factor token'))
        except GitHubError as exc:
            if exc.code == 401:
                raise FarcyException(exc.message)
            raise  # Unexpected and unhandled exception

        with open(credential_file, 'w') as fd:
            fd.write('{0}\n{1}\n'.format(auth.token, auth.id))
        return GitHub(token=auth.token)

    @staticmethod
    def prompt(msg):
        """Output message and return striped input."""
        sys.stdout.write('{0}: '.format(msg))
        sys.stdout.flush()
        return sys.stdin.readline().strip()

    def __init__(self, owner, repository, log_level=None):
        """Initialize an instance of Farcy that monitors owner/repository."""
        # Configure logging
        self.log = logging.getLogger(__name__)
        if log_level:
            try:
                level = int(getattr(logging, log_level.upper()))
            except (AttributeError, ValueError):
                raise FarcyException('Invalid log level: {0}'
                                     .format(log_level))

            self.log.setLevel(level)
            self.log.addHandler(logging.StreamHandler())
        else:
            self.log.setLevel(logging.NOTSET)

        self._load_handlers()

        # Initialize the repository to monitor
        self.repo = self.get_session().repository(owner, repository)
        if self.repo is None:
            raise FarcyException('Invalid owner or repository name: {0}/{1}'
                                 .format(owner, repository))
        # Keep track of open pull requests
        self.open_prs = {}
        for pr in self.repo.pull_requests(state='all'):
            if pr.state == 'open':
                self.open_prs[pr.head.ref] = pr

        # Check for farcy package updates
        if not self._update_checked:
            result = UpdateChecker().check(__name__, __version__)
            if result:
                self.log.info(result)
            self._update_checked = True

    def _load_handlers(self):
        from . import handlers
        self._ext_to_handler = defaultdict(list)
        for handler in (handlers.Rubocop,):
            try:
                handler_inst = handler()
            except HandlerException:
                continue
            for ext in handler.EXTENSIONS:
                self._ext_to_handler[ext].append(handler_inst)

    def event_iterator(self):
        """Yield repository events in order."""
        id_marker = None
        etag = None
        sleep_time = 8  # This value will be overwritten
        while True:
            # Fetch events
            events = []
            itr = self.repo.events(etag=etag)
            itr_first_id = None
            for event in itr:
                itr_first_id = itr_first_id or int(event.id)

                # Stop when we've already seen something
                if id_marker and int(event.id) < id_marker or \
                   event.created_at < START_TIME:
                    break

                # Add relevent events in reverse order
                if event.type in self.EVENTS:
                    events.insert(0, event)

            etag = itr.etag
            id_marker = itr_first_id or id_marker

            # Yield events from oldest to newest
            for event in events:
                yield event

            # Sleep the amount of time indicated in the API response
            sleep_time = int(itr.last_response.headers.get('X-Poll-Interval',
                                                           sleep_time))
            sleep_time = 8
            self.log.debug('Sleeping for {0} seconds.'.format(sleep_time))
            time.sleep(sleep_time)

    def get_issues(self, pfile):
        """Return a dictionary of issues for the file."""
        ext = os.path.splitext(pfile.filename)
        handlers = self._ext_to_handler.get(ext)
        if not handlers:  # Do nothing if there are no handlers
            return {}
        retval = {}
        stream = pfile._session.get(pfile.raw_url, stream=True)
        with tempfile.NamedTemporaryFile() as fp:
            for chunk in stream.iter_content(chunk_size=1024):
                if chunk:
                    fp.write(chunk)
                    fp.flush()
                # Prevent modification by handlers
                os.chmod(fp.name, stat.S_IRUSR)
            for handler in handlers:
                retval.update(handler.process(fp.name))
        return retval

    def handle_pr(self, pr):
        """Provide code review on pull request."""
        if pr is None or pr.state != 'open':  # Ignore closed PRs
            self.log.info('Handle PR called on {0} pull request: {1}'
                          .format(pr.state, pr))
            return
        self.log.info('Handling PR: {0}'.format(pr))

        if gh_version.startswith('0'):
            # TODO: Remove this with github3 v1.0
            commits = pr.iter_commits
        else:
            commits = pr.commits
        sha = list(commits())[-1].sha
        issue_count = 0
        did_work = True
        for pfile in pr.files():
            added = None
            if pfile.status == 'deleted':  # Ignore deleted files
                self.log.debug('Ignoring deleted file: {0}'
                               .format(pfile.filename))
                continue
            elif pfile.patch is None:  # Ignore files without changes
                self.log.debug('Ignoring {0} file without change: {1}'
                               .format(pfile.status, pfile.filename))
                continue
            elif pfile.status == 'modified':
                # Only report issues on the changed lines
                added = self.added_lines(pfile.patch)
                assert added
            else:
                print(pfile.status)
                assert False
            did_work = True

            issues = self.get_issues(pfile)
            by_line = {}
            for offense in issues.get('files', [{}])[0].get('offenses', []):
                lineno = offense['location']['line']
                if added is None or lineno in added:
                    msgs = by_line.setdefault(lineno, [])
                    if not msgs:
                        msgs.append('_{0}_\n'.format(VERSION_STR))
                    msgs.append('* {cop_name}: {message}'.format(**offense))
                    issue_count += 1

            for lineno, msgs in sorted(by_line.items()):
                position = added[lineno] if added else lineno
                retval = pr.create_review_comment('\n'.join(msgs), sha,
                                                  pfile.filename, position)
                print(vars(retval))

        msg = '_{0}_ {{0}}'.format(VERSION_STR)
        if issue_count > 0:
            msg = msg.format('found {0} issues'.format(issue_count))
        else:
            msg = msg.format(':+1:')
        if did_work:
            retval = self.repo.issue(pr.number).create_comment(msg)
            self.log.info('Commented "{0}": {1}'.format(msg, retval.html_url))

    def PullRequestEvent(self, event):
        """Check commits on new pull requests."""
        pr = event.payload['pull_request']
        action = event.payload['action']
        self.log.debug('{0} on {1}'.format(action, pr.head.ref))
        if action == 'closed':
            if pr.head.ref in self.open_prs:
                del self.open_prs[pr.head.ref]
            else:
                self.log.warn('open_prs did not contain {0}'
                              .format(pr.head.ref))
        elif action == 'opened':
            self.open_prs[pr.head.ref] = pr
            self.handle_pr(pr)
        elif action == 'reopened':
            self.open_prs[pr.head.ref] = pr

    def PushEvent(self, event):
        """Check push commits only to open pull requests."""
        ref = event.payload['ref']
        assert ref.startswith('refs/heads/')
        self.handle_pr(self.open_prs.get(ref.rsplit('/', 1)[1]))

    def run(self):
        """Run the bot until ctrl+c is received."""
        self.log.info('Monitoring {0}...'.format(self.repo.html_url))
        for event in self.event_iterator():
            getattr(self, event.type)(event)


def main():
    """Provide an entry point into Farcy."""
    args = docopt(__doc__, version=VERSION_STR)
    debug = 'DEBUG' if args['-D'] else args['--logging']

    try:
        Farcy(args['WATCH_OWNER'], args['WATCH_REPOSITORY'], debug).run()
    except KeyboardInterrupt:
        sys.stderr.write('Farcy shutting down. Goodbye!\n')
        return 0
    except FarcyException as exc:
        sys.stderr.write(exc.message + '\n')
        return 1


if __name__ == '__main__':
    sys.exit(main())
