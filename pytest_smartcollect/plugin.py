# -*- coding: utf-8 -*-

import pytest
from pytest_smartcollect.helpers import find_all_files, find_changed_files, find_changed_members, find_import, ObjectNameExtractor

import os
from ast import parse
from importlib import import_module
from git import Repo
from git.exc import InvalidGitRepositoryError
# from logging import getLogger


def pytest_addoption(parser):
    group = parser.getgroup('smartcollect')
    group.addoption(
        '--git-repo-root',
        action='store',
        dest='git_repo_root',
        help='Set the value for the fixture "git_repo_root", which is used to evaluate changed files in a project.'
    )

    # parser.addini('HELLO', 'Dummy pytest.ini setting')


@pytest.fixture
def git_repo_root(request):
    try:
        Repo(request.config.option.git_repo_root)

    except InvalidGitRepositoryError:
        raise Exception("Invalid value for --git-repo-root: must be a valid git repository")

    return request.config.option.git_repo_root

# TODO: configure overrides for paths to add in the INI file and on the command line


def pytest_collection_modifyitems(config, items):
    # logger = getLogger()
    #
    # # if coverage isn't loaded, warn the user that untested files won't be reported, and coverage might help
    # try:
    #     config.pluginmanager.get_plugin("coverage")
    #
    # except Exception:
    #     logger.warning("Untested files won't be reported by this plugin -- try Coverage for reported uncovered code.")

    git_repo_root = config.option.git_repo_root

    if git_repo_root is not None:
        repo = Repo(git_repo_root)

        total_commits_on_head = len(list(repo.iter_commits("HEAD")))

        if total_commits_on_head < 2:
            changed_files = find_all_files(git_repo_root)

        else:  # inspect the diff
            changed_files = find_changed_files(repo)

        # TODO: configure overrides for paths to add in the INI file

        deleted_indices = []

        if len(changed_files) > 0:
            for ch in changed_files.values():
                # check if any deleted files (or the old path for renamed files) are imported anywhere in the project
                if ch.change_type == "D":
                    found = find_import(git_repo_root, ch.current_filepath)
                    if len(found) > 0:
                        msg = ""
                        for f in found:
                            msg += "Module from deleted file '%s' imported in file '%s'\n" % (ch.current_filepath, f)

                        raise Exception(msg)

                # check if any renamed files are imported by their old name
                elif ch.change_type == "R":
                    found = find_import(git_repo_root, ch.old_filepath)
                    if len(found) > 0:
                        msg = ""
                        for f in found:
                            msg += "Module from renamed file ('%s' -> '%s') imported incorrectly using it's old name in file '%s'\n" % (ch.old_filepath, ch.current_filepath, f)

                        raise Exception(msg)

                elif ch.change_type == "T":
                    if os.path.splitext(ch.old_filepath)[-1] == ".py":
                        found = find_import(git_repo_root, ch.old_filepath)
                        if len(found) > 0:
                            msg = ""
                            for f in found:
                                msg += "Module from renamed file ('%s' -> '%s') no longer exists but is imported in file '%s'\n)" % (ch.old_filepath, ch.current_filepath, f)

                            raise Exception(msg)
                else:
                    continue

            name_extractor = ObjectNameExtractor()

            for idx, i in enumerate(items):
                with open(i.fspath) as f:
                    test_ast = parse(f.read())

                imports = filter(lambda x: True if x.__class__.__name__ == "ImportFrom" else False, test_ast.body)
                changed_members = []

                for imp in imports:
                    m = import_module(imp.module)
                    if m.__file__ in changed_files.keys():
                        changed_members.extend(find_changed_members(changed_files[m.__file__], git_repo_root))

                if len(changed_members) > 0:
                    test_fn = list(filter(lambda x: True if x.__class__.__name__ == "FunctionDef" and x.name == i.name else False, test_ast.body))[0]

                    used_names = name_extractor.extract(test_fn)
                    found_name = False
                    for name in used_names:
                        if name in changed_members:
                            found_name = True
                            break

                    if not found_name:
                        deleted_indices.append(idx)

            deleted = 0
            for d in sorted(deleted_indices):
                items.pop(d - deleted)
                deleted += 1

        else:
            for _ in range(0, len(items)):
                items.pop()