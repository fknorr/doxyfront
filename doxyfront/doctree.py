from collections import defaultdict
from enum import Enum
import os
import jinja2

from .model import *


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
    ([DirectoryDef], SymbolCategory.DIRECTORY),
    ([FileDef], SymbolCategory.FILE),
    ([NamespaceDef], SymbolCategory.NAMESPACE),
    ([MacroDef], SymbolCategory.MACRO),
    ([TypedefDef, ClassDef, EnumDef], SymbolCategory.TYPE),
    ([FunctionDef], SymbolCategory.FUNCTION),
    ([PropertyDef], SymbolCategory.PROPERTY),
    ([VariableDef], SymbolCategory.VARIABLE),
]


def category(d: Def) -> (int, str):
    for i, (classes, cat) in enumerate(CATEGORIES):
        for c in classes:
            if isinstance(d, c):
                return i, cat
    return len(CATEGORIES), SymbolCategory.OTHER


def category_key(d: Def) -> int:
    return category(d)[0]


def render(title: str or None, definition: Def or None, members: [Def], file):
    context = set()
    details = None
    include = None
    if definition is not None:
        scope = definition
        while scope is not None:
            context.add(scope)
            scope = scope.scope_parent
        if definition.detailed_description is not None:
            details = definition.detailed_description.render_html(context)
        if isinstance(definition, SymbolDef) and definition.file_parent is not None:
            include = '#include &lt;{}&gt;'.format(definition.file_parent.path_html())

    by_cat = defaultdict(list)
    for m in members:
        by_cat[category(m)].append({
            'id': m.id,
            'name': m.id,
            'vis': m.visibility.value if m.visibility else '',
            'signature': m.signature_html(context),
            'brief': m.brief_description.render_plaintext(context) if m.brief_description else ''
        })

    if title is not None:
        window_title = title
        page_title = title
    else:
        window_title = definition.signature_plaintext(context, fully_qualified=True)
        page_title = '<span class="def">{}</span>'.format(
            definition.signature_html(context, fully_qualified=True))

    member_cats = list(sorted((c.name.lower(), list(sorted(m, key=lambda m: m['name'].lower())))
                              for (_, c), m in by_cat.items()))

    global template
    file.write(template.render(window_title=window_title,
                               page_title=page_title,
                               details=details,
                               member_cats=member_cats,
                               include=include,
                               ))


def doctree(defs: [Def], outdir: str):
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
        if isinstance(d, CompoundDef):
            for m in d.members:
                if isinstance(m, ResolvedRef):
                    members.append(m.definition)
                    if not isinstance(d, FileDef):
                        non_global.add(m.definition)
        with open(os.path.join(outdir, d.id + '.html'), 'w') as f:
            render(None, d, members, file=f)

    roots = set(defs) - non_global
    symbol_roots = set(r for r in roots if isinstance(r, SymbolDef))
    with open(os.path.join(outdir, 'symbol_index.html'), 'w') as f:
        render('Symbol Index', None, symbol_roots, file=f)
    file_roots = set(r for r in roots if isinstance(r, DirectoryDef)
                  or isinstance(r, FileDef))
    with open(os.path.join(outdir, 'file_index.html'), 'w') as f:
        render('File Index', None, file_roots, file=f)
    with open(os.path.join(outdir, 'index.html'), 'w') as f:
        render('Index', None, roots - symbol_roots - file_roots, file=f)
