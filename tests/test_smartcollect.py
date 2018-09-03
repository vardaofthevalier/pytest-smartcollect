# -*- coding: utf-8 -*-
import os
import typing
from importlib import import_module
from _pytest.pytester import Testdir
from coverage import Coverage
from shutil import move
from git import Repo
from pip._internal import main as pip

if not os.environ.get('USERNAME'):
    os.environ["USERNAME"] = "foo"

smart_collect_source = os.path.dirname(import_module('pytest_smartcollect.plugin').__file__)
coverage_files = []

# TODO: new test cases:
# - test individual change types for diffs
# - test different commit ranges (also: need to consider what might happen if invalid integer values are passed in)
# - test different diff targets
# - test preemptive failures
# - test_dependencies_changed (for coverage report)

ListOfString = typing.List[str]


def _check_result(testdir: Testdir, pytest_args: ListOfString, match_lines: ListOfString, return_code_assert: typing.Callable, cover_sources=True):
    if cover_sources:
        default_pytest_args = ["--cov=%s" % smart_collect_source]
        coverage_files.append(os.path.join(testdir.tmpdir.dirpath(), '.coverage'))

    else:
        default_pytest_args = []

    pytest_args.extend(default_pytest_args)

    result = testdir.runpytest(*pytest_args)

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines(match_lines)

    # make sure that that we get a '0' exit code for the testsuite
    assert return_code_assert(result.ret)


def test_source_not_repo(testdir):
    _check_result(
        testdir,
        ["--smart-collect"],
        [],
        lambda x: x != 0,
        cover_sources=False
    )  # rootdir is not a git repo


def test_zero_commits(testdir):
    Repo.init('.')

    _check_result(
        testdir,
        ["--smart-collect"],
        [],
        lambda x: x != 0,
        cover_sources=False
    )  # no commits == invalid repo


def test_one_commit(testdir):
    r = Repo.init('.')

    testdir.makepyfile(test_foo="""
        def test_foo():
            print("foo")
    """)

    r.index.add(["test_foo.py"])
    r.index.commit("first commit")

    _check_result(
        testdir,
        ["--smart-collect"],
        ['*1 passed in * seconds*'],
        lambda x: x == 0,
        cover_sources=False
    )


