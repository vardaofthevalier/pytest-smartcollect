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

ListOrNone = typing.Union[list, None]
StrOrNone = typing.Union[str, None]
ListOfString = typing.List[str]
DictOfListOfString = typing.Dict[str, ListOfString]
ListOfTestItem = typing.List[pytest.Item]


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
        #imp = import_module(node.names[0].name)
        self.cache.append((node.names[0].name, [], 0))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        names = list(map(lambda x: x.name, node.names))
        self.cache.append((node.module, names, node.level))
        self.generic_visit(node)


class SmartCollector(object):
    def __init__(self, rootdir: str, lastfailed: ListOfString, ignore_source: ListOfString, commit_range: int, diff_current_head_with_branch: str, allow_preemptive_failures: bool, logger: logging.Logger):
        self.rootdir = rootdir
        self.lastfailed = lastfailed
        self.ignore_source = ignore_source
        self.commit_range = commit_range
        self.diff_current_head_with_branch = diff_current_head_with_branch
        self.allow_preemptive_failures = allow_preemptive_failures
        self.logger = logger
        self._encoding_detector = UniversalDetector()

    def read_file(self, fpath):
        self._encoding_detector.reset()

        f = open(fpath, "rb")
        for line in f.readlines():
            self._encoding_detector.feed(line)
            if self._encoding_detector.done:
                break
        f.close()

        if self._encoding_detector.result['encoding'] is None:
            enc = 'utf-8'

        else:
            enc = self._encoding_detector.result['encoding'].lower()

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

    def find_all_files(self, repo_path: str) -> DictOfChangedFile:
        all_files = {}
        for root, _, files in os.walk(repo_path):
            for f in files:
                if os.path.splitext(f)[-1] == ".py":
                    fpath = os.path.join(root, f)
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

    def filter_ignore_sources(self, changed_files: DictOfChangedFile) -> DictOfChangedFile:
        if len(self.ignore_source) > 0:
            filtered_changed_files = {}
            for k, v in changed_files.items():
                for y in self.ignore_source:
                    if os.path.commonpath([v.current_filepath, y]) != y:
                        filtered_changed_files[k] = v

            return filtered_changed_files

        else:
            return changed_files

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

    def find_import(self, repo_root: str, module_path: str) -> ListOfString:
        # in this function, we are looking for imports of the module specified by module_path in any python files under repo_root
        found = []
        module_name_extractor = ImportModuleNameExtractor()
        for root, _, files in os.walk(repo_root):
            for f in files:
                if os.path.splitext(f)[-1] == ".py":
                    path = os.path.join(root, f)
                    contents, _ = self.read_file(path)
                    package_path = os.path.dirname(os.path.join(root, f))
                    a = ast.parse(contents)
                    for (module, _, _) in module_name_extractor.extract(a):
                        # determine whether or not the module is part of the standard library
                        if module in sys.builtin_module_names:
                            continue

                        # determine if the imported module is relative to it's containing package or outside of it
                        if os.path.isfile(os.path.join(package_path, "%s.py" % module)) or os.path.isdir(os.path.join(package_path, module)):
                            # in the same package
                            fully_qualified_module_name = self.find_fully_qualified_module_name(os.path.join(package_path, '%s.py' % module))
                            i = import_module(fully_qualified_module_name)

                        else:
                            # in a different package
                            try:
                                i = import_module(module)  # this assumes that the module is actually installed...

                            except ImportError:
                                raise Exception("Module '%s' was imported in file '%s', but the module is not installed in the environment" % (module, os.path.join(root, f)))

                        if "__file__" in vars(i) and os.path.basename(i.__file__) == os.path.basename(module_path):
                            found.append(f)
                            break

        return found

    @staticmethod
    def find_fully_qualified_module_name(path: str) -> str:
        parts = [os.path.splitext(os.path.basename(path))[0]]

        while "__init__.py" in os.listdir(os.path.dirname(path)):
            parts.insert(0, os.path.basename(os.path.dirname(path)))
            path = os.path.dirname(path)

        return ".".join(parts)

    def dependencies_changed(self, path: str, object_name: str, change_map: DictOfListOfString, chain: ListOfString) -> bool:
        git_repo_root = self.find_git_repo_root(self.rootdir)
        all_changed_names = []

        for changed_name_list in change_map.values():
            all_changed_names.extend(changed_name_list)

        if path in change_map.keys() and object_name in change_map[path]: # if we've seen this file before and already know it to be changed, just return True
            chain.insert(0, "%s::%s" % (path, object_name))
            return True

        if git_repo_root not in os.path.commonpath([git_repo_root, path]):  # if the file is outside of the project, don't bother checking it or any of its dependencies
            return False

        # otherwise, recursively check the dependencies of this file for other known changes
        contents, _ = self.read_file(path)
        module_ast = ast.parse(contents)

        # find locally changed members
        locally_changed = []
        if path in change_map.keys():
            locally_changed = change_map[path]

        # find the object of interest in the ast
        obj = None
        for child in ast.iter_child_nodes(module_ast):
            if isinstance(child, ast.FunctionDef) or isinstance(child, ast.ClassDef) and child.name == object_name:
                if isinstance(child, ast.ClassDef):
                    for base in child.bases:
                        if base.id in all_changed_names:
                            chain.insert(0, "%s::%s (%s)" % (path, object_name, base.id))
                            return True

                obj = child

            else:
                continue

        if obj is None:  # if the object wasn't a definition and is unchanged, assume that there are no further dependencies in the chain
            return False

        # extract imports
        imported_names_and_modules = {}
        imne = ImportModuleNameExtractor()
        extracted_imports = imne.extract(module_ast)

        for (module_name, imported_names, import_level) in extracted_imports:
            if module_name in sys.builtin_module_names: # we can safely assume that builtin module changes aren't relevant
                continue

            if module_name is None:  # here we need to find the fully qualified module name for a package relative import
                assert import_level > 0
                module_name = self.find_fully_qualified_module_name(os.path.dirname(path))

            else:
                if import_level > 0: # another package relative import situation
                    module_name = [module_name]
                    src_path = path
                    while import_level > 0:
                        src_path = os.path.dirname(src_path)
                        module_name.insert(0, os.path.basename(src_path))
                        import_level -= 1

                    module_name = '.'.join(module_name)

            if len(imported_names) == 0 or '*' in imported_names:
                imp = import_module(module_name)
                imported_names = dir(imp)

            i = import_module(module_name)

            if '__file__' in vars(i):
                for imported_name in imported_names:
                    if imported_name in imported_names_and_modules.keys() and i.__file__ not in imported_names_and_modules[imported_name]:
                        imported_names_and_modules[imported_name].append(i.__file__)

                    else:
                        imported_names_and_modules[imported_name] = [i.__file__]

        # extract call objects from obj
        object_name_extractor = ObjectNameExtractor()
        used_names = object_name_extractor.extract(obj)

        for name in used_names:
            if name in locally_changed:
                if path in change_map.keys() and name in change_map[path]:
                    return True

            if name in imported_names_and_modules.keys():
                for module_path in imported_names_and_modules[name]:
                    if self.dependencies_changed(module_path, name, change_map, chain):
                        if module_path in change_map.keys():
                            change_map[module_path].append(name)
                        else:
                            change_map[module_path] = [name]

                        return True

                    else:
                        return False

        return False

    def run(self, items):
        git_repo_root = self.find_git_repo_root(self.rootdir) # recursive function still needs the parameter even though the initial value is a member of self

        repo = Repo(git_repo_root)

        total_commits_on_head = len(list(repo.iter_commits("HEAD")))

        if total_commits_on_head < 2:
            added_files = self.find_all_files(git_repo_root)
            modified_files = {}
            deleted_files = {}
            renamed_files = {}
            changed_filetype_files = {}

        else:  # inspect the diff
            added_files, modified_files, deleted_files, renamed_files, changed_filetype_files = self.find_changed_files(repo, git_repo_root)

        # search for a few problems preemptively
        for deleted in deleted_files.values():
            # check if any deleted files (or the old path for renamed files) are imported anywhere in the project
            try:
                found = self.find_import(self.rootdir, deleted.current_filepath)

            except Exception as e:
                if self.allow_preemptive_failures:
                    raise e

                else:
                    self.logger.warning("triggered by preemptive failure: " + str(e))

            else:
                if len(found) > 0:
                    msg = ""
                    for f in found:
                        msg += "Module from deleted file '%s' imported in file '%s'\n" % (deleted.current_filepath, f)

                    if self.allow_preemptive_failures:
                        raise Exception(msg)

                    self.logger.warning(msg)

        for renamed in renamed_files.values():
            # check if any renamed files are imported by their old name
            try:
                found = self.find_import(self.rootdir, renamed.old_filepath)

            except Exception as e:
                if self.allow_preemptive_failures:
                    raise e

                else:
                    self.logger.warning("triggered by preemptive failure: " + str(e))

            else:
                if len(found) > 0:
                    msg = ""
                    for f in found:
                        msg += "Module from renamed file ('%s' -> '%s') imported incorrectly using it's old name in file '%s'\n" % (
                            renamed.old_filepath, renamed.current_filepath, f)

                    if self.allow_preemptive_failures:
                        raise Exception(msg)

                    self.logger.warning(msg)

        changed_to_py = {}
        for changed_filetype in changed_filetype_files.values():
            # check if any files that changed type from python to something else are still being imported somewhere else in the project
            if os.path.splitext(changed_filetype.old_filepath)[-1] == ".py":
                found = self.find_import(self.rootdir, changed_filetype.old_filepath)
                if len(found) > 0:
                    msg = ""
                    for f in found:
                        msg += "Module from renamed file ('%s' -> '%s') no longer exists but is imported in file '%s'\n)" % (
                            changed_filetype.old_filepath, changed_filetype.current_filepath, f)

                    if self.allow_preemptive_failures:
                        raise Exception(msg)

                    self.logger.warning(msg)

            elif os.path.splitext(changed_filetype.current_filepath) == ".py":
                changed_to_py[changed_filetype.current_filepath] = changed_filetype

        changed_files = {}
        changed_files.update(changed_to_py)
        changed_files.update(modified_files)
        changed_files.update(renamed_files)
        changed_files.update(added_files)

        # ignore anything explicitly set in --ignore-source flags
        changed_files = self.filter_ignore_sources(changed_files)

        # determine all changed members of each of the changed files (if applicable)
        changed_members_and_modules = {path: self.find_changed_members(ch, git_repo_root) for path, ch in changed_files.items() }

        for test in items:
            # if the test is new, run it anyway
            if str(test.fspath) in changed_files.keys() and changed_files[str(test.fspath)].change_type == 'A':
                self.logger.warning("Test '%s' is new, so will be run regardless of changes to the code it tests" % test.nodeid)
                continue

            # if the test failed in the last run, run it anyway
            if test.nodeid in self.lastfailed:
                self.logger.warning("Test '%s' failed on the last run, so will be run regardless of changes" % test.nodeid)
                continue

            # if the test is already skipped, just ignore it
            if test.get_marker('skip'):
                self.logger.info("Found skip marker on test '%s' -- ignoring" % test.nodeid)
                continue

            # otherwise, check the dependency chain
            chain = []
            if self.dependencies_changed(str(test.fspath), test.name.split('[')[0], changed_members_and_modules, chain):  # TODO: figure out a better way to handle test names of parameterized tests
                self.logger.warning(
                    "Test '%s' will run because one of it's dependencies changed (%s)" % (test.nodeid, ' -> '.join(chain)))
                continue

            else:
                self.logger.info("Test '%s' doesn't touch new or modified code -- SKIPPING" % test.nodeid)
                skip = pytest.mark.skip(reason="This test doesn't touch new or modified code")
                test.add_marker(skip)






