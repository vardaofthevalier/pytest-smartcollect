#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import codecs
from setuptools import setup


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding='utf-8').read()


setup(
    name='pytest-smartcollect',
    version='0.1.0',
    author='Abigail Hahn',
    author_email='abigail.n.hahn@gmail.com',
    maintainer='Abigail Hahn',
    maintainer_email='abigail.n.hahn@gmail.com',
    license='BSD-3',
    url='https://github.com/vardaofthevalier/pytest-smartcollect',
    description='A plugin for collecting tests that touch changed code',
    long_description=read('README.md'),
    py_modules=['pytest_smartcollect'],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*',
    install_requires=['pytest>=3.5.0', 'GitPython==2.1.11', 'chardet==3.0.4'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Pytest',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Testing',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: BSD License',
    ],
    packages=["pytest_smartcollect"],
    entry_points={
        'pytest11': [
            'smartcollect = pytest_smartcollect.plugin',
        ],
    },
)
