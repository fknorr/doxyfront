import xml.etree.ElementTree as xml
from enum import Enum, unique
import sys
import re


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


class Item:
    def resolve_refs(self, defs: dict):
        pass


def _maybe_resolve_refs(item: Item or None, defs: dict):
    if item is not None:
        item.resolve_refs(defs)


def _html_escape(s: str) -> str:
    return s.replace('&', '&amp;') \
        .replace('<', '&lt;') \
        .replace('>', '&gt;') \
        .replace('"', '&quot;') \
        .replace("'", '&apos;')


def _elem_empty(elem: xml.Element) -> bool:
    return len(elem.attrib) == 0 and len(elem) == 0 and (elem.text is None or not elem.text.strip())


class Fragment(Item):
    def __init__(self):
        self.children: [Fragment] = []

    def resolve_refs(self, defs: dict):
        for c in self.children:
            c.resolve_refs(defs)

    def render_plaintext(self) -> str:
        return ' '.join(c.render_plaintext() for c in self.children)

    def render_html(self) -> str:
        return ' '.join(c.render_html() for c in self.children)


class TextFragment(Fragment):
    def __init__(self, text: str or None = None):
        super().__init__()
        self.text = text

    def render_plaintext(self) -> str:
        return self.text

    def render_html(self) -> str:
        return _html_escape(self.text)


class FormatFragment(Fragment):
    @unique
    class Variant(Enum):
        PARAGRAPH = 'p'
        CODE = 'code'
        STRONG = 'strong'
        EMPHASIS = 'em'
        ITEMIZE = 'ul'
        ENUMERATE = 'ol'
        ITEM = 'li'

    def __init__(self, variant: Variant):
        super().__init__()
        self.variant = variant

    def render_html(self) -> str:
        return '<{0}>{1}</{0}>'.format(self.variant.value.lower(), super().render_html())


class RefFragment(Fragment):
    def __init__(self, ref: 'Ref' or None = None):
        super().__init__()
        self.ref = ref

    def render_html(self) -> str:
        content = super().render_html()
        if isinstance(self.ref, ResolvedRef):
            return self.ref.definition.qualified_name_html()
        return content

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        self.ref = self.ref.resolve(defs)


class LinkFragment(Fragment):
    def __init__(self, url: str or None = None):
        super().__init__()
        self.url = url

    def render_html(self) -> str:
        return '<a class="external" href="{}">{}</a>'.format(self.url, super().render_html())


class SectionFragment(Fragment):
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind

    def render_html(self) -> str:
        return '<section><h3>{}</h3>{}</section>'.format(self.kind, super().render_html())


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


class Markup(Item):
    def __init__(self):
        self.root = Fragment()

    @classmethod
    def deserialize(cls, node: xml.Element) -> 'Markup' or None:
        instance = cls()
        deserialize_fragment_children(instance.root, node)
        if node.tail:
            node_tail = node.tail.strip()
            if node_tail:
                instance.root.children.append(TextFragment(node_tail))
        return instance

    def resolve_refs(self, defs: dict):
        self.root.resolve_refs(defs)

    def render_plaintext(self):
        return _SUPERFLUOUS_WHITESPACE_RE.sub('', self.root.render_plaintext())

    def render_html(self):
        return self.root.render_html()


class Location:
    def __init__(self):
        self.file: str or None = None
        self.line: int or None = None

    @staticmethod
    def maybe_lineno(attrs: dict, key: str) -> int or None:
        try:
            string = attrs[key]
            line = int(string)
            return line if line > 0 else None
        except KeyError or ValueError:
            return None

    @classmethod
    def deserialize(cls, node: xml.Element) -> 'Location' or None:
        instance = cls()
        instance.file = _require_attr(node.attrib, 'file')
        instance.line = Location.maybe_lineno(node.attrib, 'line')
        return instance


@unique
class Visibility(Enum):
    PUBLIC = 0
    PACKAGE = 1
    PROTECTED = 2
    PRIVATE = 3

    @classmethod
    def deserialize(cls, name: str) -> 'Visibility' or None:
        try:
            return cls.__dict__[name.upper()]
        except KeyError:
            _warning(name + ' is not a known visibility')
            return None

    def __repr__(self):
        return self.__class__.__name__ + '.' + self.name


