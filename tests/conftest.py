import os

pytest_plugins = 'pytester'

def pytest_addoption(parser):
    parser.addoption(
        "--coverage-report-directory", action="store", type=str, default=os.path.join(os.path.expanduser("~"), "pytest-smartcollect-coverage")
    )
