import os
import operator
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


def _subgraph(root: source.DirectoryDef, level: int, max_level: int, out):
    if level < max_level:
        print('subgraph cluster_{} {{'.format(_san_id(root.id)), file=out)
        print('{}[label="{}", shape=none];'.format(_san_id(root.id), root.name), file=out)
        for m in root.members:
            if isinstance(m, source.ResolvedRef) and isinstance(m.definition, source.DirectoryDef):
                _subgraph(m.definition, level + 1, max_level, out)
        print('}', file=out)
    else:
        print('{}[label="{}", shape=folder];'.format(_san_id(root.id), root.name), file=out)


def depgraph(defs: [source.Def], out):
    dirs = set(d for d in defs if isinstance(d, source.DirectoryDef))
    seen = set()
    for d in dirs:
        for m in d.members:
            if isinstance(m, source.ResolvedRef) and m.definition in dirs:
                seen.add(m.definition)

    roots = dirs - seen
    folders = [f for r in roots for f in _collect_folders(r, 0, 1)]
    folders.sort(key=operator.itemgetter(1))

    file_folders = dict((f, o) for o, _ in folders for f in _files_contained(o))

    deps = set()
    for file, folder in file_folders.items():
        for include in file.includes:
            if isinstance(include.file, source.ResolvedRef):
                include_folder = file_folders[include.file.definition]
                if include_folder is not folder:
                    deps.add((folder, include_folder))

    print('digraph d {\n', file=out)
    for r in roots:
        _subgraph(r, 0, 1, out)
    for r, s in deps:
        print('{} -> {};'.format(_san_id(r.id), _san_id(s.id)), file=out)
    print('}', file=out)
