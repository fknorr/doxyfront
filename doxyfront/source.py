import xml.etree.ElementTree as xml
import multiprocessing
from typing import Dict, Optional, Set

from .model import *

_SUPERFLUOUS_WHITESPACE_RE = re.compile(r'(^\s+)|(?<=[\s(])\s+|\s+(?=[.,)])|(\s+$)')
_NON_URL_RE = re.compile(r'[^a-z0-9]+')


def _maybe_text(node: xml.Element) -> Optional[str]:
    if node.text:
        return node.text
    return None


def _elem_empty(elem: xml.Element) -> bool:
    return len(elem.attrib) == 0 and len(elem) == 0 and (elem.text is None or not elem.text.strip())


def _maybe_lineno(attrs: Dict[str, int], key: str) -> Optional[int]:
    try:
        string = attrs[key]
        line = int(string)
        return line if line > 0 else None
    except KeyError or ValueError:
        return None


class Parser:
    def __init__(self, file_name: str):
        self._file_name = file_name

    def _warning(self, msg: str):
        print('{}: {}'.format(self._file_name, msg), file=sys.stderr)

    def _require_attr(self, attrs: Dict[str, str], key: str) -> Optional[str]:
        try:
            return attrs[key]
        except KeyError:
            self._warning('Missing attribute ' + key)
            return None

    def _require_text(self, node: xml.Element) -> Optional[str]:
        if node.text:
            return node.text
        self._warning('Missing node text')
        return None

    def _yesno_to_bool(self, yesno: Optional[str]) -> Optional[bool]:
        if yesno == 'yes':
            return True
        if yesno == 'no':
            return False
        self._warning('Expected "yes" or "no", got ' + str(yesno))
        return None

    def _deserialize_fragment_children(self, instance: Fragment, node: xml.Element):
        if node.text:
            node_text = node.text.strip()
            if node_text:
                instance.children.append(TextFragment(node_text))

        for child in node:
            fragment = None
            if child.tag == 'ref':
                fragment = RefFragment(self._deserialize_ref(child))
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
                fragment = SectionFragment(self._require_attr(child.attrib, 'kind'))
            elif child.tag == 'ulink':
                fragment = LinkFragment(self._require_attr(child.attrib, 'url'))
            else:
                self._warning('Unhandled markup fragment <{}>'.format(child.tag))

            if fragment is not None:
                self._deserialize_fragment_children(fragment, child)
                instance.children.append(fragment)

            if child.tail:
                child_tail = child.tail.strip()
                if child_tail:
                    instance.children.append(TextFragment(child_tail))

        return instance

    def _deserialize_markup(self, node: xml.Element) -> Optional['Markup']:
        instance = Markup()
        self._deserialize_fragment_children(instance.root, node)
        if node.tail:
            node_tail = node.tail.strip()
            if node_tail:
                instance.root.children.append(TextFragment(node_tail))
        return instance

    def _deserialize_location(self, node: xml.Element) -> Optional['Location']:
        instance = Location()
        instance.file = self._require_attr(node.attrib, 'file')
        instance.line = _maybe_lineno(node.attrib, 'line')
        return instance

    def _deserialize_visibility(self, name: str) -> Optional['Visibility']:
        try:
            return Visibility.__dict__[name.upper()]
        except KeyError:
            self._warning(name + ' is not a known visibility')
            return None

    def _deserialize_attributes(self, node: xml.Element) -> Set[Attribute]:
        attrs = set()
        for k, v in node.attrib.items():
            try:
                a = Attribute.__dict__[k.upper()]
                if self._yesno_to_bool(v):
                    attrs.add(a)
            except KeyError:
                pass
        try:
            virt = node.attrib['virt']
            if virt == 'virtual':
                attrs.add(Attribute.VIRTUAL)
            if virt == 'pure-virtual':
                attrs.add(Attribute.VIRTUAL)
                attrs.add(Attribute.ABSTRACT)
        except KeyError:
            pass
        return attrs

    def _deserialize_def(self, cls, root: xml.Element):
        instance = cls()
        instance.id = self._require_attr(root.attrib, 'id')

        prot = root.attrib.get('prot')
        if prot is not None:
            instance.visibility = self._deserialize_visibility(prot)

        instance.attributes = self._deserialize_attributes(root)

        for elem in root:
            if _elem_empty(elem):
                continue

            if elem.tag in ['name', 'compoundname']:
                instance.qualified_name = self._require_text(elem)
            elif elem.tag == 'briefdescription':
                instance.brief_description = self._deserialize_markup(elem)
            elif elem.tag == 'detaileddescription':
                instance.detailed_description = self._deserialize_markup(elem)
            elif elem.tag == 'inbodydescription':
                instance.in_body_text = self._deserialize_markup(elem)
            elif elem.tag == 'location':
                instance.location = self._deserialize_location(elem)

        return instance

    def _deserialize_ref(self, root: xml.Element) -> Optional[Ref]:
        id = root.attrib.get('refid')
        name = _maybe_text(root)
        if id is None:
            if name is None:
                return None
            return UnresolvedRef(name)
        return SymbolicRef(id, name)

    def _deserialize_include(self, root: xml.Element):
        instance = Include()
        instance.file = self._deserialize_ref(root)
        instance.local = self._yesno_to_bool(self._require_attr(root.attrib, 'local'))
        return instance

    def _deserialize_macro_def(self, root: xml.Element):
        instance: MacroDef = self._deserialize_def(MacroDef, root)
        for elem in root:
            if elem.tag == 'param':
                for name in elem.findall('defname'):
                    instance.params.append(self._require_text(name))
            elif elem.tag == 'initializer':
                instance.substitution = self._deserialize_markup(elem)
        return instance

    def _deserialize_typedef(self, root: xml.Element):
        instance: TypedefDef = self._deserialize_def(TypedefDef, root)
        for elem in root:
            if elem.tag == 'type':
                instance.type = self._deserialize_markup(elem)
            elif elem.tag == 'definition':
                instance.definition = self._deserialize_markup(elem)
        return instance

    def _deserialize_param(self, root: xml.Element) -> 'Param':
        instance = Param()
        declname = None
        defname = None
        for elem in root:
            if elem.tag == 'type':
                instance.type = self._deserialize_markup(elem)
            elif elem.tag == 'declname':
                declname = _maybe_text(elem)
            elif elem.tag == 'declname':
                defname = _maybe_text(elem)
            elif elem.tag == 'defval':
                instance.default = self._deserialize_markup(elem)
        instance.name = declname if declname else defname
        return instance

    def _deserialize_function_variant(self, repr: str) -> Optional[FunctionDef.Variant]:
        try:
            return FunctionDef.Variant.__dict__[repr.upper()]
        except KeyError:
            return None

    def _deserialize_function(self, root: xml.Element):
        instance: FunctionDef = self._deserialize_def(FunctionDef, root)
        instance.variant = self._deserialize_function_variant(self._require_attr(root.attrib, 'kind'))
        for elem in root:
            if elem.tag == 'type':
                if instance.variant == FunctionDef.Variant.FUNCTION \
                        and len(elem) == 0 and elem.text is None:
                    if instance.qualified_name.startswith('~'):
                        instance.variant = FunctionDef.Variant.DESTRUCTOR
                    else:
                        instance.variant = FunctionDef.Variant.CONSTRUCTOR
                else:
                    instance.return_type = self._deserialize_markup(elem)
            elif elem.tag == 'templateparamlist':
                for param in elem:
                    instance.template_params.append(self._deserialize_param(param))
            elif elem.tag == 'param':
                instance.parameters.append(self._deserialize_param(elem))
        return instance

    def _deserialize_variable(self, root: xml.Element):
        instance: VariableDef = self._deserialize_def(VariableDef, root)
        for elem in root:
            if elem.tag == 'type':
                instance.type = self._deserialize_markup(elem)
            elif elem.tag == 'initializer':
                instance.initializer = self._deserialize_markup(elem)
        return instance

    def _deserialize_property(self, root: xml.Element):
        instance: PropertyDef = self._deserialize_def(PropertyDef, root)
        for elem in root:
            if elem.tag == 'type':
                instance.return_type = self._deserialize_markup(elem)
        return instance

    def _deserialize_enum_variant(self, root: xml.Element):
        instance: EnumVariantDef = self._deserialize_def(EnumVariantDef, root)
        for elem in root:
            if elem.tag == 'initializer':
                instance.initializer = self._deserialize_markup(elem)
        return instance

    def _deserialize_enum(self, root: xml.Element) -> (EnumDef, [EnumVariantDef]):
        instance: EnumDef = self._deserialize_def(EnumDef, root)
        variant_defs = []
        strong = root.attrib.get('strong')
        if strong:
            instance.strong = self._yesno_to_bool(strong)
        for elem in root:
            if elem.tag == 'type':
                if not _elem_empty(elem):
                    instance.underlying_type = self._deserialize_markup(elem)
            elif elem.tag == 'enumvalue':
                variant = self._deserialize_enum_variant(elem)
                variant_defs.append(variant)
                instance.members.append(ResolvedRef(variant))
        return instance, variant_defs

    def _deserialize_friend(self, root: xml.Element):
        instance: FriendDef = self._deserialize_def(FriendDef, root)
        for elem in root:
            if elem.tag == 'definition':
                instance.definition = self._deserialize_markup(elem)
            elif elem.tag == 'templateparamlist':
                for param in elem:
                    instance.template_params.append(self._deserialize_param(param))
        instance.visibility = None
        return instance

    def _deserialize_compound(self, cls, root: xml.Element) -> (CompoundDef, [Def]):
        instance: cls = self._deserialize_def(cls, root)
        defs: [Def] = [instance]

        instance.language = root.attrib.get('language')

        for elem in root:
            if elem.tag.startswith('inner'):
                instance.members.append(self._deserialize_ref(elem))
            elif elem.tag == 'sectiondef':
                for member in elem.findall('memberdef'):
                    child = None
                    nested_defs = []

                    if member.attrib['kind'] == 'define':
                        child = self._deserialize_macro_def(member)
                    elif member.attrib['kind'] == 'typedef':
                        child = self._deserialize_typedef(member)
                    elif member.attrib['kind'] in ['function', 'signal', 'slot']:
                        child = self._deserialize_function(member)
                    elif member.attrib['kind'] == 'variable':
                        child = self._deserialize_variable(member)
                    elif member.attrib['kind'] == 'property':
                        child = self._deserialize_property(member)
                    elif member.attrib['kind'] == 'enum':
                        child, nested_defs = self._deserialize_enum(member)
                    elif member.attrib['kind'] == 'friend':
                        child = self._deserialize_friend(member)
                    else:
                        self._warning('Unknown member kind ' + member.attrib['kind'])

                    if child is not None:
                        defs.append(child)
                        instance.members.append(SymbolicRef(child.id, child.qualified_name))
                    defs += nested_defs

        return instance, defs

    def _deserialize_directory(self, root: xml.Element) -> (DirectoryDef, [Def]):
        return self._deserialize_compound(DirectoryDef, root)

    def _deserialize_file(self, root: xml.Element) -> (FileDef, [Def]):
        file: FileDef
        file, defs = self._deserialize_compound(FileDef, root)

        for elem in root:
            if elem.tag == 'includes':
                file.includes.append(self._deserialize_include(elem))

        return file, defs

    def _deserialize_namespace(self, root: xml.Element) -> (NamespaceDef, [Def]):
        return self._deserialize_compound(NamespaceDef, root)

    def _deserialize_group(self, root: xml.Element) -> (GroupDef, [Def]):
        return self._deserialize_compound(GroupDef, root)

    def _deserialize_page(self, root: xml.Element) -> (PageDef, [Def]):
        return self._deserialize_compound(PageDef, root)

    def _deserialize_inheritance(self, root: xml.Element) -> Inheritance:
        instance = Inheritance()
        instance.ref = self._deserialize_ref(root)
        instance.visibility = self._deserialize_visibility(root.attrib['prot'])
        instance.virtual = root.attrib.get('virt') == 'virtual'
        return instance

    def _deserialize_class_variant(self, repr: str) -> Optional[ClassDef.Variant]:
        try:
            return ClassDef.Variant.__dict__[repr.upper()]
        except KeyError:
            return None

    def _deserialize_class(self, root: xml.Element) -> (ClassDef, [Def]):
        klass: ClassDef
        klass, defs = self._deserialize_compound(ClassDef, root)
        klass.variant = self._deserialize_class_variant(self._require_attr(root.attrib, 'kind'))

        for elem in root:
            if elem.tag == 'basecompoundref':
                klass.bases.append(self._deserialize_inheritance(elem))
            if elem.tag == 'templateparamlist':
                for param in elem:
                    klass.template_params.append(self._deserialize_param(param))

        return klass, defs

    def parse(self) -> [Def]:
        with open(self._file_name) as f:
            try:
                tree = xml.parse(f)
            except xml.ParseError as e:
                self._warning(str(e))
                return []

        node = tree.getroot().find('compounddef')
        if node is None:
            self._warning('No compounddef in file')
            return []

        kind = self._require_attr(node.attrib, 'kind')
        if kind == 'file':
            return self._deserialize_file(node)[1]
        elif kind == 'dir':
            return self._deserialize_directory(node)[1]
        elif kind in ['class', 'struct', 'union', 'protocol', 'interface', 'category']:
            return self._deserialize_class(node)[1]
        elif kind == 'namespace':
            return self._deserialize_namespace(node)[1]
        elif kind == 'group':
            return self._deserialize_group(node)[1]
        elif kind == 'page':
            return self._deserialize_page(node)[1]
        else:
            self._warning('Unknown compounddef kind ' + kind)
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
    elif isinstance(r, NamespaceDef) or isinstance(r, ClassDef) or isinstance(r, EnumDef):
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


def _renew_ids(defs: [Def]):
    used = set()
    for d in sorted(defs, key=lambda d: d.id):
        slug = d.slug()[:50]
        id = slug
        i = 0
        while id in used:
            i += 1
            id = '{}-{}'.format(slug, i)
        d.id = id
        used.add(id)


def _parse_one(file_name: str) -> [Def]:
    return Parser(file_name).parse()


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

    return defs
