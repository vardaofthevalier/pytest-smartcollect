# -*- coding: utf-8 -*-

import pytest
from pytest_smartcollect.helpers import find_git_repo_root, find_all_files, find_changed_files, find_changed_members, find_import, ObjectNameExtractor, ImportModuleNameExtractor

import os
from ast import parse
from importlib import import_module
from git import Repo
from git.exc import InvalidGitRepositoryError
# from logging import getLogger


def pytest_addoption(parser):
    group = parser.getgroup('smartcollect')
    group.addoption(
        '--smart-collect',
        action='store_true',
        dest='smart_collect',
        help='Set the value for the fixture "git_repo_root", which is used to evaluate changed files in a project.'
    )

    # parser.addini('HELLO', 'Dummy pytest.ini setting')


@pytest.fixture
def smart_collect(request):
    return request.config.option.smart_collect


def pytest_collection_modifyitems(config, items):
    smart_collect = config.option.smart_collect

    if smart_collect:
        git_repo_root = find_git_repo_root(str(config.rootdir))

        repo = Repo(git_repo_root)

        total_commits_on_head = len(list(repo.iter_commits("HEAD")))

        if total_commits_on_head < 2:
            changed_files = find_all_files(git_repo_root)

        else:  # inspect the diff
            changed_files = find_changed_files(repo, git_repo_root)

        # TODO: configure overrides for paths to add in the INI file

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
            import_name_extractor = ImportModuleNameExtractor()

            for test in items:
                with open(test.fspath) as f:
                    test_ast = parse(f.read())

                imports = import_name_extractor.extract(test_ast)
                changed_members = []

                for imp in imports:
                    try:
                        m = import_module(imp)

                    except ImportError:
                        raise Exception("Module '%s' was imported in test '%s', but the module is not installed in the environment" % (imp, test.name))

                    if m.__file__ in changed_files.keys():
                        changed_members.extend(find_changed_members(changed_files[m.__file__], git_repo_root))

                if len(changed_members) > 0:
                    test_fn = list(filter(lambda x: True if x.__class__.__name__ == "FunctionDef" and x.name == test.name else False, test_ast.body))[0]

                    used_names = name_extractor.extract(test_fn)
                    found_name = False
                    for name in used_names:
                        if name in changed_members:
                            found_name = True
                            break

                    if not found_name:
                        skip = pytest.mark.skip(reason="Skipping: test doesn't touch new or modified code")
                        test.add_marker(skip)

                else:
                    skip = pytest.mark.skip(reason="Skipping: test doesn't touch new or modified code")
                    test.add_marker(skip)

        else:
            for test in items:
                skip = pytest.mark.skip(reason="Skipping: test doesn't touch new or modified code")
                test.add_marker(skip)