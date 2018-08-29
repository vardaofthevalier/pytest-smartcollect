# -*- coding: utf-8 -*-

import pytest
from pytest_smartcollect.helpers import find_git_repo_root, \
    find_all_files, \
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
        default=1,
        type=int,
        dest='commit_range',
        help='The number of commits before the HEAD commit to use when calculating diffs for smart collection. Default is 1'
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


def pytest_collection_modifyitems(config, items):
    smart_collect = config.option.smart_collect
    ignore_source = config.option.ignore_source
    commit_range = config.option.commit_range
    allow_preemptive_failures = config.option.allow_preemptive_failures
    log_level = config.option.log_level or 'WARNING'

    from logging import getLogger
    logger = getLogger()
    logger.setLevel(log_level)

    # TODO: review compatibility with other plugins; fail if a plugin is found to be both active and incompatible

    coverage_plugin = config.pluginmanager.get_plugin('_cov')
    if coverage_plugin is None or not coverage_plugin.active:
        logger.warning("Coverage plugin either not installed or not active -- changes to untested code will go completely unnoticed.  Try using the coverage plugin to identify these gaps.")

    if smart_collect:
        git_repo_root = find_git_repo_root(str(config.rootdir))

        repo = Repo(git_repo_root)

        total_commits_on_head = len(list(repo.iter_commits("HEAD")))

        if total_commits_on_head < 2:
            changed_files = find_all_files(git_repo_root)

        else:  # inspect the diff
            changed_files = find_changed_files(repo, git_repo_root, commit_range)

        if len(ignore_source) > 0:
            filtered_changed_files = {}
            for k, v in changed_files.items():
                for y in ignore_source:
                    if os.path.commonpath([v.current_filepath, y]) != y:
                        filtered_changed_files[k] = v

            changed_files = filtered_changed_files

        if len(changed_files) > 0:
            logger.info("Found the following changed files: " + str(changed_files.keys()))
            for ch in changed_files.values():
                # check if any deleted files (or the old path for renamed files) are imported anywhere in the project
                if ch.change_type == "D":
                    try:
                        found = find_import(str(config.rootdir), ch.current_filepath)

                    except Exception as e:
                        if allow_preemptive_failures:
                            raise e

                        else:
                            logger.warning(str(e))

                    else:
                        if len(found) > 0:
                            msg = ""
                            for f in found:
                                msg += "Module from deleted file '%s' imported in file '%s'\n" % (ch.current_filepath, f)

                            if allow_preemptive_failures:
                                raise Exception(msg)

                            logger.warning(msg)

                # check if any renamed files are imported by their old name
                elif ch.change_type == "R":
                    try:
                        found = find_import(str(config.rootdir), ch.old_filepath)

                    except Exception as e:
                        if allow_preemptive_failures:
                            raise e

                        else:
                            logger.warning(str(e))

                    else:
                        if len(found) > 0:
                            msg = ""
                            for f in found:
                                msg += "Module from renamed file ('%s' -> '%s') imported incorrectly using it's old name in file '%s'\n" % (ch.old_filepath, ch.current_filepath, f)

                            if allow_preemptive_failures:
                                raise Exception(msg)

                            logger.warning(msg)

                elif ch.change_type == "T":
                    if os.path.splitext(ch.old_filepath)[-1] == ".py":
                        found = find_import(str(config.rootdir), ch.old_filepath)
                        if len(found) > 0:
                            msg = ""
                            for f in found:
                                msg += "Module from renamed file ('%s' -> '%s') no longer exists but is imported in file '%s'\n)" % (ch.old_filepath, ch.current_filepath, f)

                            if allow_preemptive_failures:
                                raise Exception(msg)

                            logger.warning(msg)
                else:
                    continue

            name_extractor = ObjectNameExtractor()
            import_name_extractor = ImportModuleNameExtractor()

            for test in items:
                if test.nodeid in config.cache.get("cache/lastfailed", {}):
                    logger.warning("Test '%s' failed on the last run, so will be run regardless of changes" % test.nodeid)
                    continue

                if test.get_marker('skip'):
                    logger.info("Found skip marker on test '%s' -- SKIPPING" % test._nodeid)
                    continue

                with open(str(test.fspath)) as f:
                    test_ast = parse(f.read())

                imports = import_name_extractor.extract(test_ast)
                changed_members = []

                for imp in imports:
                    try:
                        m = import_module(imp)

                    except ImportError:
                        raise Exception("Module '%s' was imported in test '%s', but the module is not installed in the environment" % (imp, test._nodeid))

                    if m.__file__ in changed_files.keys():
                        changed_members.extend(find_changed_members(changed_files[m.__file__], git_repo_root))

                if len(changed_members) > 0:
                    logger.info("Found the following changed members in test '%s': " % test._nodeid + str(changed_members))
                    test_fn = list(filter(lambda x: True if x.__class__.__name__ == "FunctionDef" and x.name == test.name else False, test_ast.body))[0]

                    used_names = name_extractor.extract(test_fn)
                    logger.info("Test '%s' uses names: " % test._nodeid + str(used_names))
                    found_name = False
                    for name in used_names:
                        if name in changed_members:
                            found_name = True
                            break

                    if not found_name:
                        skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                        test.add_marker(skip)

                    else:
                        logger.warning("Selected test '%s' to run" % test._nodeid)

                else:
                    logger.info("Test '%s' doesn't touch new or modified code -- SKIPPING" % test._nodeid)
                    skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                    test.add_marker(skip)

        else:
            for test in items:
                if test.nodeid in config.cache.get("cache/lastfailed", {}):
                    logger.warning("Test '%s' failed on the last run, so will be run regardless of changes" % test._nodeid)
                    continue
                skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                test.add_marker(skip)