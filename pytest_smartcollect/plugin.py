# -*- coding: utf-8 -*-
import pytest
from pytest_smartcollect.helpers import SmartCollector


def pytest_addoption(parser):
    group = parser.getgroup('smartcollect')
    group.addoption(
        '--smart-collect',
        action='store_true',
        dest='smart_collect',
        help='Use smart collection to run tests on changed code only -- requires that the pytest rootdir exist in a valid git repository'
    )
    group.addoption(
        '--ignore-source',
        action='append',
        default=[],
        nargs='?',
        const=True,
        metavar='path',
        dest='ignore_source',
        help='Source code file or folder to ignore during smart collection.  Multiple instances of this flag are supported.'
    )
    group.addoption(
        '--commit-range',
        action='store',
        default=0,
        type=int,
        dest='commit_range',
        help='The number of commits before the HEAD commit of the diffed branch (specified with option --diff-current-head-with-branch) to use when calculating diffs for smart collection. Default is 0'
    )
    group.addoption(
        '--diff-current-head-with-branch',
        action='store',
        default='master',
        dest='diff_current_head_with_branch',
        help='The branch to diff the currently checked out head with. Default is "master".'
    )
    group.addoption(
        '--allow-preemptive-failures',
        action='store_true',
        default=False,
        dest='allow_preemptive_failures',
        help="If any deleted or renamed files are found to be imported in any files under test, collection will fail when using smart collection. Default is False."
    )


@pytest.fixture
def smart_collect(request):
    return request.config.option.smart_collect


@pytest.hookimpl(trylast=True) # I don't want to interfere with the functionality of other plugins that might implement this hook
def pytest_collection_modifyitems(config, items):
    smart_collect = config.option.smart_collect
    ignore_source = config.option.ignore_source
    commit_range = config.option.commit_range
    diff_current_head_with_branch = config.option.diff_current_head_with_branch
    allow_preemptive_failures = config.option.allow_preemptive_failures
    log_level = config.option.log_level or 'WARNING'

    from logging import getLogger
    logger = getLogger()
    logger.setLevel(log_level)

    # TODO: review compatibility with other plugins; fail if a plugin is found to be both active and incompatible

    if smart_collect:
        smart_collector = SmartCollector(
            str(config.rootdir),
            config.cache.get("cache/lastfailed", {}),
            ignore_source,
            commit_range,
            diff_current_head_with_branch,
            allow_preemptive_failures,
            logger
        )
        smart_collector.run(items)