"""Farcy, a code review bot for github pull requests.

Usage: farcy.py [-D | --logging=LEVEL] [--comments-per-pr=LIMIT]
                [--exclude-path=PATTERN...]
                [--limit-user=USER...] [options] OWNER REPOSITORY

Options:

  -s ID, --start=ID       The event id to start handling events from.
  -D, --debug             Enable debugging mode. Enables all logging output
                          and prevents the posting of comments.
  --logging=LEVEL         Specify the log level* to output.
  -h, --help              Show this screen.
  --version               Show the program's version.
  --exclude-path=PATTERN  Exclude paths that match pattern (npm_modules/*)
  --limit-user=USER       Limit processed PRs to PRs created by USER
  --comments-per-pr=LIMIT Maximum number of comments added by Farcy per PR.

* Available log levels:
    https://docs.python.org/3/library/logging.html#logging-levels

"""

from __future__ import print_function
from collections import defaultdict
from datetime import datetime
from docopt import docopt
from fnmatch import fnmatch
from github3 import GitHub
from github3.exceptions import GitHubError
from shutil import rmtree
from tempfile import mkdtemp
from update_checker import UpdateChecker
import logging
import os
import sys
import time
from .const import (
    __version__, VERSION_STR, PR_ISSUE_COMMENT_FORMAT,
    COMMIT_STATUS_FORMAT, FARCY_COMMENT_START, CONFIG_DIR)
from .exceptions import FarcyException, HandlerException
from .helpers import (
    added_lines, filter_comments_from_farcy, issues_by_line, split_dict,
    subtract_issues_by_line, UTC)


