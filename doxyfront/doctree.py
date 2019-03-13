from collections import defaultdict
from enum import Enum
import os

from . import source


class SymbolCategory(Enum):
    DIRECTORY = 0
    FILE = 1
    NAMESPACE = 2
    MACRO = 3
    TYPE = 4
    FUNCTION = 5
    PROPERTY = 6
    VARIABLE = 7
    OTHER = 8


CATEGORIES = [
    ([source.DirectoryDef], SymbolCategory.DIRECTORY),
    ([source.FileDef], SymbolCategory.FILE),
    ([source.NamespaceDef], SymbolCategory.NAMESPACE),
    ([source.MacroDef], SymbolCategory.MACRO),
    ([source.TypedefDef, source.ClassDef, source.EnumDef], SymbolCategory.TYPE),
    ([source.FunctionDef], SymbolCategory.FUNCTION),
    ([source.PropertyDef], SymbolCategory.PROPERTY),
    ([source.VariableDef], SymbolCategory.VARIABLE),
]


def category(d: source.Def) -> (int, str):
    for i, (classes, cat) in enumerate(CATEGORIES):
        for c in classes:
            if isinstance(d, c):
                return i, cat
    return len(CATEGORIES), SymbolCategory.OTHER


def category_key(d: source.Def) -> int:
    return category(d)[0]


def render(title: str, members: [source.Def], file):
    print('<!DOCTYPE html><html><head><title>{0}</title></head><body><h1>{0}</h1>'.format(title), file=file)
    by_cat = defaultdict(list)
    for m in members:
        by_cat[category(m)].append(m)
    for (_, cat), mlist in sorted(by_cat.items()):
        print('<h2>{}s</h2><ul>'.format(cat.name.lower()), file=file)
        for m in sorted(mlist, key=lambda m: m.name.lower()):
            print('<li><a href="{}.html">{} {}</a></li>'.format(m.id, m.kind(), m.name), file=file)
        print('</ul>', file=file)
    print('</body></html>', file=file)


def doctree(defs: [source.Def], outdir: str):
    non_global = set()
    for d in defs:
        members = []
        if isinstance(d, source.CompoundDef):
            for m in d.members:
                if isinstance(m, source.ResolvedRef):
                    members.append(m.definition)
                    if not isinstance(d, source.FileDef):
                        non_global.add(m.definition)
        with open(os.path.join(outdir, d.id + '.html'), 'w') as f:
            render('{} {}'.format(d.kind(), d.name), members, file=f)

    roots = set(defs) - non_global
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        render('Index', roots, file=f)
