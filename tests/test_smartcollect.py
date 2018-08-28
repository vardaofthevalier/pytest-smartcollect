# -*- coding: utf-8 -*-
import os
from shutil import rmtree, move
from git import Repo
from pip._internal import main as pip

if not os.environ.get('USERNAME'):
    os.environ["USERNAME"] = "foo"

# TODO: new test cases:
# - test commits < 2, test commits >= 2
# - test individual change types for diffs


def test_smart_collect_fixture(testdir):
    testdir.makepyfile("""
        def test_smart_collect_fixture(smart_collect):
            assert smart_collect == True
    """)

    result = testdir.runpytest(
        "--smart-collect"
    )


# def test_zero_commits(testdir):
#     pass
#
#
# def test_one_commit(testdir):
#     pass
#
#
# def test_two_commits(testdir):
#     pass


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


def test_find_git_repo_root(testdir):
    Repo.init(".")
    testdir.mkpydir("foo")

    testdir.makepyfile("""
        def test_find_git_repo_root():
            from pytest_smartcollect.helpers import find_git_repo_root
            grr = find_git_repo_root(r"%s")
            assert grr == r"%s"
    """ % (os.path.join(os.path.abspath("."), "foo"), os.path.abspath('.')))

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


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

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


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
            cf = find_changed_files(Repo(repo_path), repo_path)
            assert len(cf) == 1
            assert r"%s" in cf.keys()
    """ % (temp_repo_folder, os.path.join(temp_repo_folder, "foo.py")))

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


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
            cf = find_changed_files(Repo(repo_path), repo_path)
            cm = find_changed_members(list(cf.values())[-1], repo_path)
            assert len(cm) == 1
            assert r"%s" in cm
    """ % (temp_repo_folder, "hello"))

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


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

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


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

    result = testdir.runpytest()

    # fnmatch_lines does an assertion internally
    result.stdout.fnmatch_lines([
        '*1 passed in * seconds*',
    ])

    # make sure that that we get a '0' exit code for the testsuite
    assert result.ret == 0


def test_smartcollect(testdir):
    Repo.init(".")

    testdir.makepyfile(hello="""
        def hello():
            return 42
    """)

    testdir.makepyfile(goodbye="""
        def goodbye():
            return 42
    """)

    testdir.makepyfile(test_hello="""
        def test_hello():
            from hello import hello
            assert hello() == 42
    """)

    testdir.makepyfile(test_goodbye="""
        def test_goodbye():
            from goodbye import goodbye
            assert goodbye() == 42
    """)

    r = Repo(".")
    r.index.add(["hello.py", "goodbye.py"])
    r.index.commit("initial commit")

    result = testdir.runpytest("--smart-collect")

    result.stdout.fnmatch_lines(["*2 passed in * seconds*"])

    assert result.ret == 0

    with open("hello.py", "w") as f:
        f.write("def hello():\n\treturn 43")

    r.index.add(["hello.py"])
    r.index.commit("second commit")

    result = testdir.runpytest("--smart-collect")

    result.stdout.fnmatch_lines(["*1 failed, 1 skipped in * seconds*"])

    assert result.ret != 0




