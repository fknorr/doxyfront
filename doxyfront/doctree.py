from collections import defaultdict
from enum import Enum
import os
import jinja2

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


def render(title: str or None, definition: source.Def or None, members: [source.Def], file):
    details = None
    if definition is not None:
        if definition.detailed_description is not None:
            details = definition.detailed_description.render_html()

    by_cat = defaultdict(list)
    for m in members:
        by_cat[category(m)].append({
            'id': m.id,
            'name': m.id,
            'signature': m.signature_html(),
            'brief': m.brief_description.render_plaintext() if m.brief_description else ''
        })

    if title is not None:
        window_title = title
        page_title = title
    else:
        window_title = definition.signature_plaintext()
        page_title = '<span class="def">{}</span>'.format(definition.signature_html())

    member_cats = list(sorted((c.name.lower(), list(sorted(m, key=lambda m: m['name'].lower())))
                              for (_, c), m in by_cat.items()))

    global template
    file.write(template.render(window_title=window_title,
                               page_title=page_title,
                               details=details,
                               member_cats=member_cats
                               ))


def doctree(defs: [source.Def], outdir: str):
    env = jinja2.Environment(
        loader=jinja2.PackageLoader('doxyfront', ''),
        autoescape=jinja2.select_autoescape(['html']),
        trim_blocks=True,
    )
    global template
    template = env.get_template('doctree.html')

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
            render(None, d, members, file=f)

    roots = set(defs) - non_global
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        render('Index', None, roots, file=f)