class Farcy(object):

    """A bot to automate some code-review processes on GitHub pull requests."""

    EVENTS = {'PullRequestEvent', 'PushEvent'}
    _update_checked = False

    @staticmethod
    def _raise_unexpected(code):
        """Called from with in an except block.

        Re-raises the exception if we don't know how to handle it.

        """
        if code != 401:
            raise

    @staticmethod
    def _ensure_config_dir():
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, mode=0o700)

    @staticmethod
    def get_session():
        """Fetch and/or load API authorization token for GITHUB."""
        Farcy._ensure_config_dir()
        credential_file = os.path.join(CONFIG_DIR, 'github_auth')
        if os.path.isfile(credential_file):
            with open(credential_file) as fd:
                token = fd.readline().strip()
            gh = GitHub(token=token)
            try:  # Test connection before starting
                gh.is_starred('github', 'gitignore')
                return gh
            except GitHubError as exc:
                Farcy._raise_unexpected(exc.code)
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
            Farcy._raise_unexpected(exc.code)
            raise FarcyException(exc.message)

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
                 debug=False, exclude_paths=None, limit_users=None,
                 pr_issue_report_limit=None):
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

        self.exclude_paths = exclude_paths or []
        self.limit_users = limit_users
        self.pr_issue_report_limit = pr_issue_report_limit or 128

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
        for handler in (handlers.Flake8, handlers.Pep257, handlers.Rubocop,
                        handlers.JSXHint):
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

    def handle_pr(self, pr):
        """Provide code review on pull request."""
        pr.refresh()  # Get most recent state
        if pr.state != 'open':  # Ignore closed PRs
            self.log.info('Handle PR called on {0} PullRequest #{1}'
                          .format(pr.state, pr.number))
            return
        if self.limit_users is not None and \
           pr.user.login not in self.limit_users:
            self.log.info('Skipping PullRequest #{0} because user {1} is not '
                          'whitelisted'.format(pr.number, pr.user.login))
            return
        self.log.info('Handling PullRequest #{0}'.format(pr.number))

        sha = list(pr.commits())[-1].sha
        issue_count = 0
        did_work = True
        exception = False
        existing_comments = list(filter_comments_from_farcy(
            pr.review_comments()))
        comments_added = len(existing_comments)
        for pfile in pr.files():
            if any(fnmatch(pfile.filename, pattern) for pattern
                   in self.exclude_paths):
                self.log.debug('Ignoring blacklisted file: {0}'.format(
                    pfile.filename))
                continue

            added = None
            if pfile.status == 'removed':  # Ignore deleted files
                self.log.debug('Ignoring deleted file: {0}'
                               .format(pfile.filename))
                continue
            elif pfile.patch is None:  # Ignore files without changes
                self.log.debug('Ignoring {0} file without change: {1}'
                               .format(pfile.status, pfile.filename))
                continue
            elif pfile.status in ('modified', 'renamed'):
                # Only report issues on the changed lines
                added = added_lines(pfile.patch)
                self.log.debug('Found {0} modified line{2} in {1}'
                               .format(len(added), pfile.filename,
                                       '' if len(added) == 1 else 's'))
            elif pfile.status == 'added':
                added = added_lines(pfile.patch)
                self.log.debug('Found new file {0} with {1} new line{2}'
                               .format(pfile.filename, len(added),
                                       '' if len(added) == 1 else 's'))
            else:
                self.log.critical('Unexpected file status {0} on {1}'
                                  .format(pfile.status, pfile.filename))
                continue
            did_work = True

            try:
                file_issues = self.get_issues(pfile)
            except Exception:
                self.log.exception('Failure with get_issues for {0}'
                                   .format(pfile.filename))
                exception = True
                continue

            issues, _ = split_dict(file_issues, added.keys())

            # Maps patch line no to violations
            issues = {
                added[lineno]: value for lineno, value
                in split_dict(file_issues, added.keys())[0].items()
            }
            file_issue_count = sum(len(x) for x in issues.values())
            issue_count += file_issue_count

            self.log.info('PR#{0}: Found {1} issue{2} for {3}'.format(
                          pr.number, file_issue_count,
                          's' if file_issue_count > 1 else '', pfile.filename))

            if comments_added > self.pr_issue_report_limit:
                continue

            file_issues_to_comment = subtract_issues_by_line(
                issues, issues_by_line(existing_comments, pfile.filename))
            reported_issue_count = sum(
                len(x) for x in file_issues_to_comment.values())

            if reported_issue_count != file_issue_count:
                unreported_issues = file_issue_count-reported_issue_count
                self.log.debug(
                    'PR#{0}: Not reporting {1} previously reported issue{2} '
                    'for {3}'.format(
                        pr.number, unreported_issues,
                        '' if unreported_issues == 1 else 's', pfile.filename))

            for lineno, violations in sorted(file_issues_to_comment.items()):
                msg = '\n'.join(
                    [FARCY_COMMENT_START] + ['* {}'.format(violation)
                                             for violation in violations])

                args = (msg, sha, pfile.filename, lineno)
                info = violations
                if not self.debug:
                    info = pr.create_review_comment(*args).html_url['href']
                self.log.info('PR#{0} ({1}:{2}) COMMENT: "{3}"'.format(
                    pr.number, pfile.filename, lineno, info))
                comments_added += 1
                if comments_added >= self.pr_issue_report_limit:
                    break

        if issue_count > 0:
            status_msg = 'found {0} issue{1}'.format(
                issue_count, '' if issue_count == 1 else 's')
            status_state = 'error'
        else:
            status_msg = 'approves!'
            status_state = 'success'
        if did_work and not exception:
            pr_msg = PR_ISSUE_COMMENT_FORMAT.format(status_msg)
            if not self.debug:
                self.repo.create_status(
                    sha, status_state,
                    description=COMMIT_STATUS_FORMAT.format(status_msg),
                    context=VERSION_STR)
            self.log.info('PR#{0} COMMIT STATUS: "{1}"'.format(
                pr.number, pr_msg))

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
    limit_users = args['--limit-user'] or None

    try:
        Farcy(args['OWNER'], args['REPOSITORY'], args['--start'],
              args['--logging'], args['--debug'], args['--exclude-path'],
              limit_users, args['--comments-per-pr']).run()
    except KeyboardInterrupt:
        sys.stderr.write('Farcy shutting down. Goodbye!\n')
        return 0
    except FarcyException as exc:
        sys.stderr.write(exc.message + '\n')
        return 1


if __name__ == '__main__':
    sys.exit(main())
