import io
import re
import typing
from git import Repo
from functools import partial
from ast import parse, NodeVisitor, NodeTransformer
from contextlib import redirect_stdout

ListOrNone = typing.Union[list, None]


class ChangedFile(object):
    def __init__(self, change_type: str, filepath: str, changed_lines: ListOrNone=None):
        self.change_type = change_type
        self.filepath = filepath
        self.changed_lines = changed_lines


class GenericVisitor(NodeVisitor):
    def __init__(self):
        super(GenericVisitor, self).__init__()

    def extract(self, node):
        f = io.StringIO()

        with redirect_stdout(f):
            self.generic_visit(node)

        return f.getvalue().strip().split('\n')


class ObjectNameExtractor(GenericVisitor):
    def __init__(self, callback=None):
        super(ObjectNameExtractor, self).__init__()

    def visit_Call(self, node):
        if node.func.__class__.__name__ == "Name":
            print(node.func.id)

        self.generic_visit(node)


class ClassDefExtractor(GenericVisitor):
    def __init__(self, callback=None):
        super(ClassDefExtractor, self).__init__()

    def visit_ClassDef(self, node):
        pass


class FunctionDefExtractor(GenericVisitor):
    def __init__(self, callback=None):
        super(FunctionDefExtractor, self).__init__()

    def visit_FunctionDef(self, node):
        if node.func.__class__.__name__ == "FunctionDef":
            print()


class ChangedExtractor(GenericVisitor):
    def __init__(self, node_type, ranges):
        super(ChangedExtractor, self).__init__()
        setattr(self, 'visit_%s' % node_type, partial(self._extract_change, ranges))

    def _extract_change(self, ranges, node):
        for r in ranges:
            if node.lineno in r:
                print()


def find_changed_files(repo, ext=".py"):
    changed_files = {}

    current_head = repo.head.commit
    diffs = current_head.diff("HEAD~1", create_patch=True)

    for d in diffs:
        diff_lines_spec = d.diff.decode('utf-8').replace('\r', '').split('\n')[0].split('@@')[1].strip().replace('+', '').replace('-', '')
        changed_lines = None

        if d.change_type == 'A':  # added paths
            filepath = d.a_path
            with open(filepath) as f:
                changed_lines = list(range(1, len(f.readlines())))

        elif d.change_type == 'M':  # modified paths
            filepath = d.a_path
            ranges = diff_lines_spec.split(' ')
            if len(ranges) < 2:
                start, count = ranges[0].split(',')
                # changed_lines = sorted(list(range(start, start + count)))
                changed_lines = [range(start, start + count)]

            else:
                preimage_start, preimage_count = [int(x) for x in ranges[0].split(',')]
                postimage_start, postimage_count = [int(x) for x in ranges[1].split(',')]

                # changed_lines = sorted(list(
                #     set(range(preimage_start, preimage_start + preimage_count)).union(
                #         set(range(postimage_start, postimage_start + postimage_count))
                #     )
                # ))
                changed_lines = [
                    range(preimage_start, preimage_start + preimage_count),
                    range(postimage_start, postimage_start + postimage_count)
                ]

        elif d.change_type == 'D':  # deleted paths
            filepath = d.a_path
            # changed lines == None, but need to check that this path doesn't get imported in tests or by other modules

        elif d.change_type == 'R':  # renamed paths
            filepath = d.b_path
            # changed lines == None; how to handle this type TBD

        elif d.change_type == 'T':  # changed file types
            filepath = d.b_rawpath
            # changed lines == None; how to handle this type TBD

        else:  # something is seriously wrong...
            raise Exception("Unknown change type '%s'" % d.change_type)

        changed_files[filepath] = ChangedFile(
            d.change_type,
            filepath,
            changed_lines=changed_lines
        )

    return changed_files


def find_changed_members(changed_module: ChangedFile):
    with open(changed_module.filepath) as f:
        module_ast = parse(f.read())


