===================
pytest-smartcollect
===================

.. image:: https://img.shields.io/pypi/v/pytest-smartcollect.svg
    :target: https://pypi.org/project/pytest-smartcollect
    :alt: PyPI version

.. image:: https://img.shields.io/pypi/pyversions/pytest-smartcollect.svg
    :target: https://pypi.org/project/pytest-smartcollect
    :alt: Python versions

.. image:: https://travis-ci.org/vardaofthevalier/pytest-smartcollect.svg?branch=master
    :target: https://travis-ci.org/vardaofthevalier/pytest-smartcollect
    :alt: See Build Status on Travis CI

.. image:: https://ci.appveyor.com/api/projects/status/github/vardaofthevalier/pytest-smartcollect?branch=master
    :target: https://ci.appveyor.com/project/vardaofthevalier/pytest-smartcollect/branch/master
    :alt: See Build Status on AppVeyor

A pytest plugin for testing code changes calculated using information from `git diff`.

----

This `pytest`_ plugin was generated with `Cookiecutter`_ along with `@hackebrot`_'s `cookiecutter-pytest-plugin`_ template.


Features
--------

* Filters collected tests according to the following criteria:
    * If a test is new or changed, or if it failed in the previous run, it will run regardless of changes to the code that it tests.
    * If a preexisting test function that is unchanged imports and uses a module member that was not modified within the specified commit range, the test will be skipped.
    * If any paths are specified using one or more --ignore-source flags, those files will be considered "unchanged" for the purposes of filtering the tests.


Requirements
------------

A valid git repository (with at least one commit) containing a python project (with tests) in which to calculate changes between commits.  If a repository has only a single commit, every path within it will be considered added and no diff is necessary.


Installation
------------

You can install "pytest-smartcollect" via `pip`_ from `PyPI`_::

    $ pip install pytest-smartcollect


Usage
-----

From within a valid git repository, run the following command to run smart collection:

    $ pytest --smart-collect [--commit-range <INTEGER>] [--ignore-source <PATH>] [--allow-preemptive-failures]

    Options:
        --smart-collect                 Activates pytest-smartcollect
        --commit-range                  Specifies the number of commits before HEAD for calculating a diff.  Default is 1.
        --ignore-source                 Specifies a filepath within the git repo that should be ignored during smart collection.  Multiple instances of this flag are supported.
        --allow-preemptive-failures     Preemptive failures include scenarios where deleted/renamed/moved/copied files are referenced by their old names somewhere in the project.  If unset, warning messages will be logged only.

If --rootdir is unset, rootdir is assumed to be the current working directory from where the command was run.

Setting --log-level=INFO will print additional information.

Contributing
------------
Contributions are very welcome. Tests can be run with `tox`_, please ensure
the coverage at least stays the same before you submit a pull request.

License
-------

Distributed under the terms of the `BSD-3`_ license, "pytest-smartcollect" is free and open source software


Issues
------

If you encounter any problems, please `file an issue`_ along with a detailed description.

.. _`Cookiecutter`: https://github.com/audreyr/cookiecutter
.. _`@hackebrot`: https://github.com/hackebrot
.. _`MIT`: http://opensource.org/licenses/MIT
.. _`BSD-3`: http://opensource.org/licenses/BSD-3-Clause
.. _`GNU GPL v3.0`: http://www.gnu.org/licenses/gpl-3.0.txt
.. _`Apache Software License 2.0`: http://www.apache.org/licenses/LICENSE-2.0
.. _`cookiecutter-pytest-plugin`: https://github.com/pytest-dev/cookiecutter-pytest-plugin
.. _`file an issue`: https://github.com/vardaofthevalier/pytest-smartcollect/issues
.. _`pytest`: https://github.com/pytest-dev/pytest
.. _`tox`: https://tox.readthedocs.io/en/latest/
.. _`pip`: https://pypi.org/project/pip/
.. _`PyPI`: https://pypi.org/project