def test_GenericVisitor_extract(testdir):
    testdir.makepyfile("""
        def test_GenericVisitor_extract():
            from ast import parse
            from pytest_smartcollect.helpers import GenericVisitor
            gv = GenericVisitor()
            with open(__file__) as f:
                output = gv.extract(parse(f.read()))
            assert output == []
    """)

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


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

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_ImportModuleNameExtractor(testdir):
    testdir.makepyfile("""
        def test_ImportModuleNameExtractor_extract():
            from ast import parse
            from pytest_smartcollect.helpers import ImportModuleNameExtractor
            imne = ImportModuleNameExtractor()
            with open(__file__) as f:
                output = imne.extract(parse(f.read()))
            assert output == [('ast', ['parse']), ('pytest_smartcollect.helpers',['ImportModuleNameExtractor'])]
    """)

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_DefinitionNodeExtractor(testdir):
    testdir.makepyfile("""
        def test_DefinitionNodeExtractor_extract():
            from ast import parse, FunctionDef
            from pytest_smartcollect.helpers import DefinitionNodeExtractor
            dne = DefinitionNodeExtractor()
            with open(__file__) as f:
                output = dne.extract(parse(f.read()))
                
            assert len(output) == 1
            assert isinstance(output[0], FunctionDef)
            assert output[0].name == 'test_DefinitionNodeExtractor_extract'
    """)

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_git_repo_root(testdir):
    Repo.init(".")
    testdir.mkpydir("foo")

    testdir.makepyfile("""
        def test_find_git_repo_root():
            from pytest_smartcollect.helpers import find_git_repo_root
            grr = find_git_repo_root(r"%s")
            assert grr == r"%s"
    """ % (os.path.join(os.path.abspath("."), "foo"), os.path.abspath('.')))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_all_files(testdir):
    Repo.init(".")

    testdir.makepyfile(foo="""
        foo = 42
    """)

    testdir.makepyfile(bar="""
        bar = 42
    """)

    testdir.makepyfile("""
        def test_find_all_files():
            from pytest_smartcollect.helpers import find_all_files
            f = find_all_files(r"%s")
            assert len(f) == 3
    """ % os.path.abspath("."))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_changed_files(testdir):
    temp_repo_folder = testdir.tmpdir.dirpath()
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
        def test_find_changed_files():
            from git import Repo
            repo_path = r"%s"
            repo = Repo(repo_path)
            assert len(list(repo.iter_commits('HEAD'))) == 2
            from pytest_smartcollect.helpers import find_changed_files
            a, m, d, r, t = find_changed_files(Repo(repo_path), repo_path, 'master', 1)
            assert len(m) == 1
            assert len(a) == 0
            assert len(d) == 0 
            assert len(r) == 0
            assert len(t) == 0
            assert r"%s" in m.keys()
    """ % (temp_repo_folder, os.path.join(temp_repo_folder, "foo.py")))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_changed_members(testdir):
    temp_repo_folder = testdir.tmpdir.dirpath()
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
        def test_find_changed_members():
            from git import Repo
            repo_path = r"%s"
            repo = Repo(repo_path)
            from pytest_smartcollect.helpers import find_changed_files, find_changed_members
            _, m, _, _, _= find_changed_files(Repo(repo_path), repo_path, 'master', 1)
            cm = find_changed_members(list(m.values())[-1], repo_path)
            assert len(cm) == 1
            assert r"%s" in cm
    """ % (temp_repo_folder, "hello"))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_fully_qualified_module_name(testdir):
    testdir.mkpydir("foo")
    testdir.makepyfile(bar="""
           def hello():
               pass
       """)

    move(os.path.join("bar.py"), os.path.join("foo", "bar.py"))

    testdir.makepyfile("""
        def test_find_fully_qualified_module_name():
            import os
            import foo
            from pytest_smartcollect.helpers import find_fully_qualified_module_name
            name = find_fully_qualified_module_name(r"%s")
            assert name == "foo.bar"
    """ % os.path.join(os.path.abspath("."), "foo", "bar.py"))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_imports_package_relative(testdir):
    testdir.mkpydir("foo")

    testdir.makepyfile(foo="from bar import hello")
    testdir.makepyfile(bar="""
        def hello():
            pass
    """)
    testdir.makepyfile(setup="""
        from setuptools import setup
        setup(
            name='foo',
            version='0.1.0',
            packages=['foo']
        )
    """)

    move(os.path.join("foo.py"), os.path.join("foo", "foo.py"))
    move(os.path.join("bar.py"), os.path.join("foo", "bar.py"))

    pip(['install', '-U', '.'])

    testdir.makepyfile("""
        def test_find_imports_package_relative():
            import os
            from pytest_smartcollect.helpers import find_import
            found = find_import(r"%s", r"%s")
            assert len(found) == 1
            assert os.path.basename(found[0]) == os.path.basename(r"%s")
    """ % (os.path.abspath('.'), os.path.abspath(os.path.join("foo", "bar.py")), os.path.abspath(os.path.join("foo", "foo.py"))))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_find_imports_package_external(testdir):
    testdir.mkpydir("foo")
    testdir.mkpydir("baz")

    testdir.makepyfile(zoo="from baz.bar import hello")
    testdir.makepyfile(bar="""
            def hello():
                pass
        """)
    testdir.makepyfile(setup="""
            from setuptools import setup
            setup(
                name='test',
                version='0.1.0',
                packages=['foo', 'baz']
            )
        """)

    move(os.path.join("zoo.py"), os.path.join("foo", "zoo.py"))
    move(os.path.join("bar.py"), os.path.join("baz", "bar.py"))

    pip(['install', '-U', '.'])

    testdir.makepyfile("""
            def test_find_imports_package_external():
                import os
                from pytest_smartcollect.helpers import find_import
                found = find_import(r"%s", r"%s")
                assert len(found) == 1
                assert os.path.basename(found[0]) == os.path.basename(r"%s")
        """ % (os.path.abspath('.'), os.path.abspath(os.path.join("baz", "bar.py")),
               os.path.abspath(os.path.join("foo", "zoo.py"))))

    _check_result(
        testdir,
        [],
        ['*1 passed in * seconds*'],
        lambda x: x == 0
    )


