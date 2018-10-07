import re
import os
import sys
import ast
import pytest
import typing
import logging
from git import Repo
from importlib import import_module
from chardet import UniversalDetector
from enum import Enum

ListOrNone = typing.Union[list, None]
StrOrNone = typing.Union[str, None]
ListOfString = typing.List[str]
DictOfListOfString = typing.Dict[str, ListOfString]
DictOfString = typing.Dict[str, str]
ListOfTestItem = typing.List[pytest.Item]


class ModuleGraphNodeColor(Enum):
    WHITE = 1
    GREY = 2
    BLACK = 3


class ModuleGraphNode(object):
    def __init__(self, module_path: str, name:str, is_test_function:bool=False, dependencies: typing.List['ModuleGraphNode']=None, changed: bool=False, color: ModuleGraphNodeColor=ModuleGraphNodeColor.WHITE):
        self.module_path = module_path
        self.name = name
        self.dependencies = dependencies
        self.changed = changed
        self.color = color
        self.is_test_function = is_test_function

    def reset_color(self):
        self.color = 'W'
        

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
        self._ast_filepath = None

    def extract(self, node) -> list:
        self.cache.clear()
        self.generic_visit(node)
        return self.cache


class BaseClassNameExtractor(GenericVisitor):
    def __init__(self):
        super(BaseClassNameExtractor, self).__init__()

    def visit_ClassDef(self, node):
        for base in node.bases:
            self.generic_visit(base)

    def visit_Name(self, node):
        if ast.Attribute in [type(x) for x in ast.iter_child_nodes(node)]:
            self.generic_visit(node)

        else:
            self.cache.append(node.id)

    def visit_Attribute(self, node):
        self.cache.append(node.attr)


class AssignmentNodeExtractor(GenericVisitor):
    def __init__(self):
        super(AssignmentNodeExtractor, self).__init__()

    def visit_Assign(self, node):
        for t in node.targets:
            self.cache.append(t)


class ObjectNameExtractor(GenericVisitor):
    def __init__(self):
        super(ObjectNameExtractor, self).__init__()

    def visit_Call(self, node):
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                self.cache.append(child.id)


class DefinitionNodeExtractor(GenericVisitor):
    def __init__(self):
        super(DefinitionNodeExtractor, self).__init__()

    def visit_FunctionDef(self, node):
        self.cache.append(node)

    def visit_ClassDef(self, node):
        self.cache.append(node)
        self.generic_visit(node)


class ImportModuleNameExtractor(GenericVisitor):
    def __init__(self):
        super(ImportModuleNameExtractor, self).__init__()

    def visit_Import(self, node):
        self.cache.append((node.names[0].name, [], 0))

    def visit_ImportFrom(self, node):
        names = list(map(lambda x: x.name, node.names))
        self.cache.append((node.module, names, node.level))


class FixtureExtractor(GenericVisitor):
    def __init__(self):
        super(FixtureExtractor, self).__init__()

    def visit_FunctionDef(self, node):
        if len(node.decorator_list) > 0:
            for dec in node.decorator_list:
                if isinstance(dec, ast.Attribute):
                    if dec.attr == 'fixture':
                        self.cache.append(node)

                elif isinstance(dec, ast.Name):
                    if dec.id == 'fixture':
                        self.cache.append(node)


