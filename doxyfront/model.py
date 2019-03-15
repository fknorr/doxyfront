from enum import Enum, unique
import sys
import re


file_name = None


def _warning(msg: str):
    global file_name
    print('{}: {}'.format(file_name, msg), file=sys.stderr)


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


class Fragment(Item):
    def __init__(self):
        self.children: [Fragment] = []

    def resolve_refs(self, defs: dict):
        for c in self.children:
            c.resolve_refs(defs)

    def render_plaintext(self, context) -> str:
        return ' '.join(c.render_plaintext(context) for c in self.children)

    def render_html(self, context) -> str:
        return ' '.join(c.render_html(context) for c in self.children)


class TextFragment(Fragment):
    def __init__(self, text: str or None = None):
        super().__init__()
        self.text = text

    def render_plaintext(self, context) -> str:
        return self.text

    def render_html(self, context) -> str:
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

    def render_html(self, context) -> str:
        return '<{0}>{1}</{0}>'.format(self.variant.value.lower(), super().render_html(context))


class RefFragment(Fragment):
    def __init__(self, ref: 'Ref' or None = None):
        super().__init__()
        self.ref = ref

    def render_html(self, context) -> str:
        content = super().render_html(context)
        if isinstance(self.ref, ResolvedRef):
            return self.ref.definition.qualified_name_html(context)
        return content

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        self.ref = self.ref.resolve(defs)


class LinkFragment(Fragment):
    def __init__(self, url: str or None = None):
        super().__init__()
        self.url = url

    def render_html(self, context) -> str:
        return '<a class="external" href="{}">{}</a>'.format(self.url, super().render_html(context))


class SectionFragment(Fragment):
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind

    def render_html(self, context) -> str:
        return '<section><h3>{}</h3>{}</section>'.format(self.kind, super().render_html(context))


_SUPERFLUOUS_WHITESPACE_RE = re.compile(r'(^\s+)|(?<=[\s(])\s+|\s+(?=[.,)])|(\s+$)')


class Markup(Item):
    def __init__(self):
        self.root = Fragment()

    def resolve_refs(self, defs: dict):
        self.root.resolve_refs(defs)

    def render_plaintext(self, context):
        return _SUPERFLUOUS_WHITESPACE_RE.sub('', self.root.render_plaintext(context))

    def render_html(self, context):
        return self.root.render_html(context)


class Location:
    def __init__(self):
        self.file: str or None = None
        self.line: int or None = None


@unique
class Visibility(Enum):
    PUBLIC = '+'
    PACKAGE = '~'
    PROTECTED = '#'
    PRIVATE = '-'


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
    CONST = 10

    def __repr__(self):
        return self.__class__.__name__ + '.' + self.name

    def render_plaintext(self):
        if self == Attribute.ABSTRACT:
            return "= 0"
        return self.name.lower()

    def render_html(self):
        if self == Attribute.ABSTRACT:
            return '<span class="attrib attrib-abstract">= 0</span>'
        return '<span class="attrib attrib-{0}">{0}</span>'.format(self.name.lower())


def cpp_order_attributes(attrs: [Attribute]) -> ([Attribute], [Attribute]):
    may_before = [Attribute.STATIC, Attribute.VIRTUAL, Attribute.CONSTEXPR, Attribute.MUTABLE,
                  Attribute.EXPLICIT]
    may_after = [Attribute.CONST, Attribute.OVERRIDE, Attribute.FINAL, Attribute.ABSTRACT]
    return [a for a in may_before if a in attrs], [a for a in may_after if a in attrs]


class SingleDef:
    pass


class SymbolDef:
    pass


