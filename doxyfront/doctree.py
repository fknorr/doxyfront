import multiprocessing
import os
from collections import defaultdict
import shutil
import pkg_resources

import jinja2

from .__init__ import __version__ as package_version
from .model import *


class SymbolCategory(Enum):
    PAGE = 0
    DIRECTORY = 1
    FILE = 2
    NAMESPACE = 3
    MACRO = 4
    TYPE = 5
    VARIANT = 6
    CONSTRUCTOR = 7
    DESTRUCTOR = 8
    FUNCTION = 9
    SIGNAL = 10
    SLOT = 11
    PROPERTY = 12
    VARIABLE = 13
    FRIEND = 14


KIND_CATEGORIES = {
    'index': SymbolCategory.PAGE,
    'page': SymbolCategory.PAGE,
    'group': SymbolCategory.PAGE,
    'directory': SymbolCategory.DIRECTORY,
    'file': SymbolCategory.FUNCTION,
    'namespace': SymbolCategory.NAMESPACE,
    'package': SymbolCategory.NAMESPACE,
    'macro': SymbolCategory.MACRO,
    'typedef': SymbolCategory.TYPE,
    'struct': SymbolCategory.TYPE,
    'class': SymbolCategory.TYPE,
    'union': SymbolCategory.TYPE,
    'protocol': SymbolCategory.TYPE,
    'category': SymbolCategory.TYPE,
    'interface': SymbolCategory.TYPE,
    'enum': SymbolCategory.TYPE,
    'enum-class': SymbolCategory.TYPE,
    'enum-variant': SymbolCategory.VARIANT,
    'constructor': SymbolCategory.CONSTRUCTOR,
    'destructor': SymbolCategory.DESTRUCTOR,
    'property': SymbolCategory.PROPERTY,
    'function': SymbolCategory.FUNCTION,
    'signal': SymbolCategory.SIGNAL,
    'slot': SymbolCategory.SLOT,
    'variable': SymbolCategory.VARIABLE,
    'friend': SymbolCategory.FRIEND,
}


def category(d: Def) -> (int, str):
    return KIND_CATEGORIES[d.kind()]


def describe(d: Def, context: set) -> dict:
    template_sig, signature = d.signature_html(context)
    vis = None
    if d.scope_parent is not None and isinstance(d.scope_parent, ClassDef):
        vis = d.visibility

    return {
        'id': d.id,
        'name_html': d.qualified_name_html(context),
        'full_name_plaintext': d.qualified_name_plaintext(set()),
        'full_signature_plaintext': d.signature_plaintext(set()),
        'vis_order': '+~#-'.index(vis.value) if vis else 0,
        'vis_plaintext': vis.name.lower() if vis else None,
        'vis_symbol': vis.value if vis else None,
        'template_sig': template_sig,
        'signature': signature,
        'brief': d.brief_description.render_plaintext(context) if d.brief_description else '',
        'href': d.href,
    }


def member_order(member: Def):
    return member['vis_order'], member['full_name_plaintext'].lower()


def sorted_categories(members_by_cat: dict) -> (list, int):
    all_cats = sorted((c.value, (c.name.title(), list(sorted(m, key=member_order))))
                      for c, m in members_by_cat.items())
    return [cat for _, cat in all_cats]


def sibling_cats(parent: Def, context: set, cache: dict) -> (list, int):
    try:
        return cache[parent.id]
    except KeyError:
        by_cat = defaultdict(list)
        assert isinstance(parent, CompoundDef)
        for ref in parent.members:
            if isinstance(ref, ResolvedRef):
                m = ref.definition
                by_cat[category(m)].append(describe(m, context))
        cats = [(n, m[:30], max(0, len(m) - 30)) for n, m in sorted_categories(by_cat)]
        cache[parent.id] = cats
        return cats


scope_sibling_cache = dict()
path_sibling_cache = dict()


def prepare_render(definition: Def) -> dict:
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

    members = []
    if isinstance(definition, CompoundDef):
        members = [m.definition for m in definition.members if isinstance(m, ResolvedRef)]

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

    window_title = definition.signature_plaintext(context, fully_qualified=True)
    template_sig, signature = definition.signature_html(context, fully_qualified=True)

    return {
        'generator': '{} v{}'.format('doxyfront', package_version),
        'id': definition.id if definition else None,
        'scope_parent_href': definition.scope_parent.href if definition.scope_parent else None,
        'file_parent_href': definition.file_parent.href if definition.file_parent else None,
        'window_title': window_title,
        'template_sig': template_sig,
        'signature': signature,
        'details': details,
        'member_cats': sorted_categories(members_by_cat),
        'scope_sibling_cats': scope_sibling_cats,
        'path_sibling_cats': path_sibling_cats,
        'include': include,
    }


_LEADING_WHITESPACE_RE = re.compile(r'^\s+', re.MULTILINE)


def render(path: str, script: dict):
    with open(path, 'w') as f:
        global template
        f.write(_LEADING_WHITESPACE_RE.sub('', template.render(**script)))


def render_one(params):
    render(*params)


def _extract_assets(manager, provider, src_resource, dest_folder):
    os.makedirs(dest_folder, exist_ok=True)
    for entry in provider.resource_listdir(src_resource):
        entry_resource = '/'.join((src_resource, entry))
        entry_folder = os.path.join(dest_folder, entry)
        if provider.resource_isdir(entry_resource):
            _extract_assets(manager, provider, entry_resource, entry_folder)
        else:
            with provider.get_resource_stream(manager, entry_resource) as source:
                with open(entry_folder, 'wb') as dest:
                    dest.write(source.read())


def _generate_href(d: Def):
    if ((isinstance(d, VariableDef) or isinstance(d, FunctionDef) or isinstance(d, TypedefDef))
        and d.scope_parent is not None and isinstance(d.scope_parent, ClassDef)) \
            or isinstance(d, EnumVariantDef):
        d.page = None
        d.href = '{}.html#{}'.format(d.scope_parent.id, d.id)
    else:
        d.page = '{}.html'.format(d.id)
        d.href = d.page


def doctree(defs: [Def], outdir: str):
    env = jinja2.Environment(
        loader=jinja2.PackageLoader('doxyfront'),
        autoescape=jinja2.select_autoescape(['html']),
        trim_blocks=True,
    )
    global template
    template = env.get_template('doctree.html')

    render_jobs = []
    for d in defs:
        _generate_href(d)
        if d.page is not None:
            script = prepare_render(d)
            render_jobs.append((os.path.join(outdir, d.page), script))

    os.makedirs(outdir, exist_ok=True)
    with multiprocessing.Pool() as pool:
        pool.map(render_one, render_jobs)

    manager = pkg_resources.ResourceManager()
    provider = pkg_resources.get_provider('doxyfront')
    _extract_assets(manager, provider, 'assets', outdir)
