# -*- coding: utf-8 -*-
import re
import pytest
from pytest_smartcollect.helpers import find_git_repo_root, \
    find_all_files, \
    filter_ignore_sources, \
    find_changed_files, \
    find_changed_members, \
    find_import, \
    ObjectNameExtractor, \
    ImportModuleNameExtractor

import os
from ast import parse
from importlib import import_module
from git import Repo


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

    # coverage_plugin = config.pluginmanager.get_plugin('_cov')
    # if coverage_plugin is None or not coverage_plugin.active:
    #     logger.warning("Coverage plugin either not installed or not active -- changes to untested code will go completely unnoticed.  Try using the coverage plugin to identify these gaps.")

    if smart_collect:
        git_repo_root = find_git_repo_root(str(config.rootdir))

        repo = Repo(git_repo_root)

        total_commits_on_head = len(list(repo.iter_commits("HEAD")))

        if total_commits_on_head < 2:
            added_files = find_all_files(git_repo_root)
            modified_files = {}
            deleted_files = {}
            renamed_files = {}
            changed_filetype_files = {}

        else:  # inspect the diff
            added_files, modified_files, deleted_files, renamed_files, changed_filetype_files = find_changed_files(repo, git_repo_root, diff_current_head_with_branch, commit_range)

        # search for a few problems preemptively
        for deleted in deleted_files.values():
            # check if any deleted files (or the old path for renamed files) are imported anywhere in the project
            try:
                found = find_import(str(config.rootdir), deleted.current_filepath)

            except Exception as e:
                if allow_preemptive_failures:
                    raise e

                else:
                    logger.warning(str(e))

            else:
                if len(found) > 0:
                    msg = ""
                    for f in found:
                        msg += "Module from deleted file '%s' imported in file '%s'\n" % (deleted.current_filepath, f)

                    if allow_preemptive_failures:
                        raise Exception(msg)

                    logger.warning(msg)

        for renamed in renamed_files.values():
            # check if any renamed files are imported by their old name
            try:
                found = find_import(str(config.rootdir), renamed.old_filepath)

            except Exception as e:
                if allow_preemptive_failures:
                    raise e

                else:
                    logger.warning(str(e))

            else:
                if len(found) > 0:
                    msg = ""
                    for f in found:
                        msg += "Module from renamed file ('%s' -> '%s') imported incorrectly using it's old name in file '%s'\n" % (
                            renamed.old_filepath, renamed.current_filepath, f)

                    if allow_preemptive_failures:
                        raise Exception(msg)

                    logger.warning(msg)

        changed_to_py = {}
        for changed_filetype in changed_filetype_files.values():
            # check if any files that changed type from python to something else are still being imported somewhere else in the project
            if os.path.splitext(changed_filetype.old_filepath)[-1] == ".py":
                found = find_import(str(config.rootdir), changed_filetype.old_filepath)
                if len(found) > 0:
                    msg = ""
                    for f in found:
                        msg += "Module from renamed file ('%s' -> '%s') no longer exists but is imported in file '%s'\n)" % (
                            changed_filetype.old_filepath, changed_filetype.current_filepath, f)

                    if allow_preemptive_failures:
                        raise Exception(msg)

                    logger.warning(msg)

            elif os.path.splitext(changed_filetype.current_filepath) == ".py":
                changed_to_py[changed_filetype.current_filepath] = changed_filetype

        changed_files = {}
        changed_files.update(changed_to_py)
        changed_files.update(modified_files)
        changed_files.update(renamed_files)
        changed_files.update(added_files)

        # ignore anything explicitly set in --ignore-source flags
        changed_files = filter_ignore_sources(changed_files, ignore_source)

        for test in items:
            # if the test is new, run it anyway
            if str(test.fspath) in changed_files.keys() and changed_files[str(test.fspath)].change_type == 'A':
                logger.warning("Test '%s' is new, so will be run regardless of changes to the code it tests" % test.nodeid)
                continue

            # if the test is changed, run it anyway
            elif str(test.fspath) in changed_files.keys() and test.name in find_changed_members(changed_files[str(test.fspath)], git_repo_root):
                logger.warning("Test '%s' is changed, so will be run regardless of changes to the code it tests" % test.nodeid)
                continue

            # if the test failed in the last run, run it anyway
            if test.nodeid in config.cache.get("cache/lastfailed", {}):
                logger.warning("Test '%s' failed on the last run, so will be run regardless of changes" % test.nodeid)
                continue

            # if the test is already skipped, just ignore it
            if test.get_marker('skip'):
                logger.info("Found skip marker on test '%s' -- ignoring" % test.nodeid)
                continue

            # use the AST of the test to determine which things it imports and/or uses
            with open(str(test.fspath)) as f:
                test_ast = parse(f.read())

            if len(changed_files) > 0:
                name_extractor = ObjectNameExtractor()
                import_name_extractor = ImportModuleNameExtractor()

                imports = import_name_extractor.extract(test_ast)
                changed_members = []

                for imp in imports:
                    try:
                        m = import_module(imp)

                    except ImportError:
                        raise Exception("Module '%s' was imported in test '%s', but the module is not installed in the environment" % (imp, test.nodeid))

                    if m.__file__ in changed_files.keys():
                        changed_members.extend(find_changed_members(changed_files[m.__file__], git_repo_root))

                if len(changed_members) > 0:
                    logger.info("Found the following changed members in test '%s': " % test.nodeid + str(changed_members))
                    test_fn = list(filter(lambda x: True if x.__class__.__name__ == "FunctionDef" and re.match('^%s.*' % x.name, test.name) else False, test_ast.body))[0]

                    used_names = name_extractor.extract(test_fn)
                    logger.info("Test '%s' uses names: " % test.nodeid + str(used_names))
                    found_name = False
                    for name in used_names:
                        if name in changed_members:
                            found_name = True
                            break

                    if not found_name:
                        logger.info("Test '%s' doesn't touch new or modified code -- SKIPPING" % test.nodeid)
                        skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                        test.add_marker(skip)

                    else:
                        logger.warning("Selected test '%s' to run" % test.nodeid)

                else:
                    logger.info("Test '%s' doesn't touch new or modified code -- SKIPPING" % test.nodeid)
                    skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                    test.add_marker(skip)

            else:
                logger.info("Test '%s' doesn't touch new or modified code -- SKIPPING" % test.nodeid)
                skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                test.add_marker(skip)