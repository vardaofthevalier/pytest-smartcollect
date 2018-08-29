import io
import os
import sys
import ast
import typing
from git import Repo
from importlib import import_module
from contextlib import redirect_stdout

ListOrNone = typing.Union[list, None]
StrOrNone = typing.Union[str, None]
ListOfString = typing.List[str]


class ChangedFile(object):
    def __init__(self, change_type: str, current_filepath: str, old_filepath: StrOrNone=None, changed_lines: ListOrNone=None):
        self.change_type = change_type
        self.old_filepath = old_filepath
        self.current_filepath = current_filepath
        self.changed_lines = changed_lines


DictOfChangedFile = typing.Dict[str, ChangedFile]


class GenericVisitor(ast.NodeVisitor):
    def __init__(self):
        super(GenericVisitor, self).__init__()

    def extract(self, node) -> ListOfString:
        f = io.StringIO()

        with redirect_stdout(f):
            self.generic_visit(node)

        return list(filter(lambda x: True if x != '' else False, f.getvalue().strip().split('\n')))


class ObjectNameExtractor(GenericVisitor):
    def __init__(self):
        super(ObjectNameExtractor, self).__init__()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
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


def find_git_repo_root(dir: str) -> str:
    if ".git" in os.listdir(dir):
        return dir

    else:
        if os.path.dirname(dir) == dir:
            raise Exception("No git repo found relative to the pytest rootdir")

        else:
            return find_git_repo_root(os.path.dirname(dir))


def find_all_files(repo_path: str) -> DictOfChangedFile:
    all_files = {}
    for root, _, files in os.walk(repo_path):
        for f in files:
            if os.path.splitext(f)[-1] == ".py":
                fpath = os.path.join(root, f)
                with open(fpath) as g:
                    all_files[fpath] = ChangedFile(
                        change_type='A',
                        old_filepath=None,
                        current_filepath=fpath,
                        changed_lines=[range(1, len(g.readlines()))]
                    )

    return all_files


def find_changed_files(repo: Repo, repo_path: str, commit_range: int) -> DictOfChangedFile:
    changed_files = {}

    current_head = repo.head.commit
    diffs = current_head.diff("HEAD~%d" % commit_range)
    diffs_with_patch = current_head.diff("HEAD~%d" % commit_range, create_patch=True)

    for idx, d in enumerate(diffs):
        assert d.a_path == diffs_with_patch[idx].a_path

        diff_lines_spec = diffs_with_patch[idx].diff.decode('utf-8').replace('\r', '').split('\n')[0].split('@@')[1].strip().replace('+', '').replace('-', '')
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
                preimage = [int(x) for x in ranges[0].split(',')]
                preimage_start = preimage[0]
                if len(preimage) > 1:
                    preimage_count = preimage[1]
                else:
                    preimage_count = 0

                postimage = [int(x) for x in ranges[1].split(',')]
                postimage_start = postimage[0]
                if len(postimage) > 1:
                    postimage_count = postimage[1]

                else:
                    postimage_count = 0

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

        if os.path.splitext(filepath)[-1] == ".py":
            if os.sep == "\\":
                filepath = os.path.join(repo_path, filepath).replace('/', os.sep)

                if old_filepath is not None:
                    old_filepath = os.path.join(repo_path, old_filepath).replace('/', os.sep)

            else:
                filepath = os.path.join(repo_path, filepath)

                if old_filepath is not None:
                    old_filepath = os.path.join(repo_path, old_filepath)

            changed_files[os.path.join(repo_path, filepath)] = ChangedFile(
                d.change_type,
                filepath,
                old_filepath=old_filepath,
                changed_lines=changed_lines
            )

    return changed_files


def find_changed_members(changed_module: ChangedFile, repo_path: str) -> ListOfString:
    changed_members = []
    name_extractor = ObjectNameExtractor()

    with open(os.path.join(repo_path, changed_module.current_filepath)) as f:
        contents = f.read()

    total_lines = len(contents.split('\n'))
    module_ast = ast.parse(contents)
    # direct_children = sorted(ast.iter_child_nodes(module_ast), key=lambda x: x.lineno)
    direct_children = list(ast.iter_child_nodes(module_ast))

    changed_lines = set()
    for ch in changed_module.changed_lines:
        changed_lines.update(set(ch))

    for idx, node in enumerate(direct_children):
        if isinstance(node, ast.Assign) or isinstance(node, ast.FunctionDef) or isinstance(node, ast.ClassDef):
            try:
                r = range(node.lineno, direct_children[idx + 1].lineno)

            except IndexError:
                r = range(node.lineno, total_lines)

            if set(changed_lines).intersection(set(r)):
                if isinstance(node, ast.Assign):
                    changed_members.extend(name_extractor.extract(node))

                elif isinstance(node, ast.FunctionDef):
                    changed_members.append(node.name)

                else:
                    changed_members.append(node.name)

    return changed_members


def find_import(repo_root: str, module_path: str) -> ListOfString:
    found = []
    module_name_extractor = ImportModuleNameExtractor()

    for root, _, files in os.walk(repo_root):
        for f in files:
            if os.path.splitext(f)[-1] == ".py":
                with open(os.path.join(root, f)) as g:
                    a = ast.parse(g.read())

                for module in module_name_extractor.extract(a):
                    # determine whether or not the module is part of the standard library
                    if module in sys.builtin_module_names:
                        continue

                    # determine if the imported module is relative to it's containing package or outside of it
                    package_path = os.path.dirname(os.path.join(root, f))

                    if os.path.isfile(os.path.join(package_path, "%s.py" % module)) or os.path.isdir(os.path.join(package_path, module)):
                        # in the same package
                        fully_qualified_module_name = find_fully_qualified_module_name(os.path.join(package_path, '%s.py' % module))
                        i = import_module(fully_qualified_module_name)

                    else:
                        # in a different package
                        try:
                            i = import_module(module)  # this assumes that the module is actually installed...

                        except ImportError:
                            raise Exception("Module '%s' was imported in file '%s', but the module is not installed in the environment" % (module, os.path.join(root, f)))

                    if os.path.basename(i.__file__) == os.path.basename(module_path):
                        found.append(f)
                        break

    return found


def find_fully_qualified_module_name(path: str) -> str:
    parts = [os.path.splitext(os.path.basename(path))[0]]

    while "__init__.py" in os.listdir(os.path.dirname(path)):
        parts.insert(0, os.path.basename(os.path.dirname(path)))
        path = os.path.dirname(path)

    return ".".join(parts)





