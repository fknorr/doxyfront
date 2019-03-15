import xml.etree.ElementTree as xml
import multiprocessing

from .model import *


def _warning(msg: str):
    global file_name
    print('{}: {}'.format(file_name, msg), file=sys.stderr)


def _require_attr(attrs: dict, key: str) -> str or None:
    try:
        return attrs[key]
    except KeyError:
        _warning('Missing attribute ' + key)
        return None


def _maybe_attr(attrs: dict, key: str) -> str or None:
    try:
        return attrs[key]
    except KeyError:
        return None


def _require_text(node: xml.Element) -> str or None:
    if node.text:
        return node.text
    _warning('Missing node text')
    return None


def _maybe_text(node: xml.Element) -> str or None:
    if node.text:
        return node.text
    return None


def _yesno_to_bool(yesno: str or None) -> bool or None:
    if yesno == 'yes':
        return True
    if yesno == 'no':
        return False
    _warning('Expected "yes" or "no", got ' + str(yesno))
    return None


def _elem_empty(elem: xml.Element) -> bool:
    return len(elem.attrib) == 0 and len(elem) == 0 and (elem.text is None or not elem.text.strip())


def deserialize_fragment_children(instance: Fragment, node: xml.Element):
    if node.text:
        node_text = node.text.strip()
        if node_text:
            instance.children.append(TextFragment(node_text))

    for child in node:
        fragment = None
        if child.tag == 'ref':
            fragment = RefFragment(deserialize_ref(child))
        elif child.tag == 'para':
            fragment = FormatFragment(FormatFragment.Variant.PARAGRAPH)
        elif child.tag == 'computeroutput':
            fragment = FormatFragment(FormatFragment.Variant.CODE)
        elif child.tag == 'emphasis':
            fragment = FormatFragment(FormatFragment.Variant.EMPHASIS)
        elif child.tag == 'bold':
            fragment = FormatFragment(FormatFragment.Variant.STRONG)
        elif child.tag == 'itemizedlist':
            fragment = FormatFragment(FormatFragment.Variant.ITEMIZE)
        elif child.tag == 'listitem':
            fragment = FormatFragment(FormatFragment.Variant.ITEM)
        elif child.tag == 'simplesect':
            fragment = SectionFragment(_require_attr(child.attrib, 'kind'))
        elif child.tag == 'ulink':
            fragment = LinkFragment(_require_attr(child.attrib, 'url'))
        else:
            _warning('Unhandled markup fragment <{}>'.format(child.tag))

        if fragment is not None:
            deserialize_fragment_children(fragment, child)
            instance.children.append(fragment)

        if child.tail:
            child_tail = child.tail.strip()
            if child_tail:
                instance.children.append(TextFragment(child_tail))

    return instance


_SUPERFLUOUS_WHITESPACE_RE = re.compile(r'(^\s+)|(?<=[\s(])\s+|\s+(?=[.,)])|(\s+$)')
_NON_URL_RE = re.compile(r'[^a-z0-9]+')


def deserialize_markup(node: xml.Element) -> 'Markup' or None:
    instance = Markup()
    deserialize_fragment_children(instance.root, node)
    if node.tail:
        node_tail = node.tail.strip()
        if node_tail:
            instance.root.children.append(TextFragment(node_tail))
    return instance


def _maybe_lineno(attrs: dict, key: str) -> int or None:
    try:
        string = attrs[key]
        line = int(string)
        return line if line > 0 else None
    except KeyError or ValueError:
        return None


def deserialize_location(node: xml.Element) -> 'Location' or None:
    instance = Location()
    instance.file = _require_attr(node.attrib, 'file')
    instance.line = _maybe_lineno(node.attrib, 'line')
    return instance


def deserialize_visibility(name: str) -> 'Visibility' or None:
    try:
        return Visibility.__dict__[name.upper()]
    except KeyError:
        _warning(name + ' is not a known visibility')
        return None


def deserialize_attributes(node: xml.Element) -> set:
    attrs = []
    for k, v in node.attrib.items():
        try:
            a = Attribute.__dict__[k.upper()]
            if _yesno_to_bool(v):
                attrs.append(a)
        except KeyError:
            pass
    try:
        virt = node.attrib['virt']
        if virt == 'virtual':
            attrs.append(Attribute.VIRTUAL)
        if virt == 'pure-virtual':
            attrs.append(Attribute.VIRTUAL)
            attrs.append(Attribute.ABSTRACT)
    except KeyError:
        pass
    return attrs