class SmartCollector(object):
    def __init__(self, rootdir: str, lastfailed: ListOfString, ignore_source: ListOfString, commit_range: int, diff_current_head_with_branch: str, allow_preemptive_failures: bool, logger: logging.Logger):
        self.rootdir = rootdir
        self.git_repo_root = None
        self.lastfailed = lastfailed
        self.ignore_source = ignore_source
        self.commit_range = commit_range
        self.diff_current_head_with_branch = diff_current_head_with_branch
        self.allow_preemptive_failures = allow_preemptive_failures
        self.logger = logger
        self.packages = []
        self.encoding_detector = UniversalDetector()

        self.fixture_map = {}
        self.changed_members_and_modules = {}
        self.project_nodes = {}

    def read_file(self, fpath):
        self.encoding_detector.reset()

        f = open(fpath, "rb")
        for line in f.readlines():
            self.encoding_detector.feed(line)
            if self.encoding_detector.done:
                break
        f.close()

        if self.encoding_detector.result['encoding'] is None:
            enc = 'utf-8'

        else:
            enc = self.encoding_detector.result['encoding'].lower()

        with open(fpath, encoding=enc) as f:
            lines = f.readlines()

        contents = ''.join(lines)
        linecount = len(lines)

        try:
            ast.parse(contents)

        except Exception as e:
            raise Exception("Couldn't read file '%s' -- %s" % (fpath, str(e)))

        return contents, linecount

    def find_git_repo_root(self, dir: str) -> str:
        if ".git" in os.listdir(dir):
            return dir

        else:
            if os.path.dirname(dir) == dir:
                raise Exception("No git repo found relative to the pytest rootdir")

            else:
                return self.find_git_repo_root(os.path.dirname(dir))

    @staticmethod
    def find_packages(dir: str) -> ListOfString:
        packages = []
        is_valid_package = lambda x: True if os.path.isdir(x) and '__init__.py' in os.listdir(x) else False

        for root, _, _ in os.walk(dir):
            abs_root = os.path.abspath(root)

            if is_valid_package(abs_root):
                packages.append(abs_root)

        return packages

    def find_all_files(self, repo_path: str) -> DictOfChangedFile:
        all_files = {}
        for root, _, files in os.walk(repo_path):
            for f in files:
                fpath = os.path.join(root, f)
                if os.path.splitext(f)[-1] == ".py" and not self.should_ignore_source_file(fpath):
                    contents, linecount = self.read_file(fpath)
                    all_files[fpath] = ChangedFile(
                        change_type='A',
                        old_filepath=None,
                        current_filepath=fpath,
                        changed_lines=[range(1, linecount)]
                    )

        return all_files

    def find_changed_files(self, repo: Repo, repo_path: str) -> (DictOfChangedFile, DictOfChangedFile, DictOfChangedFile, DictOfChangedFile, DictOfChangedFile):
        changed_files = {
            'A': {},
            'M': {},
            'D': {},
            'R': {},
            'T': {}
        }

        current_head = repo.head.commit
        previous_commits = repo.commit("%s~%d" % (self.diff_current_head_with_branch, self.commit_range))
        diffs = previous_commits.diff(current_head)
        diffs_with_patch = previous_commits.diff(current_head, create_patch=True)

        for idx, d in enumerate(diffs):
            diff_text = diffs_with_patch[idx].diff.decode('utf-8').replace('\r', '')
            if re.match('^Binary files.*', diff_text) or len(diff_text) == 0:  # TODO: figure out if there are any other special cases where the diff information is non-standard
                continue
            diff_lines_spec = diff_text.split('\n')[0].split('@@')[1].strip().replace('+', '').replace('-', '')
            changed_lines = None
            old_filepath = None

            if d.change_type == 'A':  # added paths
                filepath = os.path.join(repo_path, d.a_path)
                if os.path.splitext(filepath)[-1] != '.py':
                    continue

                _, linecount = self.read_file(filepath)
                changed_lines = [range(1, linecount)]

            elif d.change_type == 'M':  # modified paths
                filepath = os.path.join(repo_path, d.a_path)
                if os.path.splitext(filepath)[-1] != '.py':
                    continue
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
                if os.path.splitext(filepath)[-1] != '.py':
                    continue

            elif d.change_type == 'R':  # renamed paths
                filepath = os.path.join(repo_path, d.b_path)
                if os.path.splitext(filepath)[-1] != '.py':
                    continue
                old_filepath = os.path.join(repo_path, d.a_path)
                _, linecount = self.read_file(filepath)
                changed_lines = [range(1, linecount)]

            elif d.change_type == 'T':  # changed file types
                filepath = os.path.join(repo_path, d.b_rawpath)
                if os.path.splitext(filepath)[-1] != '.py':
                    continue
                old_filepath = os.path.join(repo_path, d.a_path)
                _, linecount = self.read_file(filepath)
                changed_lines = [range(1, linecount)]

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

    def should_ignore_source_file(self, source_file: str) -> bool:
        if self.ignore_source is not None:
            for ign in self.ignore_source:
                if os.path.commonpath([source_file, ign]) == ign:
                    return True

        return False

    def find_changed_members(self, changed_module: ChangedFile, repo_path: str) -> ListOfString:
        # find all changed members of changed_module
        changed_members = []
        name_extractor = ObjectNameExtractor()

        contents, total_lines = self.read_file(os.path.join(repo_path, changed_module.current_filepath))
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

    @staticmethod
    def find_fully_qualified_module_name(path: str) -> str:
        parts = [os.path.splitext(os.path.basename(path))[0]]

        while "__init__.py" in os.listdir(os.path.dirname(path)):
            parts.insert(0, os.path.basename(os.path.dirname(path)))
            path = os.path.dirname(path)

        return ".".join(parts)

    @staticmethod
    def file_in_project(dir, f):
        if dir not in os.path.commonpath([dir, f]):
            return False

        return True

    @staticmethod
    def add_key_and_value_to_linked_list(module_path, member, m):
        if module_path not in m.keys():
            m[module_path] = [member]

        else:
            if member not in m[module_path]:
                m[module_path].append(member)

    # def dependencies_changed(self, path: str, object_name: str, change_map: DictOfListOfString, unchanged_map: DictOfListOfString, visited_map: DictOfListOfString, chain: ListOfString) -> bool:
    #     git_repo_root = self.find_git_repo_root(self.rootdir)
    # 
    #     if path in change_map.keys() and object_name in change_map[path]: # if we've seen this file before and already know it to be changed, just return True
    #         chain.append("%s::%s" % (path, object_name))
    #         return True
    # 
    #     if path in unchanged_map.keys() and object_name in unchanged_map[path]:
    #         return False
    # 
    #     if not self.file_in_project(git_repo_root, path):  # if the file is outside of the project, don't bother checking it or any of its dependencies
    #         return False
    # 
    #     # if this module and object have been visited before but aren't yet marked changed or unchanged, then we have detected a dependency cycle
    #     if path in visited_map.keys() and object_name in visited_map[path]:
    #         raise Exception("Dependency cycle detected: " + ' -> '.join(chain))
    # 
    #     else:
    #         self.add_key_and_value_to_linked_list(path, object_name, visited_map)
    # 
    #     # otherwise, recursively check the dependencies of this file for other known changes
    #     contents, _ = self.read_file(path)
    #     module_ast = ast.parse(contents)
    # 
    #     # find locally changed members
    #     locally_changed = []
    #     if path in change_map.keys():
    #         locally_changed = change_map[path]
    # 
    #     # find the object of interest in the ast
    #     obj = None
    #     definition_extractor = DefinitionNodeExtractor()
    #     definition_nodes = definition_extractor.extract(module_ast)
    # 
    #     for child in definition_nodes:
    #         if child.name == object_name:
    #             obj = child
    #             break
    # 
    #         else:
    #             continue
    # 
    #     if obj is None:  # if the object wasn't a definition and is unchanged, assume that there are no further dependencies in the chain
    #         self.add_key_and_value_to_linked_list(path, object_name, unchanged_map)
    #         return False
    # 
    #     # extract imports
    #     imported_names_and_modules = {}
    #     imne = ImportModuleNameExtractor()
    #     extracted_imports = imne.extract(module_ast)
    # 
    #     for (module_name, imported_names, import_level) in extracted_imports:
    #         if module_name in sys.builtin_module_names: # we can safely assume that builtin module changes aren't relevant
    #             continue
    # 
    #         if module_name is None:  # here we need to find the fully qualified module name for a package relative import
    #             assert import_level > 0
    #             module_name = self.find_fully_qualified_module_name(os.path.dirname(path))
    # 
    #         else:
    #             if import_level > 0: # another package relative import situation
    #                 module_name = [module_name]
    #                 src_path = path
    #                 while import_level > 0:
    #                     src_path = os.path.dirname(src_path)
    #                     module_name.insert(0, os.path.basename(src_path))
    #                     import_level -= 1
    # 
    #                 module_name = '.'.join(module_name)
    # 
    #         if len(imported_names) == 0 or '*' in imported_names:
    #             imp = import_module(module_name)
    #             imported_names = dir(imp)
    # 
    #         i = import_module(module_name)
    # 
    #         for imported_name in imported_names:
    #             o = getattr(i, imported_name)
    # 
    #             if hasattr(o, '__module__') and o.__module__ not in sys.builtin_module_names and o.__module__ is not None:
    #                 f = import_module(o.__module__).__file__
    # 
    #             else:
    #                 f = None
    # 
    #             if hasattr(i, '__file__') and self.file_in_project(git_repo_root, i.__file__):
    #                 self.add_key_and_value_to_linked_list(imported_name, i.__file__, imported_names_and_modules)
    # 
    #             if f is not None and self.file_in_project(git_repo_root, f):
    #                 self.add_key_and_value_to_linked_list(imported_name, f, imported_names_and_modules)
    # 
    #     # check base classes recursively
    #     base_class_name_extractor = BaseClassNameExtractor()
    #     if isinstance(obj, ast.ClassDef):
    #         for base_name in base_class_name_extractor.extract(obj):
    #             if base_name in imported_names_and_modules.keys():
    #                 base_class_module_paths = imported_names_and_modules[base_name]
    #                 for path in base_class_module_paths:
    #                     if self.dependencies_changed(path, base_name, change_map, unchanged_map, visited_map, chain):
    #                         self.add_key_and_value_to_linked_list(path, base_name, change_map)
    #                         return True
    # 
    #     # extract call objects from obj
    #     object_name_extractor = ObjectNameExtractor()
    #     used_names = set(object_name_extractor.extract(obj))
    # 
    #     for name in used_names:
    #         if name == object_name:  # to avoid infinite recursion when a class invokes it's own class methods or if a recursive function calls itself
    #             continue
    # 
    #         if name in locally_changed:
    #             if path in change_map.keys() and name in change_map[path]:
    #                 return True
    # 
    #         if name in imported_names_and_modules.keys():
    #             for module_path in imported_names_and_modules[name]:
    #                 if self.dependencies_changed(module_path, name, change_map, unchanged_map, visited_map, chain):
    #                     self.add_key_and_value_to_linked_list(module_path, name, change_map)
    #                     return True
    # 
    #     self.add_key_and_value_to_linked_list(path, object_name, unchanged_map)
    #     return False

    def is_changed(self, module, name):
        if module in self.changed_members_and_modules.keys() and name in self.changed_members_and_modules[module]:
            return True

        return False

    def find_dependencies(self, module: str, member: str, is_test_function: bool=False) -> typing.List[ModuleGraphNode]:
        if not self.file_in_project(self.git_repo_root, module) or self.should_ignore_source_file(module):
            return []

        dependencies = []
        contents, _ = self.read_file(module)
        module_ast = ast.parse(contents)

        # find the member of interest in the ast
        obj = None
        definition_extractor = DefinitionNodeExtractor()
        definition_nodes = definition_extractor.extract(module_ast)

        assignment_extractor = AssignmentNodeExtractor()
        assignment_targets = assignment_extractor.extract(module_ast)
        local_objects = []
        for a in assignment_targets:
            if isinstance(a, ast.Name):
                local_objects.append(a)

        local_objects.extend(definition_nodes)

        for child in local_objects:
            if isinstance(child, ast.FunctionDef) or isinstance(child, ast.AsyncFunctionDef) or isinstance(child, ast.ClassDef):
                child_name = child.name

            elif isinstance(child, ast.Name):
                child_name = child.id

            else:
                raise Exception("Local object name unknown")

            if child_name == member:
                obj = child
                break

            else:
                continue

        if obj is None:
            return []

        if is_test_function:
            # check dependencies within any defined fixtures
            test_args = set(obj.args.args)
            if module not in self.fixture_map.keys():
                fixture_extractor = FixtureExtractor()
                fixtures = fixture_extractor.extract(module_ast)
                self.fixture_map[module] = set([x.name for x in fixtures])

            for test_module, fixture_list in self.fixture_map.items():
                used_fixtures = fixture_list.intersection(test_args)
                for fixture in used_fixtures:
                    if (test_module, fixture) not in self.project_nodes.keys():
                        self.project_nodes[(test_module, fixture)] = ModuleGraphNode(test_module, fixture, changed=self.is_changed(test_module, fixture))

                    dependencies.append(self.project_nodes[(test_module, fixture)])

        # extract imports
        imported_names_and_modules = {}
        imne = ImportModuleNameExtractor()
        extracted_imports = imne.extract(module_ast)

        for (module_name, imported_names, import_level) in extracted_imports:
            if module_name in sys.builtin_module_names:  # we can safely assume that builtin module changes aren't relevant
                continue

            if module_name is None:  # here we need to find the fully qualified module name for a package relative import
                assert import_level > 0
                module_name = self.find_fully_qualified_module_name(os.path.dirname(module))

            else:
                if import_level > 0:  # another package relative import situation
                    module_name = [module_name]
                    src_path = module
                    while import_level > 0:
                        src_path = os.path.dirname(src_path)
                        module_name.insert(0, os.path.basename(src_path))
                        import_level -= 1

                    module_name = '.'.join(module_name)

            if len(imported_names) == 0 or '*' in imported_names:
                imp = import_module(module_name)
                imported_names = dir(imp)

            i = import_module(module_name)

            for imported_name in imported_names:
                o = getattr(i, imported_name)

                if hasattr(o,
                           '__module__') and o.__module__ not in sys.builtin_module_names and o.__module__ is not None:
                    f = import_module(o.__module__).__file__

                else:
                    f = None

                if hasattr(i, '__file__') and self.file_in_project(self.git_repo_root, i.__file__):
                    self.add_key_and_value_to_linked_list(imported_name, i.__file__, imported_names_and_modules)

                if f is not None and self.file_in_project(self.git_repo_root, f):
                    self.add_key_and_value_to_linked_list(imported_name, f, imported_names_and_modules)

        # check base classes recursively
        base_class_name_extractor = BaseClassNameExtractor()
        if isinstance(obj, ast.ClassDef):
            for base_name in base_class_name_extractor.extract(obj):
                if base_name in imported_names_and_modules.keys():
                    base_class_module_paths = imported_names_and_modules[base_name]
                    for path in base_class_module_paths:
                        if (path, base_name) not in self.project_nodes.keys():
                            self.project_nodes[(path, base_name)] = ModuleGraphNode(path, base_name, changed=self.is_changed(path, base_name))

                        dependencies.append(self.project_nodes[(path, base_name)])

        # find all locally defined objects
        member_extractor = ObjectNameExtractor()

        # extract call objects from obj
        used_names = set(member_extractor.extract(obj))
        local_names = []

        for local_obj in local_objects:
            if isinstance(local_obj, ast.FunctionDef) or isinstance(local_obj, ast.AsyncFunctionDef) or isinstance(local_obj, ast.ClassDef):
                local_names.append(local_obj.name)

            elif isinstance(local_obj, ast.Name):
                local_names.append(local_obj.id)

        for name in used_names:
            if name == member:  # to avoid infinite recursion when a class invokes it's own class methods or if a recursive function calls itself
                continue

            elif name in local_names:
                if (module, name) not in self.project_nodes.keys():
                    self.project_nodes[(module, name)] = ModuleGraphNode(module, name, changed=self.is_changed(module, name))

                dependencies.append(self.project_nodes[(module, name)])

            elif name in imported_names_and_modules.keys():
                for module_path in imported_names_and_modules[name]:
                    if (module_path, name) not in self.project_nodes.keys():
                        self.project_nodes[(module_path, name)] = ModuleGraphNode(module_path, name, changed=self.is_changed(module_path, name))

                    dependencies.append(self.project_nodes[(module_path, name)])

        return dependencies

    def run(self, items):
        log_records = []
        self.git_repo_root = self.find_git_repo_root(self.rootdir)
        self.packages = self.find_packages(self.git_repo_root)

        for p in self.packages:
            sys.path.insert(0, p)

        try:
            repo = Repo(self.git_repo_root)

            total_commits_on_head = len(list(repo.iter_commits("HEAD")))

            if self.diff_current_head_with_branch == repo.active_branch.name and total_commits_on_head < 2:
                added_files = self.find_all_files(self.git_repo_root)
                modified_files = {}
                deleted_files = {}
                renamed_files = {}
                changed_filetype_files = {}

            else:  # inspect the diff
                added_files, modified_files, deleted_files, renamed_files, changed_filetype_files = self.find_changed_files(repo, self.git_repo_root)

            changed_to_py = {}
            for changed_filetype in changed_filetype_files.values():
                if os.path.splitext(changed_filetype.current_filepath) == ".py":
                    changed_to_py[changed_filetype.current_filepath] = changed_filetype

            changed_files = {}
            changed_files.update(changed_to_py)
            changed_files.update(modified_files)
            changed_files.update(renamed_files)
            changed_files.update(added_files)

            # ignore anything explicitly set in --ignore-source flags
            changed_files = {k: v for k, v in changed_files.items() if not self.should_ignore_source_file(k)}

            # determine all changed members of each of the changed files (if applicable)
            self.changed_members_and_modules = {
                path: self.find_changed_members(ch, self.git_repo_root) for path, ch in changed_files.items()
            }

            test_count = 0
            for test in items:
                test_name = test.name.split('[')[0]

                # if the test failed in the last run, run it anyway
                if test.nodeid in self.lastfailed:
                    log_records.append(
                        ('RUN', test.nodeid, "Failed on last run")
                    )
                    self.logger.info(
                        "Test '%s' failed on the last run, so will be run regardless of changes" % test.nodeid)
                    test_count += 1
                    continue

                # if the test is already skipped, just ignore it
                if test.get_marker('skip'):
                    log_records.append(
                        ('SKIP', test.nodeid, "Found skip marker")
                    )
                    self.logger.info("Found skip marker on test '%s' -- ignoring" % test.nodeid)
                    continue

                # otherwise, check the dependency chain from inside the test function
                module_spec = (str(test.fspath), test_name)
                t = ModuleGraphNode(*module_spec, changed=self.is_changed(*module_spec))
                t.dependencies = self.find_dependencies(*module_spec, is_test_function=True)
                self.project_nodes[module_spec] = t

                # construct the entire graph
                queue = []
                queue.append(t)
                while len(queue) > 0:
                    current = queue.pop(0)
                    if current.dependencies is None:
                        current.dependencies = self.find_dependencies(current.module_path, current.name)

                    queue.extend(current.dependencies)

                # use dfs for guarding against import cycles in the project
                stack = []
                stack.insert(0, t)
                found_changed_dep = False
                while len(stack) > 0:
                    current = stack.pop(0)
                    if current.changed:
                        found_changed_dep = True
                        stack.insert(0, current)
                        break

                    if current.color == ModuleGraphNodeColor.WHITE:
                        current.color = ModuleGraphNodeColor.GREY
                        stack.insert(0, current)
                        for dep in current.dependencies:
                            stack.insert(0, dep)

                    elif current.color == ModuleGraphNodeColor.GREY:
                        for d in current.dependencies:
                            if d.color != ModuleGraphNodeColor.BLACK:
                                stack.insert(0, current)
                                dependency_chain = ' -> '.join(
                                    list(reversed(list(map(lambda x: "%s::%s" % (x.module_path, x.name), stack)))))
                                raise Exception("Import cycle detected in project! " + dependency_chain)

                        current.color = ModuleGraphNodeColor.BLACK

                if not found_changed_dep:
                    log_records.append(
                        ('SKIP', test.nodeid, "Unchanged")
                    )
                    skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                    test.add_marker(skip)

                else:
                    for node in stack:
                        node.changed = True

                    dependency_chain = ' -> '.join(
                        list(reversed(list(map(lambda x: "%s::%s" % (x.module_path, x.name), stack))))
                    )
                    log_records.append(('RUN', test.nodeid, "Dependency changed: " + dependency_chain))
                    test_count += 1

                for node in self.project_nodes.values():
                    node.color = ModuleGraphNodeColor.WHITE

            # TODO: add option to write to csv
            import csv
            with open("results.csv", "w") as csvfile:
                csvwriter = csv.writer(csvfile)
                for row in log_records:
                    csvwriter.writerow(list(row))

            self.logger.warning("Total tests selected to run: " + str(test_count))
            self._revert_syspath()

        except Exception as e:
            self._handle_exception(str(e))

    def _handle_exception(self, msg):
        self._revert_syspath()
        raise Exception(msg)

    def _revert_syspath(self):
        for _ in range(0, len(self.packages)):
            sys.path.pop(0)






