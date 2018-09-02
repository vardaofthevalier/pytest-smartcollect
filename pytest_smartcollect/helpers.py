import re
import os
import sys
import ast
import typing
from git import Repo
from importlib import import_module

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
        self.cache = []

    def extract(self, node) -> list:
        self.cache.clear()
        self.generic_visit(node)
        return self.cache


class ObjectNameExtractor(GenericVisitor):
    def __init__(self):
        super(ObjectNameExtractor, self).__init__()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.cache.append(node.func.id)

        self.generic_visit(node)


class DefinitionNodeExtractor(GenericVisitor):
    def __init__(self):
        super(DefinitionNodeExtractor, self).__init__()

    def visit_FunctionDef(self, node):
        self.cache.append(node)

    def visit_ClassDef(self, node):
        self.cache.append(node)


class ImportModuleNameExtractor(GenericVisitor):
    def __init__(self):
        super(ImportModuleNameExtractor, self).__init__()

    def visit_Import(self, node):
        imp = import_module(node.names[0].name)
        self.cache.append((node.names[0].name, ['%s.%s' % (node.names[0].name, x) for x in dir(imp)]))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        names = list(map(lambda x: x.name, node.names))
        if '*' in names:
            imp = import_module(node.name)
            names = dir(imp)
        self.cache.append((node.module, names))


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


def find_changed_files(repo: Repo, repo_path: str, diff_current_head_with_branch: str, commit_range: int) -> (DictOfChangedFile, DictOfChangedFile, DictOfChangedFile, DictOfChangedFile, DictOfChangedFile):
    changed_files = {
        'A': {},
        'M': {},
        'D': {},
        'R': {},
        'T': {}
    }

    # currently this only calculates the diff between the tip of the branch and the previous commits specified in commit_range
    # it might be useful in the future to add additional functionality for using diffs between the index and HEAD, between the working tree and HEAD, or between arbitrary commits
    current_head = repo.head.commit
    previous_commits = repo.commit("%s~%d" % (diff_current_head_with_branch, commit_range))
    diffs = previous_commits.diff(current_head)
    diffs_with_patch = previous_commits.diff(current_head, create_patch=True)

    for idx, d in enumerate(diffs):
        diff_text = diffs_with_patch[idx].diff.decode('utf-8').replace('\r', '')
        if re.match('^Binary files.*', diff_text) or len(diff_text) == 0:
            continue
        diff_lines_spec = diff_text.split('\n')[0].split('@@')[1].strip().replace('+', '').replace('-', '')
        changed_lines = None
        old_filepath = None

        if d.change_type == 'A':  # added paths
            filepath = os.path.join(repo_path, d.a_path)
            with open(filepath, encoding='utf-8') as f:
                changed_lines = [range(1, len(f.readlines()))]

        elif d.change_type == 'M':  # modified paths
            filepath = os.path.join(repo_path, d.a_path)
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
            filepath = os.path.join(repo_path, d.a_path)

        elif d.change_type == 'R':  # renamed paths
            filepath = os.path.join(repo_path, d.b_path)
            old_filepath = os.path.join(repo_path, d.a_path)
            with open(filepath, encoding='utf-8') as f:
                changed_lines = [range(1, len(f.readlines()))]

        elif d.change_type == 'T':  # changed file types
            filepath = os.path.join(repo_path, d.b_rawpath)
            old_filepath = os.path.join(repo_path, d.a_path)
            with open(filepath, encoding='utf-8') as f:
                changed_lines = [range(1, len(f.readlines()))]

        else:  # something is seriously wrong...
            raise Exception("Unknown change type '%s'" % d.change_type)

        # we only care about python files here
        if os.path.splitext(filepath)[-1] == ".py":
            if os.sep == "\\":
                filepath = filepath.replace('/', os.sep)

                if old_filepath is not None:
                    old_filepath = old_filepath.replace('/', os.sep)

            changed_files[d.change_type][filepath] = ChangedFile(
                d.change_type,
                filepath,
                old_filepath=old_filepath,
                changed_lines=changed_lines
            )

    return changed_files['A'], changed_files['M'], changed_files['D'], changed_files['R'], changed_files['T']


def filter_ignore_sources(changed_files: DictOfChangedFile, ignore_source: ListOfString) -> DictOfChangedFile:
    if len(ignore_source) > 0:
        filtered_changed_files = {}
        for k, v in changed_files.items():
            for y in ignore_source:
                if os.path.commonpath([v.current_filepath, y]) != y:
                    filtered_changed_files[k] = v

        return filtered_changed_files

    else:
        return changed_files


def find_changed_members(changed_module: ChangedFile, repo_path: str) -> ListOfString:
    # find all changed members of changed_module
    changed_members = []
    name_extractor = ObjectNameExtractor()

    with open(os.path.join(repo_path, changed_module.current_filepath)) as f:
        contents = f.read()

    total_lines = len(contents.split('\n'))
    module_ast = ast.parse(contents)
    direct_children = list(ast.iter_child_nodes(module_ast))

    # get a set of all changed lines in changed_module
    changed_lines = set()
    for ch in changed_module.changed_lines:
        changed_lines.update(set(ch))

    # the direct children of the module correspond to the imported names in test files
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
    # in this function, we are looking for imports of the module specified by module_path in any python files under repo_root
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


def skip_item(item):
    pass


def dependencies_changed(path, object_name, change_map):
    if path in change_map.keys() and object_name in change_map[path]:
        return True

    module_ast = ast.parse(path)

    # extract imports
    imported_names_and_modules = {}
    imne = ImportModuleNameExtractor()
    extracted_imports = imne.extract(module_ast)

    for module_name, imported_names in extracted_imports:
        if module_name in sys.builtin_module_names:
            continue

        i = import_module(module_name)

        for imported_name in imported_names:
            if imported_name in imported_names_and_modules.keys() and i.__file__ not in imported_names_and_modules[imported_name]:
                imported_names_and_modules[imported_name].append(i.__file__)

            else:
                imported_names_and_modules[imported_name] = [i.__file__]

    # extract the object of interest from the ast
    definition_node_extractor = DefinitionNodeExtractor()
    definitions = definition_node_extractor.extract(module_ast)
    obj = None
    for d in definitions:
        if d.name == object_name:
            obj = d
            break

    if obj is None:
        raise Exception("Member '%s' not defined in module '%s'" % (object_name, path))

    # extract call objects from obj
    object_name_extractor = ObjectNameExtractor()
    used_names = object_name_extractor.extract(obj)
    for name in used_names:
        if name in imported_names_and_modules.keys():
            for module_path in imported_names_and_modules[name]:
                if dependencies_changed(module_path, name, change_map):
                    if module_path in change_map.keys():
                        change_map[module_path].append(name)
                    else:
                        change_map[module_path] = [name]

                    return True

                else:
                    return False







