import io
import os
import re
import ast
import typing
from git import Repo
from functools import partial
from importlib import import_module
from contextlib import redirect_stdout

ListOrNone = typing.Union[list, None]
StrOrNone = typing.Union[str, None]


class ChangedFile(object):
    def __init__(self, change_type: str, current_filepath: str, old_filepath: StrOrNone=None, changed_lines: ListOrNone=None):
        self.change_type = change_type
        self.old_filepath = old_filepath
        self.current_filepath = current_filepath
        self.changed_lines = changed_lines


class GenericVisitor(ast.NodeVisitor):
    def __init__(self):
        super(GenericVisitor, self).__init__()

    def extract(self, node):
        f = io.StringIO()

        with redirect_stdout(f):
            self.generic_visit(node)

        return f.getvalue().strip().split('\n')


class ObjectNameExtractor(GenericVisitor):
    def __init__(self):
        super(ObjectNameExtractor, self).__init__()

    def visit_Call(self, node):
        if node.func.__class__.__name__ == "Name":
            print(node.func.id)

        self.generic_visit(node)


class ImportModuleNameExtractor(GenericVisitor):
    def __init__(self):
        super(ImportModuleNameExtractor, self).__init__()

    def visit_Import(self, node):
        print(node.names[0].name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        print(node.module)


def find_changed_files(repo, ext=".py"):
    changed_files = {}

    current_head = repo.head.commit
    diffs = current_head.diff("HEAD~1", create_patch=True)

    for d in diffs:
        diff_lines_spec = d.diff.decode('utf-8').replace('\r', '').split('\n')[0].split('@@')[1].strip().replace('+', '').replace('-', '')
        changed_lines = None
        old_filepath = None

        if d.change_type == 'A':  # added paths
            filepath = d.a_path
            with open(filepath) as f:
                changed_lines = list(range(1, len(f.readlines())))

        elif d.change_type == 'M':  # modified paths
            filepath = d.a_path
            ranges = diff_lines_spec.split(' ')
            if len(ranges) < 2:
                start, count = ranges[0].split(',')
                changed_lines = [range(start, start + count)]

            else:
                preimage_start, preimage_count = [int(x) for x in ranges[0].split(',')]
                postimage_start, postimage_count = [int(x) for x in ranges[1].split(',')]
                changed_lines = [
                    range(preimage_start, preimage_start + preimage_count),
                    range(postimage_start, postimage_start + postimage_count)
                ]

        elif d.change_type == 'D':  # deleted paths
            filepath = d.a_path

        elif d.change_type == 'R':  # renamed paths
            filepath = d.b_path
            old_filepath = d.a_path

        elif d.change_type == 'T':  # changed file types
            filepath = d.b_rawpath

        else:  # something is seriously wrong...
            raise Exception("Unknown change type '%s'" % d.change_type)

        if os.path.splitext(filepath)[-1] == ext:
            changed_files[filepath] = ChangedFile(
                d.change_type,
                filepath,
                old_filepath=old_filepath,
                changed_lines=changed_lines
            )

    return changed_files


def find_changed_members(changed_module: ChangedFile):
    changed_members = []
    name_extractor = ObjectNameExtractor()
    with open(changed_module.current_filepath) as f:
        module_ast = ast.parse(f.read())

    for idx, node in enumerate(module_ast.body):
        if isinstance(node, ast.Assign) or isinstance(node, ast.FunctionDef) or isinstance(node, ast.ClassDef):
            r = range(node.lineno, module_ast.body[idx + 1].lineno - 1)
            for ch in changed_module.changed_lines:
                if set(ch).intersection(set(r)):
                    changed_members.append(name_extractor.extract(node))

    return changed_members


def find_import(repo_root, module_path):
    found = []
    module_name_extractor = ImportModuleNameExtractor()

    for root, _, files in os.walk(repo_root):
        for f in files:
            if os.path.splitext(f)[-1] == ".py":
                with open(f) as g:
                    a = ast.parse(g.read())

                for module in module_name_extractor.extract(a):
                    i = import_module(module)
                    if i.__file__ == module_path:
                        found.append(i.__file__)

    return found






