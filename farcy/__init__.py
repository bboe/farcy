#!/usr/bin/env python

"""Farcy, a code review bot for github pull requests.

Usage: farcy.py [-D | --logging=LEVEL] [options] OWNER REPOSITORY

Options:

  -s ID, --start=ID  The event id to start handling events from.
  -D, --debug        Enable debugging mode. This enables all logging output
                     and prevents the posting of comments.
  --logging=LEVEL    Specify the log level* to output.
  -h, --help         Show this screen.
  --version          Show the program's version.

* Available log levels:
    https://docs.python.org/3/library/logging.html#logging-levels

"""

from __future__ import print_function
from collections import defaultdict
from datetime import datetime, timedelta, tzinfo
from docopt import docopt
from github3 import GitHub
from github3.exceptions import GitHubError
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
MD_VERSION_STR = ('[{0}](https://github.com/appfolio/farcy)'
                  .format(VERSION_STR))


class UTC(tzinfo):

    """Provides a simple UTC timezone class.

    Source: http://docs.python.org/release/2.4.2/lib/datetime-tzinfo.html

    """

    dst = lambda x, y: timedelta(0)
    tzname = lambda x, y: 'UTC'
    utcoffset = lambda x, y: timedelta(0)


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

    def __init__(self, owner, repository, start_event=None, log_level=None,
                 debug=False):
        """Initialize an instance of Farcy that monitors owner/repository."""
        # Configure logging
        self.debug = debug
        self.log = logging.getLogger(__name__)
        if debug:
            log_level = 'DEBUG'
        if log_level:
            try:
                level = int(getattr(logging, log_level.upper()))
            except (AttributeError, ValueError):
                raise FarcyException('Invalid log level: {0}'
                                     .format(log_level))

            self.log.setLevel(level)
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)8s %(message)s', '%Y/%m/%d %H:%M:%S'))
            self.log.addHandler(handler)
            self.log.info('Logging enabled at level {0}'.format(log_level))
        else:
            self.log.setLevel(logging.NOTSET)

        if start_event:
            self.start_time = None
            self.last_event_id = int(start_event) - 1
        else:
            self.start_time = datetime.now(UTC())
            self.last_event_id = None

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
        for handler in (handlers.Flake8, handlers.Pep257, handlers.Rubocop):
            try:
                handler_inst = handler()
            except HandlerException:
                continue
            for ext in handler.EXTENSIONS:
                self._ext_to_handler[ext].append(handler_inst)

    def events(self):
        """Yield repository events in order."""
        etag = None
        sleep_time = None  # This value will be overwritten
        while True:
            # Fetch events
            events = []
            itr = self.repo.events(etag=etag)
            itr_first_id = None
            for event in itr:
                itr_first_id = itr_first_id or int(event.id)

                # Stop when we've already seen something
                if self.last_event_id and int(event.id) <= self.last_event_id \
                   or self.start_time and event.created_at < self.start_time:
                    break

                self.log.debug('EVENT {eid} {time} {etype}'.format(
                    eid=event.id, time=event.created_at, etype=event.type))

                # Add relevent events in reverse order
                if event.type in self.EVENTS:
                    events.insert(0, event)

            etag = itr.etag
            self.last_event_id = itr_first_id or self.last_event_id

            # Yield events from oldest to newest
            for event in events:
                yield event

            # Sleep the amount of time indicated in the API response
            sleep_time = int(itr.last_response.headers.get('X-Poll-Interval',
                                                           sleep_time))
            self.log.debug('Sleeping for {0} seconds.'.format(sleep_time))
            time.sleep(sleep_time)

    def get_issues(self, pfile):
        """Return a dictionary of issues for the file."""
        ext = os.path.splitext(pfile.filename)[1]
        handlers = self._ext_to_handler.get(ext)
        if not handlers:  # Do nothing if there are no handlers
            self.log.debug('No handlers for extension {0}'.format(ext))
            return {}
        retval = {}
        with tempfile.NamedTemporaryFile() as fp:
            for chunk in pfile.contents(True).iter_content(chunk_size=1024):
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
        pr.refresh()  # Get most recent state
        if pr.state != 'open':  # Ignore closed PRs
            self.log.info('Handle PR called on {0} PullRequest #{1}'
                          .format(pr.state, pr.number))
            return
        self.log.info('Handling PullRequest #{0}'.format(pr.number))

        sha = list(pr.commits())[-1].sha
        issue_count = 0
        did_work = True
        exception = False
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
                self.log.debug('Found {0} modified line{2} in {1}'
                               .format(len(added), pfile.filename,
                                       '' if len(added) == 1 else 's'))
            elif pfile.status == 'added':
                added = self.added_lines(pfile.patch)
                self.log.debug('Found new file {0} with {1} new line{2}'
                               .format(pfile.filename, len(added),
                                       '' if len(added) == 1 else 's'))
            else:
                self.log.critical('Unexpected file status {0} on {1}'
                                  .format(pfile.status, pfile.filename))
                continue
            did_work = True

            try:
                issues = self.get_issues(pfile)
            except Exception:
                self.log.exception('Failure with get_issues for {0}'
                                   .format(pfile.filename))
                exception = True
                continue
            by_line = defaultdict(lambda: ['_{0}_\n'.format(MD_VERSION_STR)])
            for lineno, line_issues in issues.items():
                if added is None or lineno in added:
                    by_line[lineno].extend(
                        ['* {0}'.format(x) for x in line_issues])
                    issue_count += len(line_issues)
                    del issues[lineno]

            if issues:
                count = sum(len(x) for x in issues.values())
                self.log.debug('IGNORING {0} issue{1} on line{2} {3}'.format(
                    count, '' if count == 1 else 's',
                    '' if len(issues) == 1 else 's',
                    ', '.join(str(x) for x in sorted(issues))))

            for lineno, msgs in sorted(by_line.items()):
                position = added[lineno] if added else lineno
                args = ('\n'.join(msgs), sha, pfile.filename, position)
                info = msgs
                if not self.debug:
                    info = pr.create_review_comment(*args).html_url
                self.log.info('PR#{0} ({1}:{2}) COMMENT: "{3}"'.format(
                    pr.number, pfile.filename, position, info))

        msg = '_{0}_ {{0}}'.format(MD_VERSION_STR)
        if issue_count > 0:
            msg = msg.format('found {0} issue{1}'.format(
                issue_count, '' if issue_count == 1 else 's'))
        else:
            msg = msg.format(':+1:')
        if did_work and not exception:
            url = ''
            if not self.debug:
                url = self.repo.issue(pr.number).create_comment(msg).html_url
            self.log.info('PR#{0} COMMENT: "{1}" {2}'.format(
                pr.number, msg, url))

    def PullRequestEvent(self, event):
        """Check commits on new pull requests."""
        pr = event.payload['pull_request']
        action = event.payload['action']
        self.log.debug('PullRequest #{num} {action} on branch {branch}'
                       .format(action=action, branch=pr.head.ref,
                               num=pr.number))
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
        pull_request = self.open_prs.get(ref.rsplit('/', 1)[1])
        if pull_request:
            self.handle_pr(pull_request)

    def run(self):
        """Run the bot until ctrl+c is received."""
        self.log.info('Monitoring {0}'.format(self.repo.html_url))
        for event in self.events():
            getattr(self, event.type)(event)


def main():
    """Provide an entry point into Farcy."""
    args = docopt(__doc__, version=VERSION_STR)

    try:
        Farcy(args['OWNER'], args['REPOSITORY'], args['--start'],
              args['--logging'], args['--debug']).run()
    except KeyboardInterrupt:
        sys.stderr.write('Farcy shutting down. Goodbye!\n')
        return 0
    except FarcyException as exc:
        sys.stderr.write(exc.message + '\n')
        return 1


if __name__ == '__main__':
    sys.exit(main())
