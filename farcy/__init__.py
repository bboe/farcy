"""Farcy, a code review bot for github pull requests.

Usage: farcy.py [-D | --logging=LEVEL] [--comments-per-pr=LIMIT]
                [--exclude-path=PATTERN...]
                [--limit-user=USER...] [options] [REPOSITORY]

Options:

  -s ID, --start=ID  The event id to start handling events from.
  -p ID, --pr=ID     Process only the provided pull request(s).
  -D, --debug        Enable debugging mode. Enables all logging output
                     and prevents the posting of comments.
  --logging=LEVEL    Specify the log level* to output.
  -h, --help         Show this screen.
  --version          Show the program's version.
  -X PATTERN, --exclude-path=PATTERN  Exclude paths that match pattern
                                      (npm_modules/*).
  -u USER, --limit-user=USER          Limit processed pull requests to pull
                                      requests created by USER. This argument
                                      can be provided multiple times, and each
                                      USER token can contain a comma separated
                                      list of users.
  -C LIMIT, --comments-per-pr=LIMIT   Maximum number of comments added by
                                      Farcy per pull request.

* Available log levels:
    https://docs.python.org/3/library/logging.html#logging-levels

"""

from __future__ import print_function
from collections import Counter, defaultdict
from datetime import datetime
from docopt import docopt
from fnmatch import fnmatch
from github3.exceptions import ServerError, UnprocessableEntity
from random import choice
from requests import ConnectionError
from shutil import rmtree
from tempfile import mkdtemp
from timeit import default_timer
import logging
import os
import sys
import time
from .const import (APPROVAL_PHRASES, FARCY_COMMENT_START, STATUS_CONTEXT,
                    VERSION_STR)
from .exceptions import FarcyException, HandlerException
from .helpers import added_lines, plural
from .objects import Config, ErrorTracker, UTC


def no_handler_debug_factory(duration=3600):
    """Return a function to cache 'No handler for...' messages for an hour."""
    last_logged = {}

    def log(obj, ext):
        now = default_timer()
        if now - last_logged.get(ext, 0) > duration:
            obj.log.debug('No handlers for extension {0}'.format(ext))
        last_logged[ext] = now
    return log