@unique
class Attribute(Enum):
    FINAL = 0
    OVERRIDE = 1
    VIRTUAL = 2
    ABSTRACT = 3
    CONSTEXPR = 4
    EXPLICIT = 5
    NOEXCEPT = 6
    STATIC = 7
    MUTABLE = 8
    INLINE = 9

    def __repr__(self):
        return self.__class__.__name__ + '.' + self.name


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
        if node.attrib['virt'] == 'virtual':
            attrs.append(Attribute.VIRTUAL)
    except KeyError:
        pass
    return attrs


class Def(Item):
    def __init__(self):
        self.id: str or None = None
        self.name: str or None = None
        self.qualified_name: str or None = None
        self.brief_description: Markup or None = None
        self.detailed_description: Markup or None = None
        self.in_body_text: Markup or None = None
        self.location: Location or None = None
        self.visibility: Visibility or None = None
        self.attributes: [Attribute]
        self.href: str or None = None
        self.file_parent: Def or None = None
        self.scope_parent: Def or None = None

    def kind(self) -> str or None:
        raise NotImplementedError()

    def resolve_refs(self, defs: dict):
        _maybe_resolve_refs(self.brief_description, defs)
        _maybe_resolve_refs(self.detailed_description, defs)
        _maybe_resolve_refs(self.in_body_text, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance = cls()
        instance.id = _require_attr(root.attrib, 'id')

        prot = _maybe_attr(root.attrib, 'prot')
        if prot is not None:
            instance.visibility = Visibility.deserialize(prot)

        instance.attributes = deserialize_attributes(root)

        for elem in root:
            if _elem_empty(elem):
                continue

            if elem.tag in ['name', 'compoundname']:
                instance.qualified_name = _require_text(elem)
            elif elem.tag == 'briefdescription':
                instance.brief_description = Markup.deserialize(elem)
            elif elem.tag == 'detaileddescription':
                instance.detailed_description = Markup.deserialize(elem)
            elif elem.tag == 'inbodydescription':
                instance.in_body_text = Markup.deserialize(elem)
            elif elem.tag == 'location':
                instance.location = Location.deserialize(elem)

        return instance

    def __repr__(self):
        repr = self.kind()
        if repr is None:
            repr = self.__class__.__name__
        if self.name is not None:
            return repr + ' ' + self.name
        if self.qualified_name is not None:
            return repr + ' ' + self.qualified_name
        return repr

    def qualified_name_plaintext(self):
        scope_parent = self.scope_parent
        text = ''
        while scope_parent is not None:
            text = '::'.join((scope_parent.name, text))
            scope_parent = scope_parent.scope_parent
        return text + self.name

    def qualified_name_html(self):
        scope_parent = self.scope_parent
        html = ''
        while scope_parent is not None:
            html = '<a class="ref ref-{}" href="{}">{}</a>::'.format(
                scope_parent.kind(), scope_parent.href, scope_parent.name) + html
            scope_parent = scope_parent.scope_parent
        return '<span class="ref">{}<a class="ref ref-{}" href="{}">{}</a></span>'.format(
            html, self.kind(), self.href, self.name)

    def path_html(self):
        file_parent = self.file_parent
        html = ''
        while file_parent is not None:
            html = '<a class="ref ref-{}" href="{}">{}</a>/'.format(
                file_parent.kind(), file_parent.href, file_parent.name) + html
            file_parent = file_parent.file_parent
        return '<span class="ref">{}<a class="ref ref-{}" href="{}">{}</a></span>'.format(
            html, self.kind(), self.href, self.name)

    def signature_html(self):
        return '{} {}'.format(self.kind(), self.qualified_name_html())

    def signature_plaintext(self):
        return '{} {}'.format(self.kind(), self.qualified_name_plaintext())


class Ref:
    def resolve(self, defs: dict) -> 'Ref':
        return self


class SymbolicRef(Ref):
    def __init__(self, id: str, name: str or None):
        self.id = id
        self.name = name

    def resolve(self, defs: dict) -> 'Ref':
        try:
            return ResolvedRef(defs[self.id])
        except KeyError:
            _warning('Unresolved reference ' + self.id)
            return UnresolvedRef(self.name)


class UnresolvedRef(Ref):
    def __init__(self, name: str):
        self.name = name


class ResolvedRef(Ref):
    def __init__(self, definition: Def):
        self.definition = definition


def deserialize_ref(root: xml.Element) -> Ref or None:
    id = _maybe_attr(root.attrib, 'refid')
    name = _maybe_text(root)
    if id is None:
        if name is None:
            return None
        return UnresolvedRef(name)
    return SymbolicRef(id, name)


class Include(Item):
    def __init__(self):
        self.file: Ref or None = None
        self.local: bool or None = None

    def resolve_refs(self, defs: dict):
        if self.file:
            self.file = self.file.resolve(defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance = cls()
        instance.file = deserialize_ref(root)
        instance.local = _yesno_to_bool(_require_attr(root.attrib, 'local'))
        return instance

    def render_html(self):
        if isinstance(self.file, ResolvedRef):
            name = self.file.definition.name
        else:
            name = self.file.name
        return '<span class="preprocessor">#include &lt;{}&gt;</span>'.format(name)


class SingleDef:
    pass


class MacroDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.params = []
        self.substitution = None

    def kind(self) -> str or None:
        return 'macro'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.substitution, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        for elem in root:
            if elem.tag == 'param':
                for name in elem.findall('defname'):
                    instance.params.append(_require_text(name))
            elif elem.tag == 'initializer':
                instance.substitution = Markup.deserialize(elem)
        return instance

    def signature_html(self):
        return '<span class="preprocessor">#define</span> ' \
               '<a class="ref ref-macro" href="{}">{}</a>({})'.format(
            self.href, self.name, ', '.join('<span class="param macro-param">{}</span>'.format(p)
                                            for p in self.params))

    def signature_plaintext(self):
        return '#define {}({})'.format(self.name, ', '.join(p for p in self.params))


class TypedefDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.type = None
        self.definition = None

    def kind(self) -> str or None:
        return 'typedef'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.definition, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        for elem in root:
            if elem.tag == 'type':
                instance.type = Markup.deserialize(elem)
            elif elem.tag == 'definition':
                instance.definition = Markup.deserialize(elem)
        return instance


class Param(Item):
    def __init__(self):
        self.name: str or None = None
        self.type: Markup or None = None
        self.default: Markup or None = None

    def resolve_refs(self, defs: dict):
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.default, defs)

    @classmethod
    def deserialize(cls, root: xml.Element) -> 'Param':
        instance = cls()
        declname = None
        defname = None
        for elem in root:
            if elem.tag == 'type':
                instance.type = Markup.deserialize(elem)
            elif elem.tag == 'declname':
                declname = _maybe_text(elem)
            elif elem.tag == 'declname':
                defname = _maybe_text(elem)
            elif elem.tag == 'defval':
                instance.default = Markup.deserialize(elem)
        instance.name = declname if declname else defname
        return instance

    def render_html(self):
        html = ''
        if self.type:
            html += '<span class="type param-type">{}</span>'.format(self.type.render_html())
        if self.type and self.name:
            html += ' '
        if self.name:
            html += '<span class="param-name">{}</span>'.format(self.name)
        if self.default:
            html += ' = <span class="param-default">{}</span>'.format(self.default.render_html())
        return html


class FunctionDef(Def, SingleDef):
    @unique
    class Variant(Enum):
        FUNCTION = 0
        SIGNAL = 1
        SLOT = 2
        CONSTRUCTOR = 3
        DESTRUCTOR = 4

        @classmethod
        def deserialize(cls, repr: str) -> 'Variant' or None:
            try:
                return cls.__dict__[repr.upper()]
            except KeyError:
                return None

    def __init__(self):
        super().__init__()
        self.return_type: Markup or None = None
        self.template_params: [Param] = []
        self.parameters: [Param] = []
        self.variant: FunctionDef.Variant or None = None

    def kind(self) -> str or None:
        return self.variant.name.lower() if self.variant is not None else None

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.return_type, defs)
        for param in self.template_params:
            param.resolve_refs(defs)
        for param in self.parameters:
            param.resolve_refs(defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        instance.variant = FunctionDef.Variant.deserialize(_require_attr(root.attrib, 'kind'))
        for elem in root:
            if elem.tag == 'type':
                if instance.variant == FunctionDef.Variant.FUNCTION \
                        and len(elem) == 0 and elem.text is None:
                    if instance.qualified_name.startswith('~'):
                        instance.variant = FunctionDef.Variant.DESTRUCTOR
                    else:
                        instance.variant = FunctionDef.Variant.CONSTRUCTOR
                else:
                    instance.return_type = Markup.deserialize(elem)
            elif elem.tag == 'templateparamlist':
                for param in elem:
                    instance.template_params.append(Param.deserialize(param))
            elif elem.tag == 'param':
                instance.parameters.append(Param.deserialize(elem))
        return instance

    def signature_html(self):
        html = ''
        if self.template_params:
            html += '<span class="template">template&lt;{}&gt;</span> '.format(
                ', '.join(p.render_html() for p in self.template_params))
        if self.return_type:
            html += '<span class="type return-type">{}</span> '.format(
                self.return_type.render_html())
        html += '{}({})'.format(self.qualified_name_html(),
                                ', '.join(p.render_html() for p in self.parameters))
        return html

    def signature_plaintext(self):
        text = ''
        if self.return_type:
            text += self.return_type.render_plaintext() + ' '
        text += self.qualified_name_plaintext()
        if self.template_params:
            text += '<>'
        text += '({})'.format(', '.join(p.type.render_plaintext() for p in self.parameters))
        return text


class VariableDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.type = None
        self.initializer = None

    def kind(self) -> str or None:
        return 'variable'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.initializer, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        for elem in root:
            if elem.tag == 'type':
                instance.return_type = Markup.deserialize(elem)
            if elem.tag == 'initializer':
                instance.initializer = Markup.deserialize(elem)
        return instance


# stub
class PropertyDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.type = None

    def kind(self) -> str or None:
        return 'property'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        for elem in root:
            if elem.tag == 'type':
                instance.return_type = Markup.deserialize(elem)
        return instance


class EnumValueDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.initializer = None

    def kind(self) -> str or None:
        return 'enum value'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.initializer, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        for elem in root:
            if elem.tag == 'initializer':
                instance.initializer = Markup.deserialize(elem)
        return instance


class EnumDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.underlying_type = None
        self.strong = None
        self.values = []

    def kind(self) -> str or None:
        return 'enum'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.underlying_type, defs)
        for value in self.values:
            value.resolve_refs(defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        strong = _maybe_attr(root.attrib, 'strong')
        if strong:
            instance.strong = _yesno_to_bool(strong)
        for elem in root:
            if elem.tag == 'type':
                instance.underlying_type = Markup.deserialize(elem)
            if elem.tag == 'enumvalue':
                instance.values.append(EnumValueDef.deserialize(elem))
        return instance


class FriendDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.definition = None

    def kind(self) -> str or None:
        return 'friend'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.definition, defs)

    @classmethod
    def deserialize(cls, root: xml.Element):
        instance: cls = super().deserialize(root)
        for elem in root:
            if elem.tag == 'definition':
                instance.definition = Markup.deserialize(elem)
        return instance


