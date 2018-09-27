# pytest-smartcollect


[![PyPI version](https://img.shields.io/pypi/v/pytest-smartcollect.svg)](https://pypi.org/project/pytest-smartcollect)
[![Build Status](https://travis-ci.org/vardaofthevalier/pytest-smartcollect.svg?branch=master)](https://travis-ci.org/vardaofthevalier/pytest-smartcollect)


A pytest plugin for testing code changes calculated using information
from the output of `git diff`.

------------------------------------------------------------------------

This [pytest](https://github.com/pytest-dev/pytest) plugin was generated
with [Cookiecutter](https://github.com/audreyr/cookiecutter) along with
[@hackebrot](https://github.com/hackebrot)'s
[cookiecutter-pytest-plugin](https://github.com/pytest-dev/cookiecutter-pytest-plugin)
template.

Features
========

- Filters collected tests according to the following criteria:
    1. The test test function body has changed lines
    2. The test function body uses a changed member from another module
    
- Recursively detects changes in both composition (in the case of function and class definitions) and inheritance (in the case of class definitions only).

How it works
============

File changes (including paths and changed lines) are discovered from the output of `git diff`.  This information is then used to determine which "members" of a given module were changed between commits.  Members include any names that can be imported from a module, including assignments, function definitions and class definitions.

A particular test will run if there exists any change in it's dependency hierarchy, starting with the test itself.  If the test is changed or contained in a new file, it will be selected to run regardless of any other changes.  Otherwise, dependency changes are determined by recursively parsing Abstract Sytax Trees within the project using the ast module.  

This process begins by parsing the AST for the test module, then resolving imported names within the test module to file names of their respective modules installed in the environment.  Once this resolution has occurred, the test object is located in the test module AST and a number of checks are performed on the test function in order to determine whether or not it should be considered changed.  

For each assignment found in the body of the object currently under inspection (which would be the test function itself on the first recursive call), the object name on the right hand side of the assignment will be cross checked in the imported names that were resolved for the outer scope.  If the object is known to be changed, the recursion will terminate (True) and the test will run.  If the object name was imported from another module within the project and is not yet known to be changed, the algorithm will recurse on this imported module in order to check whether or not the new object in question (the RHS of the assignment) is changed.  If at any time a changed member is found at the module, function or class method scope, or if a class's bases are changed, the test will be considered to have a changed dependency and will be selected to run.  Otherwise, the test will be skipped. 

Requirements
============

* A valid git repository (with at least one commit) containing a python
project (with tests) in which to calculate changes between commits. If a
repository has only a single commit, every path within it will be
considered to be changed.

* Python version 3.5 or 3.6

Installation
============

You can install "pytest-smartcollect" via
[pip](https://pypi.org/project/pip/) from
[PyPI](https://pypi.org/project):

    $ pip install pytest-smartcollect

Usage
=====

From within a valid git repository, run the following command to run
smart collection:

    $ pytest --smart-collect [--commit-range <INTEGER>] [--ignore-source <PATH>] [--allow-preemptive-failures]


| Option Name | Option Description |
| ----------- | ------------------ |
| --smart-collect | Activates pytest-smartcollect |
| --diff-current-head-with-branch | Specifies the branch to diff the current HEAD with. Default is 'master' |
| --commit-range | Specifies the number of commits before the head of the branch specified with --diff-current-head-with-branch for calculating a diff. Default is 0. |
| --ignore-source | Specifies a filepath within the git repo that should be ignored during smart collection. Multiple instances of this flag are supported. |
| --allow-preemptive-failures | Preemptive failures include scenarios where deleted/renamed/moved/copied files are referenced by their old names somewhere in the project. If unset, warning messages will be logged only. |

*Important Notes*: 
-   Results depend on sources being kept up-to-date for any branches that you plan to calculate diffs between, so be sure to manage your local source branches accordingly.

-   If --rootdir is unset, rootdir is assumed to be the current working
    directory from where the command was run.
-   Setting --log-level=INFO will print additional information about
    skipped tests.
    
Usage Examples
==============

```bash
# enter your repo
cd my_git_repo
git checkout master
git checkout -b my_new_branch
# ... make some changes on my_new_branch
# Add and commit changes on my_new_branch
git add -A
git commit -m "Wow, these are great changes!"
# Run smart collection to test only the changes you made.  The command below will diff the head of the currently checked out branch with the master branch by default.
pytest --smart-collect
```

Contributing
============

Contributions are very welcome. Tests can be run with
[tox](https://tox.readthedocs.io/en/latest/), please ensure the coverage
at least stays the same before you submit a pull request.

License
=======

Distributed under the terms of the
[BSD-3](http://opensource.org/licenses/BSD-3-Clause) license,
"pytest-smartcollect" is free and open source software

Issues
======

If you encounter any problems, please [file an
issue](https://github.com/vardaofthevalier/pytest-smartcollect/issues)
along with a detailed description.