class Farcy(object):
    """A bot to automate some code-review processes on GitHub pull requests."""

    EVENTS = {'PullRequestEvent', 'PushEvent'}

    def __init__(self, config):
        """Initialize an instance of Farcy that monitors owner/repository."""
        # Configure logging
        self.config = config
        self.log = logging.getLogger(__name__)
        self.log.setLevel(config.log_level_int)

        # Prepare logging
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)8s %(message)s', '%Y/%m/%d %H:%M:%S'))
        self.log.addHandler(handler)
        self.log.info('Logging enabled at level {0}'.format(config.log_level))

        if config.start_event:
            self.start_time = None
            self.last_event_id = int(config.start_event) - 1
        else:
            self.start_time = datetime.now(UTC())
            self.last_event_id = None

        self._load_handlers()

        # Initialize the repository to monitor
        self.repo = config.session.repository(
            *self.config.repository.split('/'))
        if self.repo is None:
            raise FarcyException('Invalid owner or repository name: {0}'
                                 .format(self.config.repository))
        # Keep track of open pull requests
        self.open_prs = {}
        for pr in self.repo.pull_requests(state='open'):
            self.open_prs[pr.head.ref] = pr

        self.running = False

    def _compute_pfile_stats(self, pfile, stats):
        added = None
        if self.config.exclude_paths is not None and \
                any(fnmatch(pfile.filename, pattern) for pattern
                    in self.config.exclude_paths):
            stats['blacklisted_files'] += 1
        elif pfile.status == 'removed':  # Ignore deleted files
            stats['deleted_files'] += 1
        elif pfile.patch is None:  # Ignore files without changes
            stats['unchanged_files'] += 1
        elif pfile.status in ('modified', 'renamed'):
            # Only report issues on the changed lines
            added = added_lines(pfile.patch)
            stats['modified_files'] += 1
            stats['modified_lines'] += len(added)
        elif pfile.status == 'added':
            added = added_lines(pfile.patch)
            stats['added_files'] += 1
            stats['added_lines'] += len(added)
        else:
            self.log.critical('Unexpected file status {0} on {1}'
                              .format(pfile.status, pfile.filename))
        return added

    def _event_loop(self, itr, events):
        newest_id = None
        for event in itr:
            # Stop when we've already seen something
            if self.last_event_id and int(event.id) <= self.last_event_id \
               or self.start_time and event.created_at < self.start_time:
                break

            self.log.debug('EVENT {eid} {time} {etype} {user}'.format(
                eid=event.id, time=event.created_at, etype=event.type,
                user=event.actor.login))
            newest_id = newest_id or int(event.id)

            # Add relevent events in reverse order
            if event.type in self.EVENTS:
                events.insert(0, event)
        return newest_id

    def _fail_allowed(self, pr):
        if self.config.user_allowed(pr.user.login):
            return None
        return ('Skipping PR#{0}: {1} is not allowed'
                .format(pr.number, pr.user.login))

    def _fail_closed(self, pr):
        pr.refresh()
        if pr.state == 'open':
            return None
        return ('Skipping PR#{0}: invalid state ({1})'
                .format(pr.number, pr.state))

    def _get_state(self, issues, exception):
        if exception:
            return 'error', 'encountered an exception in handler. Check log.'
        if issues > 0:
            return 'failure', 'found {0}'.format(plural(issues, 'issue'))
        return 'success', 'approves! {0}!'.format(choice(APPROVAL_PHRASES))

    def _handle_pr_file(self, pfile, pr, sha, data):
        """Return whether or not an exception occured."""
        added = self._compute_pfile_stats(pfile, data['stats'])
        if added is None:
            return False

        try:
            file_issues = self.get_issues(pfile)
        except Exception:
            self.log.exception('Failure with get_issues for {0}'
                               .format(pfile.filename))
            return True

        for line, messages in file_issues.items():
            if line not in added:  # Skip unadded/unmodified lines.
                continue
            for message in messages:
                data['errors'].track(message, pfile.filename, added[line])

        exception_occurred = False
        for line, violations in data['errors'].errors(pfile.filename):
            if data['comments'] >= self.config.pr_issue_report_limit:
                data['stats']['skipped_issues'] += 1
                continue

            if self.config.debug:
                # Only log each issue if we're in debugging mode because we
                # don't want the logs in non-debugging mode to be noisy.
                self.log.info('PR#{0} ({1}:{2}): {3}"'.format(
                    pr.number, pfile.filename, line, violations))
            else:
                msg = '\n'.join(
                    [FARCY_COMMENT_START] + ['* {}'.format(violation)
                                             for violation in violations])
                try:
                    (pr.create_review_comment(msg, sha, pfile.filename, line)
                     .html_url['href'])
                except UnprocessableEntity as exc:
                    self.log.exception('Failure with create_review_comment for'
                                       ' {0} on line {1}'
                                       .format(pfile.filename, line))
                    self.log.exception(str(exc))
                    exception_occurred = True

            # `data['comments']` is misleading when in debug mode.  What
            # it really means is the number of comments that would be on
            # on the pr (existing + new) when not in debug mode.
            data['comments'] += 1
        return exception_occurred

    def _load_handlers(self):
        from . import handlers
        self._ext_to_handler = defaultdict(list)
        active = []
        for handler in (handlers.ESLint, handlers.Flake8, handlers.Pep257,
                        handlers.Rubocop, handlers.SCSSLint):
            try:
                handler_inst = handler()
            except HandlerException:
                continue
            for ext in handler.EXTENSIONS:
                self._ext_to_handler[ext].append(handler_inst)
            active.append(handler_inst.name)
        if active:
            self.log.info('Active handlers: %s', ', '.join(active))
        else:
            self.log.warning('No active handlers')

    def _set_status(self, sha, status, description):
        if not self.config.debug:
            self.repo.create_status(sha, status, context=STATUS_CONTEXT,
                                    description=description)

    def events(self):
        """Yield repository events in order."""
        if self.running:
            raise FarcyException('Can only enter `events` once.')

        etag = None
        sleep_time = None  # This value will be overwritten.
        self.running = True
        while self.running:
            if sleep_time:  # Only sleep before we're about to make requests.
                time.sleep(sleep_time)

            # Fetch events
            events = []
            itr = self.repo.events(etag=etag)
            try:
                newest_id = self._event_loop(itr, events)
            except (ConnectionError, ServerError) as exc:
                self.log.error('Error in event generation loop: {0}'
                               .format(exc))
                sleep_time = 1
                continue

            etag = itr.etag
            self.last_event_id = newest_id or self.last_event_id

            # Yield events from oldest to newest
            for event in events:
                yield event

            sleep_time = int(itr.last_response.headers.get('X-Poll-Interval',
                                                           sleep_time))

    def get_issues(self, pfile):
        """Return a dictionary of issues for the file."""
        ext = os.path.splitext(pfile.filename)[1]
        handlers = self._ext_to_handler.get(ext)
        if not handlers:  # Do nothing if there are no handlers
            self.no_handler_debug(ext)
            return {}
        retval = {}

        try:
            tmpdir = mkdtemp()
            filepath = os.path.join(tmpdir, os.path.basename(pfile.filename))
            with open(filepath, 'wb') as fp:
                fp.write(pfile.contents().decoded)
            for handler in handlers:
                retval.update(handler.process(fp.name))
        finally:
            rmtree(tmpdir)

        return retval

    def handle_pr(self, pr, force=False):
        """Provide code review on pull request."""
        failure = not force and (self._fail_allowed(pr) or
                                 self._fail_closed(pr))
        if failure:
            self.log.debug(failure)
            return

        sha = list(pr.commits())[-1].sha
        self._set_status(sha, 'pending', 'started investigation')
        self.log.info('Handling PR#{0} by {1}'
                      .format(pr.number, pr.user.login))

        exception = False
        error_tracker = ErrorTracker(pr.review_comments(),
                                     self.config.comment_group_threshold)
        handle_data = {'comments': error_tracker.github_message_count,
                       'errors': error_tracker,
                       'stats': Counter()}
        for pfile in pr.files():
            exception = self._handle_pr_file(
                pfile, pr, sha, handle_data) or exception

        handle_data['stats']['issues'] += error_tracker.new_issue_count
        handle_data['stats']['hidden'] += error_tracker.hidden_issue_count

        # Log the statistics for the PR
        for key, count in sorted(handle_data['stats'].items()):
            if count > 0:
                self.log.debug('PR#{0} {1:>16}: {2}'
                               .format(pr.number, key, count))

        state, message = self._get_state(handle_data['stats']['issues'],
                                         exception)
        self._set_status(sha, state, message)
        self.log.info('PR#{0} STATUS: {1}'.format(pr.number, message))

    no_handler_debug = no_handler_debug_factory()

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
                self.log.warning('open_prs did not contain {0}'
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
        if self.config.pull_requests is not None:
            for number in sorted(int(x) for x in self.config.pull_requests):
                self.handle_pr(self.repo.pull_request(number), force=True)
            return

        self.log.info('Monitoring {0}'.format(self.repo.html_url))
        for event in self.events():
            attempts = 3
            while attempts > 0:
                if attempts < 3:  # Sleep only on subsequent attempts.
                    time.sleep(4 ** (3 - attempts))
                try:
                    getattr(self, event.type)(event)
                    attempts = 0
                except Exception as exc:
                    attempts -= 1
                    self.log.error('Error with event ({0}): {1}'
                                   .format(event, exc))
                    self.log.info('Retrying {0} more time(s).'
                                  .format(attempts))


def main():
    """Provide an entry point into Farcy."""
    args = docopt(__doc__, version=VERSION_STR)
    config = Config(args['REPOSITORY'], debug=args['--debug'],
                    exclude_paths=args['--exclude-path'],
                    limit_users=args['--limit-user'],
                    log_level=args['--logging'],
                    pr_issue_report_limit=args['--comments-per-pr'],
                    pull_requests=args['--pr'],
                    start_event=args['--start'])
    if config.repository is None:
        sys.stderr.write('No repository specified\n')
        return 2

    try:
        Farcy(config).run()
    except KeyboardInterrupt:
        sys.stderr.write('Farcy shutting down. Goodbye!\n')
        return 0
    except FarcyException as exc:
        sys.stderr.write('{0}\n'.format(exc))
        return 1