def test_filter_ignore_sources(testdir): # TODO: the code that this tests is broken
    Repo.init(".")

    testdir.makepyfile(test_foo="""
        def test_foo():
            from foo import foo
    """)

    r = Repo(".")
    r.index.add(["test_foo.py"])
    r.index.commit("initial commit")

    testdir.makepyfile(foo="""
        def foo():
            pass
    """)

    r.index.add(["foo.py"])
    r.index.commit("second commit")

    _check_result(
        testdir,
        ["--smart-collect", "--commit-range", "1", "--ignore-source", os.path.join(testdir.tmpdir.dirpath(), "test_foo.py")],
        ["*1 skipped in * seconds*"],
        lambda x: x == 0,
        cover_sources=False
    )


def test_dependencies_changed(testdir): # TODO, for coverage report only
    # case 1: a direct dependency has changed
    # case 2: one step dependency changed
    # case 3: two step dependency changed
    # case 4: no dependencies changed
    pass


def test_run_smart_collection(testdir):
    Repo.init(".")

    testdir.makepyfile(hello="""
        def hello():
            return 42
    """)

    testdir.makepyfile(goodbye="""
        def goodbye():
            return 43
    """)

    testdir.makepyfile(hello_goodbye="""
        from hello import hello
        from goodbye import goodbye

        def hello_goodbye(select):
            if select == 'hello':
                return hello()

            else:
                return goodbye()
    """)

    testdir.makepyfile(test_hello="""
        def test_hello():
            from hello import hello
            assert hello() == 42
    """)

    testdir.makepyfile(test_goodbye="""
        def test_goodbye():
            from goodbye import goodbye
            assert goodbye() == 43\n
    """)

    testdir.makepyfile(test_hello_goodbye="""
        def test_hello_goodbye():
            from hello_goodbye import hello_goodbye
            assert hello_goodbye('hello') == 42
            assert hello_goodbye('goodbye') == 43
    """)

    r = Repo(".")
    r.index.add(["hello.py", "goodbye.py", "hello_goodbye.py"])
    r.index.commit("initial commit")

    # case 1: all tests are new, and therefore should run
    _check_result(
        testdir,
        ["--smart-collect"],
        ["*3 passed in * seconds*"],
        lambda x: x == 0,
        cover_sources=False
    )

    # case 2: one direct dependency (of test_hello) and one indirect dependency (of test_hello_goodbye) has changed
    with open("hello.py", "w") as f:
        f.write("def hello():\n\treturn 44")

    r.index.add(["hello.py"])
    r.index.commit("second commit")

    _check_result(
        testdir,
        ["--smart-collect", "--commit-range", "1"],
        ["*2 failed, 1 skipped in * seconds*"],
        lambda x: x != 0,
        cover_sources=False
    )

    # test the lastfailed functionality -- test_hello and test_hello_goodbye should still fail, but it should also still run those tests even though changes to their dependencies didn't occur
    _check_result(
        testdir,
        ["--smart-collect", "--commit-range", "1"],
        ["*2 failed, 1 skipped in * seconds*"],
        lambda x: x != 0,
        cover_sources=False
    )


# def test_generate_coverage_report(testdir):
#     cov = Coverage()
#     cov.combine(coverage_files)





