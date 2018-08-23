# -*- coding: utf-8 -*-

import pytest
from pytest_smartcollect_helpers import find_changed_files, find_changed_members, NameExtractor

import re
from ast import parse, walk
from importlib import import_module


def pytest_addoption(parser):
    group = parser.getgroup('smartcollect')
    group.addoption(
        '--git-repo-root',
        action='store',
        dest='git_repo_root',
        required=True,
        help='Set the value for the fixture "git_repo_root", which is used to evaluate changed files.'
    )

    # parser.addini('HELLO', 'Dummy pytest.ini setting')


@pytest.fixture
def git_repo_root(request):
    return request.config.option.git_repo_root


def pytest_collection_modifyitems(config, items):
    deleted_indices = []
    changed_files = find_changed_files(git_repo_root)

    # TODO: modify behavior by change type
    # if deleted: need to check the entire project for imports of the deleted module (fail fast); otherwise remove the file from changed_files
    # if renamed: need to check the entire project for imports of the OLD name; then continue on as normal
    # if added: if fail_if_untested is set, fail if no tests exist for the added module; otherwise continue as normal
    # if modified: continue as normal
    # if changed file type: remove from changed_files (for now)
    name_extractor = NameExtractor()

    for idx, i in enumerate(items):
        with open(i.fspath) as f:
            test_ast = parse(f.read())

        imports = filter(lambda x: True if x.__class__.__name__ == "ImportFrom" else False, test_ast.body)
        changed_members = []

        for imp in imports:
            m = import_module(imp.module)
            if m.__file__ in changed_files.keys():
                changed_members.extend(find_changed_members(changed_files[m.__file__]))

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