def deserialize_def(cls, root: xml.Element):
    instance = cls()
    instance.id = _require_attr(root.attrib, 'id')

    prot = _maybe_attr(root.attrib, 'prot')
    if prot is not None:
        instance.visibility = deserialize_visibility(prot)

    instance.attributes = deserialize_attributes(root)

    for elem in root:
        if _elem_empty(elem):
            continue

        if elem.tag in ['name', 'compoundname']:
            instance.qualified_name = _require_text(elem)
        elif elem.tag == 'briefdescription':
            instance.brief_description = deserialize_markup(elem)
        elif elem.tag == 'detaileddescription':
            instance.detailed_description = deserialize_markup(elem)
        elif elem.tag == 'inbodydescription':
            instance.in_body_text = deserialize_markup(elem)
        elif elem.tag == 'location':
            instance.location = deserialize_location(elem)

    return instance


def deserialize_ref(root: xml.Element) -> Ref or None:
    id = _maybe_attr(root.attrib, 'refid')
    name = _maybe_text(root)
    if id is None:
        if name is None:
            return None
        return UnresolvedRef(name)
    return SymbolicRef(id, name)


def deserialize_include(root: xml.Element):
    instance = Include()
    instance.file = deserialize_ref(root)
    instance.local = _yesno_to_bool(_require_attr(root.attrib, 'local'))
    return instance


def deserialize_macro_def(root: xml.Element):
    instance: MacroDef = deserialize_def(MacroDef, root)
    for elem in root:
        if elem.tag == 'param':
            for name in elem.findall('defname'):
                instance.params.append(_require_text(name))
        elif elem.tag == 'initializer':
            instance.substitution = deserialize_markup(elem)
    return instance


def deserialize_typedef(root: xml.Element):
    instance: TypedefDef = deserialize_def(TypedefDef, root)
    for elem in root:
        if elem.tag == 'type':
            instance.type = deserialize_markup(elem)
        elif elem.tag == 'definition':
            instance.definition = deserialize_markup(elem)
    return instance


def deserialize_param(root: xml.Element) -> 'Param':
    instance = Param()
    declname = None
    defname = None
    for elem in root:
        if elem.tag == 'type':
            instance.type = deserialize_markup(elem)
        elif elem.tag == 'declname':
            declname = _maybe_text(elem)
        elif elem.tag == 'declname':
            defname = _maybe_text(elem)
        elif elem.tag == 'defval':
            instance.default = deserialize_markup(elem)
    instance.name = declname if declname else defname
    return instance


def deserialize_function_variant(repr: str) -> FunctionDef.Variant or None:
    try:
        return FunctionDef.Variant.__dict__[repr.upper()]
    except KeyError:
        return None


def deserialize_function(root: xml.Element):
    instance: FunctionDef = deserialize_def(FunctionDef, root)
    instance.variant = deserialize_function_variant(_require_attr(root.attrib, 'kind'))
    for elem in root:
        if elem.tag == 'type':
            if instance.variant == FunctionDef.Variant.FUNCTION \
                    and len(elem) == 0 and elem.text is None:
                if instance.qualified_name.startswith('~'):
                    instance.variant = FunctionDef.Variant.DESTRUCTOR
                else:
                    instance.variant = FunctionDef.Variant.CONSTRUCTOR
            else:
                instance.return_type = deserialize_markup(elem)
        elif elem.tag == 'templateparamlist':
            for param in elem:
                instance.template_params.append(deserialize_param(param))
        elif elem.tag == 'param':
            instance.parameters.append(deserialize_param(elem))
    return instance


def deserialize_variable(root: xml.Element):
    instance: VariableDef = deserialize_def(VariableDef, root)
    for elem in root:
        if elem.tag == 'type':
            instance.return_type = deserialize_markup(elem)
        if elem.tag == 'initializer':
            instance.initializer = deserialize_markup(elem)
    return instance


def deserialize_property(root: xml.Element):
    instance: PropertyDef = deserialize_def(PropertyDef, root)
    for elem in root:
        if elem.tag == 'type':
            instance.return_type = deserialize_markup(elem)
    return instance


