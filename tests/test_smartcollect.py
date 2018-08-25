# -*- coding: utf-8 -*-
import os
from shutil import rmtree
from git import Repo
from tempfile import mkdtemp
import pytest

if not os.environ.get('USERNAME'):
    os.environ["USERNAME"] = "foo"

# TODO: new test cases:
# - test commits < 2, test commits >= 2
# - test individual change types for diffs
# - test 0, 1, 2 and 3 commits


def test_git_repo_root_fixture_valid_repo(testdir):
    # create a temporary repo with a minimal number of commits for producing a diff (2)
    temp_repo_folder = mkdtemp()
    temp_git_repo = Repo.init(temp_repo_folder)

    filename = os.path.join(temp_repo_folder, "foo.py")
    with open(filename, 'w') as f:
        f.write("def hello():\n\tprint('Hello foo!')")
    temp_git_repo.index.add([filename])
    temp_git_repo.index.commit("initial commit")

    with open(filename, 'w') as f:
        f.write("def hello():\n\tprint('Hello foo!')\n\tprint('How goes it?')")
    temp_git_repo.index.add([filename])
    temp_git_repo.index.commit("second commit")

    testdir.makepyfile("""
        def test_git_repo_root_valid_repo(git_repo_root):
            assert git_repo_root == r"%s"
    """ % temp_repo_folder)

    result = testdir.runpytest(
        "--git-repo-root=%s" % temp_repo_folder
    )

    #fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_git_repo_root_fixture_invalid_repo(testdir):
    temp_folder = mkdtemp()
    testdir.makepyfile("""
        def test_git_repo_root_invalid_repo(git_repo_root):
            assert git_repo_root == r"%s"
    """ % temp_folder)

    result = testdir.runpytest(
        "--git-repo-root=%s" % temp_folder
    )

    #fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*no tests ran in * seconds*',  # should fail collection
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret != 0


def test_pytest_collection_modify_items(testdir):
    pass


def test_GenericVisitor_extract(testdir):
    testdir.makepyfile("""
        def test_GenericVisitor_extract():
            from ast import parse
            from pytest_smartcollect.helpers import GenericVisitor
            gv = GenericVisitor()
            with open(__file__) as f:
                output = gv.extract(parse(f.read()))
            assert output == ['']
    """)

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_ObjectNameExtractor(testdir):
    testdir.makepyfile("""
            def test_ObjectNameExtractor_extract():
                from ast import parse
                from pytest_smartcollect.helpers import ObjectNameExtractor
                one = ObjectNameExtractor()
                with open(__file__) as f:
                    output = one.extract(parse(f.read()))
                assert output == ['ObjectNameExtractor', 'open', 'parse']
        """)

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_ImportModuleNameExtractor(testdir):
    testdir.makepyfile("""
        def test_ImportModuleNameExtractor_extract():
            from ast import parse
            from pytest_smartcollect.helpers import ImportModuleNameExtractor
            imne = ImportModuleNameExtractor()
            with open(__file__) as f:
                output = imne.extract(parse(f.read()))
            assert output == ['ast', 'pytest_smartcollect.helpers']
    """)

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_find_changed_files(testdir):
    # create a temporary repo with a minimal number of commits for producing a diff (2)
    temp_repo_folder = mkdtemp()
    temp_git_repo = Repo.init(temp_repo_folder)

    filename = os.path.join(temp_repo_folder, "foo.py")
    with open(filename, 'w') as f:
        f.write("def hello():\n\tprint('Hello foo!')")
    temp_git_repo.index.add([filename])
    temp_git_repo.index.commit("initial commit")

    with open(filename, 'w') as f:
        f.write("def hello():\n\tprint('Hello foo!')\n\tprint('How goes it?')")
    temp_git_repo.index.add([filename])
    temp_git_repo.index.commit("second commit")

    testdir.makepyfile("""
        def test_find_changed_files(git_repo_root):
            from git import Repo
            repo = Repo(git_repo_root)
            assert len(list(repo.iter_commits('HEAD'))) == 2
            from pytest_smartcollect.helpers import find_changed_files
            cf = find_changed_files(Repo(git_repo_root))
            assert len(cf) == 1
            assert r"%s" in cf.keys()
    """ % "foo.py")

    result = testdir.runpytest(
        "--git-repo-root=%s" % temp_repo_folder
    )

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_find_changed_members(testdir):
    #create a temporary repo with a minimal number of commits for producing a diff (2)
    temp_repo_folder = mkdtemp()
    temp_git_repo = Repo.init(temp_repo_folder)

    filename = os.path.join(temp_repo_folder, "foo.py")
    with open(filename, 'w') as f:
        f.write("def hello():\n\tprint('Hello foo!')")
    temp_git_repo.index.add([filename])
    temp_git_repo.index.commit("initial commit")

    with open(filename, 'w') as f:
        f.write("def hello():\n\tprint('Hello foo!')\n\tprint('How goes it?')")
    temp_git_repo.index.add([filename])
    temp_git_repo.index.commit("second commit")

    testdir.makepyfile("""
            def test_find_changed_files(git_repo_root):
                from git import Repo
                repo = Repo(git_repo_root)
                from pytest_smartcollect.helpers import find_changed_files, find_changed_members
                cf = find_changed_files(Repo(git_repo_root))
                cm = find_changed_members(list(cf.values())[-1], git_repo_root)
                assert len(cm) == 1
                assert r"%s" in cm
        """ % "hello")

    result = testdir.runpytest(
        "--git-repo-root=%s" % temp_repo_folder
    )

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_file_path_to_module_name(testdir):
    # create a temporary repo with a minimal number of commits for producing a diff (2)
    temp_repo_folder = mkdtemp()

    filename = os.path.join(temp_repo_folder, "foo.py")
    with open(filename, 'w') as f:
        f.write("from bar import hello")

    init = os.path.join(temp_repo_folder, "__init__.py")
    with open(init, 'w') as f:
        f.write("")

    testdir.makepyfile("""
            def test_file_path_to_module_name():
                from pytest_smartcollect.helpers import file_path_to_module_name
                tokens = file_path_to_module_name(r"%s")
                assert tokens == ['%s', 'foo']
        """ % (filename, os.path.basename(temp_repo_folder)))

    result = testdir.runpytest(
        # "--git-repo-root=%s" % temp_repo_folder
    )

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])


def test_find_imports(testdir):
    # create a temporary repo with a minimal number of commits for producing a diff (2)
    temp_repo_folder = mkdtemp()
    temp_git_repo = Repo.init(temp_repo_folder)

    filename = os.path.join(temp_repo_folder, "foo.py")
    with open(filename, 'w') as f:
        f.write("from bar import hello")

    filename2 = os.path.join(temp_repo_folder, "bar.py")
    with open(filename2, 'w') as f:
        f.write("def hello():\n\tpass")

    init = os.path.join(temp_repo_folder, "__init__.py")
    with open(init, 'w') as f:
        f.write("")

    temp_git_repo.index.add([filename, filename2, init])
    temp_git_repo.index.commit("initial commit")

    testdir.makepyfile("""
        def test_find_imports():
            from pytest_smartcollect.helpers import find_import
            found = find_import(r"%s", r"%s")
            assert len(found) == 1
            assert r"%s" in found
    """ % (temp_repo_folder, filename2, filename))

    result = testdir.runpytest(
        # "--git-repo-root=%s" % temp_repo_folder
    )

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0