class CompoundDef(Def, SingleDef):
    def __init__(self):
        super().__init__()
        self.language: str or None = None
        self.members: [Ref] = []

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for i in range(len(self.members)):
            self.members[i] = self.members[i].resolve(defs)

    @classmethod
    def deserialize(cls, root: xml.Element) -> ('CompoundDef', [Def]):
        instance: cls = super().deserialize(root)
        defs: [Def] = [instance]

        instance.language = _maybe_attr(root.attrib, 'language')

        for elem in root:
            if elem.tag.startswith('inner'):
                instance.members.append(deserialize_ref(elem))
            elif elem.tag == 'sectiondef':
                for member in elem.findall('memberdef'):
                    child = None

                    if member.attrib['kind'] == 'define':
                        child = MacroDef.deserialize(member)
                    elif member.attrib['kind'] == 'typedef':
                        child = TypedefDef.deserialize(member)
                    elif member.attrib['kind'] in ['function', 'signal', 'slot']:
                        child = FunctionDef.deserialize(member)
                    elif member.attrib['kind'] == 'variable':
                        child = VariableDef.deserialize(member)
                    elif member.attrib['kind'] == 'property':
                        child = PropertyDef.deserialize(member)
                    elif member.attrib['kind'] == 'enum':
                        child = EnumDef.deserialize(member)
                    elif member.attrib['kind'] == 'friend':
                        child = FriendDef.deserialize(member)
                    else:
                        _warning('Unknown member kind ' + member.attrib['kind'])

                    if child is not None:
                        defs.append(child)
                        instance.members.append(SymbolicRef(child.id, child.qualified_name))

        return instance, defs


