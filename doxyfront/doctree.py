from collections import defaultdict
from enum import Enum
import os
import jinja2
import multiprocessing

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


def describe(d: Def, context: set) -> dict:
    return {
        'id': d.id,
        'name_html': d.qualified_name_html(context),
        'full_name_plaintext': d.qualified_name_plaintext(set()),
        'full_signature_plaintext': d.signature_plaintext(set()),
        'vis': d.visibility.value if d.visibility else '',
        'signature': d.signature_html(context),
        'brief': d.brief_description.render_plaintext(context) if d.brief_description else '',
        'href': d.href,
    }


def sorted_categories(members_by_cat: dict) -> list:
    return list(sorted((c.name.lower(),
                        list(sorted(m, key=lambda m: m['full_name_plaintext'].lower())))
                       for (_, c), m in members_by_cat.items()))


def sibling_cats(parent: Def, context: set, cache: dict) -> list:
    try:
        return cache[parent.id]
    except KeyError:
        by_cat = defaultdict(list)
        assert isinstance(parent, CompoundDef)
        for ref in parent.members:
            if isinstance(ref, ResolvedRef):
                m = ref.definition
                by_cat[category(m)].append(describe(m, context))
        cats = sorted_categories(by_cat)
        cache[parent.id] = cats
        return cats


scope_sibling_cache = dict()
path_sibling_cache = dict()


def prepare_render(title: str or None, definition: Def or None, members: [Def]) -> dict:
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

    members_by_cat = defaultdict(list)
    for m in members:
        members_by_cat[category(m)].append(describe(m, context))

    scope_sibling_cats = None
    if definition is not None and definition.scope_parent:
        global scope_sibling_cache
        scope_sibling_cats = sibling_cats(definition.scope_parent, context, scope_sibling_cache)

    path_sibling_cats = None
    if definition is not None and definition.file_parent:
        global path_sibling_cache
        path_sibling_cats = sibling_cats(definition.file_parent, context, path_sibling_cache)

    if title is not None:
        window_title = title
        page_title = title
    else:
        window_title = definition.signature_plaintext(context, fully_qualified=True)
        page_title = '<span class="def">{}</span>'.format(
            definition.signature_html(context, fully_qualified=True))

    return {
        'id': definition.id if definition else None,
        'window_title': window_title,
        'page_title': page_title,
        'details': details,
        'member_cats': sorted_categories(members_by_cat),
        'scope_sibling_cats': scope_sibling_cats,
        'path_sibling_cats': path_sibling_cats,
        'include': include,
    }


def render(path: str, script: dict):
    with open(path, 'w') as f:
        global template
        f.write(template.render(**script))


def render_one(params):
    render(*params)


def doctree(defs: [Def], outdir: str):
    env = jinja2.Environment(
        loader=jinja2.PackageLoader('doxyfront', ''),
        autoescape=jinja2.select_autoescape(['html']),
        trim_blocks=True,
    )
    global template
    template = env.get_template('doctree.html')

    render_jobs = []
    non_global = set()
    for d in defs:
        members = []
        if isinstance(d, CompoundDef):
            for m in d.members:
                if isinstance(m, ResolvedRef):
                    members.append(m.definition)
                    if not isinstance(d, FileDef):
                        non_global.add(m.definition)
        script = prepare_render(None, d, members)
        render_jobs.append((os.path.join(outdir, d.id + '.html'), script))

    with multiprocessing.Pool() as pool:
        pool.map(render_one, render_jobs)

    roots = set(defs) - non_global
    symbol_roots = set(r for r in roots if isinstance(r, SymbolDef))
    render(os.path.join(outdir, 'symbol_index.html'),
           prepare_render('Symbol Index', None, symbol_roots))
    file_roots = set(r for r in roots if isinstance(r, DirectoryDef)
                  or isinstance(r, FileDef))
    render(os.path.join(outdir, 'file_index.html'),
           prepare_render('File Index', None, file_roots))
    render(os.path.join(outdir, 'index.html'),
           prepare_render('Index', None, roots - symbol_roots - file_roots))