class PathDef:
    pass


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

    def __repr__(self):
        repr = self.kind()
        if repr is None:
            repr = self.__class__.__name__
        if self.name is not None:
            return repr + ' ' + self.name
        if self.qualified_name is not None:
            return repr + ' ' + self.qualified_name
        return repr

    def qualified_name_plaintext(self, context: set):
        scope_parent = self.scope_parent
        text = ''
        while scope_parent is not None and scope_parent not in context:
            text = '::'.join((scope_parent.name, text))
            scope_parent = scope_parent.scope_parent
        return text + self.name

    def qualified_name_html(self, context: set):
        scope_parent = self.scope_parent
        html = ''
        while scope_parent is not None and scope_parent not in context:
            html = '<a class="ref ref-{}" href="{}">{}</a><span class="scope">::</span>'.format(
                scope_parent.kind(), scope_parent.href, scope_parent.name) + html
            scope_parent = scope_parent.scope_parent
        return '<span class="ref">{}<a class="ref ref-{}" href="{}">{}</a></span>'.format(
            html, self.kind(), self.href, self.name)

    def path_plaintext(self, short=False):
        file_parent = self.file_parent
        text = self.name
        while not short and file_parent is not None:
            text = '{}/{}'.format(file_parent.name, text)
            file_parent = file_parent.file_parent
        return text

    def path_html(self, short=False):
        file_parent = self.file_parent
        html = '<a class="ref ref-{}" href="{}">{}</a>'.format(self.kind(), self.href, self.name)
        while not short and file_parent is not None:
            html = '<a class="ref ref-{}" href="{}">{}</a>/{}'.format(
                file_parent.kind(), file_parent.href, file_parent.name, html)
            file_parent = file_parent.file_parent
        return '<span class="ref">{}</span>'.format(html)

    def signature_html(self, context, fully_qualified=False):
        if isinstance(self, PathDef):
            sig = self.path_html(short=not fully_qualified)
        else:
            sig = self.qualified_name_html(context if not fully_qualified else set())
        return '{} {}'.format(self.kind(), sig)

    def signature_plaintext(self, context, fully_qualified=False):
        if isinstance(self, PathDef):
            sig = self.path_plaintext(short=not fully_qualified)
        else:
            sig = self.qualified_name_plaintext(context if not fully_qualified else set())
        return '{} {}'.format(self.kind(), sig)


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


class Include(Item):
    def __init__(self):
        self.file: Ref or None = None
        self.local: bool or None = None

    def resolve_refs(self, defs: dict):
        if self.file:
            self.file = self.file.resolve(defs)


class MacroDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.params = []
        self.substitution = None

    def kind(self) -> str or None:
        return 'macro'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.substitution, defs)

    def signature_html(self, context, fully_qualified=False):
        return '<span class="preprocessor">#define</span> ' \
               '<a class="ref ref-macro" href="{}">{}</a>({})'.format(
            self.href, self.name, ', '.join('<span class="param macro-param">{}</span>'.format(p)
                                            for p in self.params))

    def signature_plaintext(self, context, fully_qualified=False):
        return '#define {}({})'.format(self.name, ', '.join(p for p in self.params))


class TypedefDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.template_params: [Param] = []
        self.type = None
        self.definition = None

    def kind(self) -> str or None:
        return 'typedef'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for param in self.template_params:
            param.resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.definition, defs)

    def signature_html(self, context, fully_qualified=False):
        html = ''
        if self.template_params:
            html += '<span class="template">template&lt;{}&gt;</span> '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        html += 'using {} = {}'.format(
            self.qualified_name_html(context if not fully_qualified else set()),
            self.type.render_html(context))
        return html

    def signature_plaintext(self, context, fully_qualified=False):
        text = ''
        text += 'using {} = {}'.format(
            self.qualified_name_plaintext(context if not fully_qualified else set()),
            self.type.render_plaintext(context))
        if self.template_params:
            text += '<>'
        return text


class Param(Item):
    def __init__(self):
        self.name: str or None = None
        self.type: Markup or None = None
        self.default: Markup or None = None

    def resolve_refs(self, defs: dict):
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.default, defs)

    def render_html(self, context):
        html = ''
        if self.type:
            html += '<span class="type param-type">{}</span>'.format(self.type.render_html(context))
        if self.type and self.name:
            html += ' '
        if self.name:
            html += '<span class="param-name">{}</span>'.format(self.name)
        if self.default:
            html += ' = <span class="param-default">{}</span>'.format(
                self.default.render_html(context))
        return html