class DirectoryDef(CompoundDef, SingleDef):
    def kind(self) -> str or None:
        return 'directory'


class FileDef(CompoundDef, SingleDef):
    def __init__(self):
        super().__init__()
        self.includes: [Include] = []

    def kind(self) -> str or None:
        return 'file'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for include in self.includes:
            include.resolve_refs(defs)

    @classmethod
    def deserialize(cls, root: xml.Element) -> ('FileDef', [Def]):
        file: FileDef
        file, defs = super().deserialize(root)

        for elem in root:
            if elem.tag == 'includes':
                file.includes.append(Include.deserialize(elem))

        return file, defs


class NamespaceDef(CompoundDef):
    def kind(self) -> str or None:
        return 'namespace'


class GroupDef(CompoundDef):
    def kind(self) -> str or None:
        return 'group'


# Stub
class PageDef(CompoundDef):
    def kind(self) -> str or None:
        return 'page'


class CompoundSingleDef(CompoundDef, SingleDef):
    def __init__(self):
        super().__init__()
        self.include: Include or None = None

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        if self.include is not None:
            self.include.resolve_refs(defs)

    @classmethod
    def deserialize(cls, root: xml.Element) -> ('ClassDef', [Def]):
        item: cls
        item, defs = super().deserialize(root)

        for elem in root:
            if elem.tag == 'includes':
                item.include = Include.deserialize(elem)

        return item, defs


