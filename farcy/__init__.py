"""Farcy, a code review bot for github pull requests.

Usage: farcy.py [-D | --logging=LEVEL] [--comments-per-pr=LIMIT]
                [--exclude-path=PATTERN...]
                [--limit-user=USER...] [options] [REPOSITORY]

Options:

  -s ID, --start=ID  The event id to start handling events from.
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
from github3 import GitHub
from github3.exceptions import GitHubError
from random import choice
from shutil import rmtree
from tempfile import mkdtemp
from timeit import default_timer
from update_checker import UpdateChecker
import logging
import os
import sys
import time
from .const import (__version__, APPROVAL_PHRASES, CONFIG_DIR,
                    FARCY_COMMENT_START, STATUS_FORMAT, VERSION_STR)
from .exceptions import FarcyException, HandlerException
from .helpers import (
    UTC, added_lines, filter_comments_from_farcy, issues_by_line, plural,
    process_user_list, split_dict, subtract_issues_by_line)


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

    def _compute_pfile_stats(self, pfile, stats):
        added = None
        if any(fnmatch(pfile.filename, pattern) for pattern
               in self.exclude_paths):
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

                self.log.debug('EVENT {eid} {time} {etype} {user}'.format(
                    eid=event.id, time=event.created_at, etype=event.type,
                    user=event.actor.login))

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
            time.sleep(sleep_time)

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

    def handle_pr(self, pr):
        """Provide code review on pull request."""
        pr.refresh()  # Get most recent state
        if pr.state != 'open':  # Ignore closed PRs
            self.log.debug('Skipping PR#{0}: invalid state ({1})'
                           .format(pr.number, pr.state))
            return
        if self.limit_users is not None and \
                pr.user.login.lower() not in self.limit_users:
            self.log.debug('Skipping PR#{0}: {1} is not whitelisted'
                           .format(pr.number, pr.user.login))
            return
        self.log.info('Handling PR#{0} by {1}'
                      .format(pr.number, pr.user.login))

        sha = list(pr.commits())[-1].sha
        exception = False
        existing_comments = list(filter_comments_from_farcy(
            pr.review_comments()))
        stats = Counter()
        comments_on_github = len(existing_comments)
        for pfile in pr.files():
            added = self._compute_pfile_stats(pfile, stats)
            if added is None:
                continue

            try:
                file_issues = self.get_issues(pfile)
            except Exception:
                self.log.exception('Failure with get_issues for {0}'
                                   .format(pfile.filename))
                exception = True
                continue

            # Maps patch line number to violation
            issues = {added[lineno]: value for lineno, value in
                      split_dict(file_issues, added.keys())[0].items()}

            file_issues_to_comment = subtract_issues_by_line(
                issues, issues_by_line(existing_comments, pfile.filename))

            file_issue_count = sum(len(x) for x in issues.values())
            stats['issues'] += file_issue_count

            unreported_issues = file_issue_count - sum(
                len(x) for x in file_issues_to_comment.values())
            if unreported_issues > 0:
                stats['duplicate_issues'] += unreported_issues

            for lineno, violations in sorted(file_issues_to_comment.items()):
                if comments_on_github >= self.pr_issue_report_limit:
                    stats['skipped_issues'] += 1
                    continue

                if self.debug:
                    # Only log each issue if we're in debugging mode because we
                    # don't want the logs in non-debugging mode to be noisy.
                    self.log.info('PR#{0} ({1}:{2}): {3}"'.format(
                        pr.number, pfile.filename, lineno, violations))
                else:
                    msg = '\n'.join(
                        [FARCY_COMMENT_START] + ['* {}'.format(violation)
                                                 for violation in violations])
                    (pr.create_review_comment(msg, sha, pfile.filename, lineno)
                     .html_url['href'])
                # `comments_on_github` is misleading when in debug mode.  What
                # it really means is the number of comments that would be on
                # github when not in debug mode.
                comments_on_github += 1

        # Log the statistics for the PR
        for key, count in sorted(stats.items()):
            if count > 0:
                self.log.debug('PR#{0} {1:>16}: {2}'
                               .format(pr.number, key, count))

        if stats['issues'] > 0:
            status_msg = 'found {0}'.format(plural(stats['issues'], 'issue'))
            status_state = 'error'
        else:
            status_msg = 'approves! {0}!'.format(choice(APPROVAL_PHRASES))
            status_state = 'success'
        if not exception:
            if not self.debug:
                self.repo.create_status(
                    sha, status_state, context=VERSION_STR,
                    description=STATUS_FORMAT.format(status_msg))
            self.log.info('PR#{0} STATUS: "{1}"'.format(pr.number, status_msg))

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

    not_set_value = {
        'start_event': None,
        'debug': False,
        'exclude_paths': [],
        'limit_users': None,
        'log_level': None,
        'pr_issue_report_limit': None,
    }
    params = {
        'start_event': args['--start'],
        'debug': args['--debug'],
        'exclude_paths': args['--exclude-path'],
        'limit_users': args['--limit-user'] or None,
        'log_level': args['--logging'],
        'pr_issue_report_limit': args['--comments-per-pr'],
    }

    repository = args['REPOSITORY']
    config_path = os.path.join(CONFIG_DIR, 'farcy.conf')
    if os.path.isfile(config_path):
        try:
            import configparser  # PY3
        except ImportError:
            import ConfigParser as configparser  # PY2
        config_file = configparser.SafeConfigParser()
        config_file.read(config_path)

        if repository is None and config_file.has_option('default',
                                                         'repository'):
            repository = config_file.get('default', 'repository')

        for section in (repository, 'default'):
            if not config_file.has_section(section):
                continue
            for key, cur_value in params.items():
                if cur_value != not_set_value[key] or \
                   not config_file.has_option(section, key):
                    continue
                value = config_file.get(section, key)
                if key in ('exclude_paths', 'limit_users'):
                    value = [item.strip() for item in value.split(',')]
                elif key == 'debug':
                    value = value.lower() in ('true', '1')
                params[key] = value

    if repository is None:
        sys.stderr.write('No repository specified\n')
        return 2
    repo_parts = repository.split('/')
    if len(repo_parts) != 2:
        sys.stderr.write(
            'Invalid repository specified: {0}\n'.format(repository))
        return 2

    try:
        Farcy(repo_parts[0], repo_parts[1], **params).run()
    except KeyboardInterrupt:
        sys.stderr.write('Farcy shutting down. Goodbye!\n')
        return 0
    except FarcyException as exc:
        sys.stderr.write(exc.message + '\n')
        return 1


if __name__ == '__main__':
    sys.exit(main())