def deserialize_enum_value(root: xml.Element):
    instance: EnumValueDef = deserialize_def(EnumValueDef, root)
    for elem in root:
        if elem.tag == 'initializer':
            instance.initializer = deserialize_markup(elem)
    return instance


def deserialize_enum(root: xml.Element):
    instance: EnumDef = deserialize_def(EnumDef, root)
    strong = _maybe_attr(root.attrib, 'strong')
    if strong:
        instance.strong = _yesno_to_bool(strong)
    for elem in root:
        if elem.tag == 'type':
            instance.underlying_type = deserialize_markup(elem)
        if elem.tag == 'enumvalue':
            instance.values.append(deserialize_enum_value(elem))
    return instance


def deserialize_friend(root: xml.Element):
    instance: FriendDef = deserialize_def(FriendDef, root)
    for elem in root:
        if elem.tag == 'definition':
            instance.definition = deserialize_markup(elem)
    return instance


def deserialize_compound(cls, root: xml.Element) -> (CompoundDef, [Def]):
    instance: cls = deserialize_def(cls, root)
    defs: [Def] = [instance]

    instance.language = _maybe_attr(root.attrib, 'language')

    for elem in root:
        if elem.tag.startswith('inner'):
            instance.members.append(deserialize_ref(elem))
        elif elem.tag == 'sectiondef':
            for member in elem.findall('memberdef'):
                child = None

                if member.attrib['kind'] == 'define':
                    child = deserialize_macro_def(member)
                elif member.attrib['kind'] == 'typedef':
                    child = deserialize_typedef(member)
                elif member.attrib['kind'] in ['function', 'signal', 'slot']:
                    child = deserialize_function(member)
                elif member.attrib['kind'] == 'variable':
                    child = deserialize_variable(member)
                elif member.attrib['kind'] == 'property':
                    child = deserialize_property(member)
                elif member.attrib['kind'] == 'enum':
                    child = deserialize_enum(member)
                elif member.attrib['kind'] == 'friend':
                    child = deserialize_friend(member)
                else:
                    _warning('Unknown member kind ' + member.attrib['kind'])

                if child is not None:
                    defs.append(child)
                    instance.members.append(SymbolicRef(child.id, child.qualified_name))

    return instance, defs


def deserialize_directory(root: xml.Element) -> (DirectoryDef, [Def]):
    return deserialize_compound(DirectoryDef, root)


def deserialize_file(root: xml.Element) -> (FileDef, [Def]):
    file: FileDef
    file, defs = deserialize_compound(FileDef, root)

    for elem in root:
        if elem.tag == 'includes':
            file.includes.append(deserialize_include(elem))

    return file, defs


def deserialize_namespace(root: xml.Element) -> (NamespaceDef, [Def]):
    return deserialize_compound(NamespaceDef, root)


def deserialize_group(root: xml.Element) -> (GroupDef, [Def]):
    return deserialize_compound(GroupDef, root)


def deserialize_page(root: xml.Element) -> (PageDef, [Def]):
    return deserialize_compound(PageDef, root)


def deserialize_inheritance(root: xml.Element) -> Inheritance:
    instance = Inheritance()
    instance.ref = deserialize_ref(root)
    instance.visibility = deserialize_visibility(root.attrib['prot'])
    instance.virtual = _maybe_attr(root.attrib, 'virt') == 'virtual'
    return instance


def deserialize_class_variant(repr: str) -> ClassDef.Variant or None:
    try:
        return ClassDef.Variant.__dict__[repr.upper()]
    except KeyError:
        return None


def deserialize_class(root: xml.Element) -> (ClassDef, [Def]):
    klass: ClassDef
    klass, defs = deserialize_compound(ClassDef, root)
    klass.variant = deserialize_class_variant(_require_attr(root.attrib, 'kind'))

    for elem in root:
        if elem.tag == 'basecompoundref':
            klass.bases.append(deserialize_inheritance(elem))
        if elem.tag == 'templateparamlist':
            for param in elem:
                klass.template_params.append(deserialize_param(param))

    return klass, defs


