import operator
import sys
from collections import defaultdict

from . import source


def _san_id(id: str) -> str:
    return id.replace('-', '__')


def _files_contained(root: source.DirectoryDef) -> [source.FileDef]:
    for m in root.members:
        if isinstance(m, source.ResolvedRef):
            if isinstance(m.definition, source.FileDef):
                yield m.definition
            elif isinstance(m.definition, source.DirectoryDef):
                yield from _files_contained(m.definition)


def _collect_folders(root: source.DirectoryDef, level: int, max_level: int) -> [source.DirectoryDef]:
    yield root, level
    if level < max_level:
        for m in root.members:
            if isinstance(m, source.ResolvedRef) and isinstance(m.definition, source.DirectoryDef):
                yield from _collect_folders(m.definition, level + 1, max_level)


def _subgraph(root: source.DirectoryDef, level: int, max_level: int, visible: set, prefix: str, out):
    if root not in visible:
        return
    if level < max_level:
        print('subgraph cluster_{}_{} {{'.format(prefix, _san_id(root.id)), file=out)
        print('{}_{}[label="{}", shape=none];'.format(prefix, _san_id(root.id), root.name), file=out)
        for m in root.members:
            if isinstance(m, source.ResolvedRef):
                _subgraph(m.definition, level + 1, max_level, visible, prefix, out)
        print('}', file=out)
    else:
        print('{}_{}[label="{}", shape=folder];'.format(prefix, _san_id(root.id), root.name), file=out)


def _visible_folders(root: source.DirectoryDef, interesting: set) -> set:
    visible = set()
    for m in root.members:
        if isinstance(m, source.ResolvedRef) and isinstance(m.definition, source.DirectoryDef):
            visible.update(_visible_folders(m.definition, interesting))
    if visible or root in interesting:
        visible.add(root)
    return visible


def depgraph(defs: [source.Def], depth=1, out=sys.stdout):
    dirs = set(d for d in defs if isinstance(d, source.DirectoryDef))
    seen = set()
    for d in dirs:
        for m in d.members:
            if isinstance(m, source.ResolvedRef) and m.definition in dirs:
                seen.add(m.definition)

    roots = dirs - seen
    folder_roots_l = dict((f, r) for r in roots for f in _collect_folders(r, 0, depth))
    folder_roots = dict((o, r) for r in roots for o, _ in _collect_folders(r, 0, depth))
    folders = sorted(folder_roots_l.keys(), key=operator.itemgetter(1))

    file_folders = dict((f, o) for o, _ in folders for f in _files_contained(o))

    deps = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for file, folder in file_folders.items():
        for include in file.includes:
            if isinstance(include.file, source.ResolvedRef):
                include_folder = file_folders[include.file.definition]
                if include_folder is not folder:
                    root = folder_roots[folder]
                    deps[root][folder][include_folder] += 1

    print('digraph d {rankdir=LR;\n', file=out)
    for root, r_deps in deps.items():
        prefix = root.id
        interesting = set()
        for on, to in r_deps.items():
            interesting.add(on)
            interesting.update(to.keys())
        visible = set(d for r in roots for d in _visible_folders(r, interesting))
        for r in roots:
            _subgraph(r, 0, depth, visible, prefix, out)
        for on, to in r_deps.items():
            for t, n in to.items():
                print('{0}_{1} -> {0}_{2} [label={3}];'.format(prefix, _san_id(on.id), _san_id(t.id), n), file=out)
    print('}', file=out)