class FunctionDef(Def, SingleDef, SymbolDef):
    @unique
    class Variant(Enum):
        FUNCTION = 0
        SIGNAL = 1
        SLOT = 2
        CONSTRUCTOR = 3
        DESTRUCTOR = 4

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

    def signature_html(self, context, fully_qualified=False):
        html = ''
        if self.template_params:
            html += '<span class="template">template&lt;{}&gt;</span> '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        html += ''.join('{} '.format(a.render_html()) for a in attr_before)
        if self.return_type:
            html += '<span class="type return-type">{}</span> '.format(
                self.return_type.render_html(context))
        html += '{}({})'.format(self.qualified_name_html(context if not fully_qualified else set()),
                                ', '.join(p.render_html(context) for p in self.parameters))
        html += ''.join(' {}'.format(a.render_html()) for a in attr_after)
        return html

    def signature_plaintext(self, context, fully_qualified=False):
        text = ''
        if self.return_type:
            text += self.return_type.render_plaintext(context) + ' '
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        text += ''.join('{} '.format(a.render_plaintext()) for a in attr_before)
        text += self.qualified_name_plaintext(context if not fully_qualified else set())
        if self.template_params:
            text += '<>'
        text += '({})'.format(', '.join(p.type.render_plaintext(context) for p in self.parameters))
        text += ''.join(' {}'.format(a.render_plaintext()) for a in attr_after)
        return text


class VariableDef(Def, SingleDef, SymbolDef):
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


# stub
class PropertyDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.type = None

    def kind(self) -> str or None:
        return 'property'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)


class EnumValueDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.initializer = None

    def kind(self) -> str or None:
        return 'enum value'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.initializer, defs)


class EnumDef(Def, SingleDef, SymbolDef):
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

    def signature_html(self, context, fully_qualified=False):
        html = ''
        html += '{} {}'.format(
            'enum class' if self.strong else 'enum',
            self.qualified_name_html(context if not fully_qualified else set()))
        if self.underlying_type is not None:
            html += ': {}'.format(self.underlying_type.render_html(context))
        return html

    def signature_plaintext(self, context, fully_qualified=False):
        text = ''
        text += '{} {}'.format(
            'enum class' if self.strong else 'enum',
            self.qualified_name_plaintext(context if not fully_qualified else set()))
        if self.underlying_type is not None:
            text += ': {}'.format(self.underlying_type.render_plaintext(context))
        return text


class FriendDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.definition = None

    def kind(self) -> str or None:
        return 'friend'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.definition, defs)


class CompoundDef(Def):
    def __init__(self):
        super().__init__()
        self.language: str or None = None
        self.members: [Ref] = []

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for i in range(len(self.members)):
            self.members[i] = self.members[i].resolve(defs)


class DirectoryDef(CompoundDef, SingleDef, PathDef):
    def kind(self) -> str or None:
        return 'directory'


class FileDef(CompoundDef, SingleDef, PathDef):
    def __init__(self):
        super().__init__()
        self.includes: [Include] = []

    def kind(self) -> str or None:
        return 'file'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for include in self.includes:
            include.resolve_refs(defs)


class NamespaceDef(CompoundDef, SymbolDef):
    def kind(self) -> str or None:
        return 'namespace'


class GroupDef(CompoundDef):
    def kind(self) -> str or None:
        return 'group'


# Stub
class PageDef(CompoundDef):
    def kind(self) -> str or None:
        return 'page'


class Inheritance(Item):
    def __init__(self):
        self.ref: Ref or None = None
        self.visibility: Visibility or None = None
        self.virtual: bool or None = None

    def resolve_refs(self, defs: dict):
        if self.ref is not None:
            self.ref = self.ref.resolve(defs)


class ClassDef(CompoundDef, SymbolDef, SingleDef):
    @unique
    class Variant(Enum):
        CLASS = 0
        STRUCT = 1
        UNION = 2
        PROTOCOL = 3
        INTERFACE = 4
        CATEGORY = 5

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

    def signature_html(self, context, fully_qualified=False):
        html = ''
        if self.template_params:
            html += '<span class="template">template&lt;{}&gt;</span> '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        html += ''.join('{} '.format(a.render_html()) for a in attr_before)
        html += '{} {}'.format(
            self.kind(), self.qualified_name_html(context if not fully_qualified else set()))
        html += ''.join(' {}'.format(a.render_html()) for a in attr_after)
        return html

    def signature_plaintext(self, context, fully_qualified=False):
        text = ''
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        text += ''.join('{} '.format(a.render_plaintext()) for a in attr_before)
        text += '{} {}'.format(
            self.kind(), self.qualified_name_plaintext(context if not fully_qualified else set()))
        if self.template_params:
            text += '<>'
        text += ''.join(' {}'.format(a.render_plaintext()) for a in attr_after)
        return text