def _parse(file) -> [Def]:
    try:
        tree = xml.parse(file)
    except xml.ParseError as e:
        _warning(e)
        return []

    node = tree.getroot().find('compounddef')
    if node is None:
        _warning('No compounddef in file')
        return []

    kind = _require_attr(node.attrib, 'kind')
    if kind == 'file':
        return deserialize_file(node)[1]
    elif kind == 'dir':
        return deserialize_directory(node)[1]
    elif kind in ['class', 'struct', 'union', 'protocol', 'interface', 'category']:
        return deserialize_class(node)[1]
    elif kind == 'namespace':
        return deserialize_namespace(node)[1]
    elif kind == 'group':
        return deserialize_group(node)[1]
    elif kind == 'page':
        return deserialize_page(node)[1]
    else:
        _warning('Unknown compounddef kind ' + kind)
        return []


def _resolve_refs(def_list: [Def]):
    defs = dict((d.id, d) for d in def_list)
    for d in def_list:
        d.resolve_refs(defs)


def _assign_parents(r: Def):
    if isinstance(r, FileDef) or isinstance(r, DirectoryDef):
        for m in r.members:
            if isinstance(m, ResolvedRef):
                if isinstance(m.definition, SingleDef):
                    m.definition.file_parent = r
    elif isinstance(r, NamespaceDef) or isinstance(r, ClassDef):
        for m in r.members:
            if isinstance(m, ResolvedRef):
                m.definition.scope_parent = r


def _assign_roots(d: Def, scope_root: IndexDef, file_root: IndexDef):
    if isinstance(d, SymbolDef) and d.scope_parent is None:
        d.scope_parent = scope_root
        scope_root.members.append(ResolvedRef(d))
    if isinstance(d, PathDef) and d.file_parent is None:
        d.file_parent = file_root
        file_root.members.append(ResolvedRef(d))


def _unqualify_names(d: Def, prefix: str = ''):
    if prefix and d.qualified_name.startswith(prefix):
        d.name = d.qualified_name[len(prefix):]
    if (not prefix or d.qualified_name.startswith(prefix)) and isinstance(d, CompoundDef):
        prefix = d.qualified_name + '::'
        for m in d.members:
            if isinstance(m, ResolvedRef):
                _unqualify_names(m.definition, prefix)


def _derive_brief_description(d: Def):
    if d.brief_description is None and d.detailed_description is not None:
        fragments = d.detailed_description.root.children
        if fragments and isinstance(fragments[0], FormatFragment) \
                and fragments[0].variant == FormatFragment.Variant.PARAGRAPH:
            d.brief_description = Markup()
            d.brief_description.root.children.append(fragments[0])


def _generate_href(d: Def):
    if (isinstance(d, VariableDef) or isinstance(d, FunctionDef) or isinstance(d, TypedefDef)) \
            and d.scope_parent is not None and isinstance(d.scope_parent, ClassDef):
        d.page = None
        d.href = '{}.html#{}'.format(d.scope_parent.id, d.id)
    else:
        d.page = '{}.html'.format(d.id)
        d.href = d.page


def _renew_ids(defs: [Def]):
    used = set()
    for d in sorted(defs, key=lambda d: d.id):
        slug = d.slug()[:40]
        id = slug
        i = 0
        while id in used:
            i += 1
            id = '{}-{}'.format(slug, i)
        d.id = id
        used.add(id)


def _parse_one(name: str) -> [Def]:
    global file_name
    file_name = name
    with open(name, 'rb') as f:
        return _parse(f)


def load(files: [str]) -> [Def]:
    with multiprocessing.Pool() as pool:
        def_slices = pool.map(_parse_one, files)

    defs = [d for slice in def_slices for d in slice]
    _resolve_refs(defs)

    for d in defs:
        _assign_parents(d)

    for d in defs:
        _unqualify_names(d)
    for d in defs:
        if d.name is None:
            d.name = d.qualified_name

    _renew_ids(defs)

    scope_root = IndexDef('index', 'Global Namespace')
    file_root = IndexDef('file_index', 'Root Folder')
    for d in defs:
        _assign_roots(d, scope_root, file_root)
    defs += [scope_root, file_root]

    for d in defs:
        _derive_brief_description(d)
        _generate_href(d)

    return defs


if __name__ == '__main__':
    defs = load(['class_framework_1_1_cache.xml'])
    print()