class Inheritance(Item):
    def __init__(self):
        self.ref: Ref or None = None
        self.visibility: Visibility or None = None
        self.virtual: bool or None = None

    def resolve_refs(self, defs: dict):
        if self.ref is not None:
            self.ref = self.ref.resolve(defs)

    @classmethod
    def deserialize(cls, root: xml.Element) -> 'Inheritance':
        instance = cls()
        instance.ref = deserialize_ref(root)
        instance.visibility = Visibility.deserialize(root.attrib['prot'])
        instance.virtual = _maybe_attr(root.attrib, 'virt') == 'virtual'
        return instance


class ClassDef(CompoundSingleDef):
    @unique
    class Variant(Enum):
        CLASS = 0
        STRUCT = 1
        UNION = 2
        PROTOCOL = 3
        INTERFACE = 4
        CATEGORY = 5

        @classmethod
        def deserialize(cls, repr: str) -> 'Variant' or None:
            try:
                return cls.__dict__[repr.upper()]
            except KeyError:
                return None

    def __init__(self):
        super().__init__()
        self.template_params: [Param] = []
        self.bases: [Inheritance] = []
        self.variant: ClassDef.Variant or None = None

    def kind(self) -> str or None:
        return self.variant.name.lower() if self.variant is not None else None

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for param in self.template_params:
            param.resolve_refs(defs)
        for base in self.bases:
            base.resolve_refs(defs)

    @classmethod
    def deserialize(cls, root: xml.Element) -> ('ClassDef', [Def]):
        klass: cls
        klass, defs = super().deserialize(root)
        klass.variant = cls.Variant.deserialize(_require_attr(root.attrib, 'kind'))

        for elem in root:
            if elem.tag == 'basecompoundref':
                klass.bases.append(Inheritance.deserialize(elem))
            if elem.tag == 'templateparamlist':
                for param in elem:
                    klass.template_params.append(Param.deserialize(param))

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
        return FileDef.deserialize(node)[1]
    elif kind == 'dir':
        return DirectoryDef.deserialize(node)[1]
    elif kind in ['class', 'struct', 'union', 'protocol', 'interface', 'category']:
        return ClassDef.deserialize(node)[1]
    elif kind == 'namespace':
        return NamespaceDef.deserialize(node)[1]
    elif kind == 'group':
        return GroupDef.deserialize(node)[1]
    elif kind == 'page':
        return PageDef.deserialize(node)[1]
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
    d.href = d.id + '.html'


def load(files: [str]) -> [Def]:
    defs = []
    global file_name
    for file_name in files:
        with open(file_name, 'rb') as f:
            defs += _parse(f)

    _resolve_refs(defs)

    for d in defs:
        _assign_parents(d)

    for d in defs:
        _unqualify_names(d)
    for d in defs:
        if d.name is None:
            d.name = d.qualified_name

    for d in defs:
        _derive_brief_description(d)
        _generate_href(d)

    return defs
