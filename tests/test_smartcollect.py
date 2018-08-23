# -*- coding: utf-8 -*-
import os
from shutil import rmtree
from git import Repo
from tempfile import mkdtemp
import pytest


temp_repo_folder = mkdtemp()
temp_git_repo = Repo().init(temp_repo_folder)
temp_folder = mkdtemp()


def test_git_repo_root_fixture_valid_repo(testdir):
    testdir.makepyfile("""
        def test_git_repo_root_valid_repo(git_repo_root):
            assert git_repo_root == "%s"
    """ % temp_repo_folder)

    result = testdir.runpytest(
        "--git-repo-root=%s" % temp_repo_folder
    )

    #fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*::test_git_repo_root_valid_repo PASSED*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_git_repo_root_fixture_invalid_repo(testdir):
    testdir.makepyfile("""
        def test_git_repo_root_invalid_repo(git_repo_root):
            assert git_repo_root == "%s"
    """ % temp_repo_folder)

    result = testdir.runpytest(
        "--git-repo-root=%s" % temp_folder
    )

    #fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*::test_git_repo_root_invalid_repo PASSED*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret != 0

def test_pytest_collection_modify_items(testdir):
    pass

def test_GenericVisitor(testdir):
    pass

def test_ObjectNameExtractor(testdir):
    pass

def test_ImportModuleNameExtractor(testdir):
    pass

def test_find_changed_files(testdir):
    pass

def test_find_changed_members(testdir):
    pass

def test_find_imports(testdir):
    pass

# def test_bar_fixture(testdir):
#     """Make sure that pytest accepts our fixture."""
#
#     # create a temporary pytest test module
#     testdir.makepyfile("""
#         def test_sth(bar):
#             assert bar == "europython2015"
#     """)
#
#     # run pytest with the following cmd args
#     result = testdir.runpytest(
#         '--foo=europython2015',
#         '-v'
#     )
#
#     # fnmatch_lines does an assertion internally
#     result.stdout.fnmatch_lines([
#         '*::test_sth PASSED*',
#     ])
#
#     # make sure that that we get a '0' exit code for the testsuite
#     assert result.ret == 0
#
#
# def test_help_message(testdir):
#     result = testdir.runpytest(
#         '--help',
#     )
#     # fnmatch_lines does an assertion internally
#     result.stdout.fnmatch_lines([
#         'smartcollect:',
#         '*--foo=DEST_FOO*Set the value for the fixture "bar".',
#     ])
#
#
# def test_hello_ini_setting(testdir):
#     testdir.makeini("""
#         [pytest]
#         HELLO = world
#     """)
#
#     testdir.makepyfile("""
#         import pytest
#
#         @pytest.fixture
#         def hello(request):
#             return request.config.getini('HELLO')
#
#         def test_hello_world(hello):
#             assert hello == 'world'
#     """)
#
#     result = testdir.runpytest('-v')
#
#     # fnmatch_lines does an assertion internally
#     result.stdout.fnmatch_lines([
#         '*::test_hello_world PASSED*',
#     ])
#
#     # make sure that that we get a '0' exit code for the testsuite
#     assert result.ret == 0
