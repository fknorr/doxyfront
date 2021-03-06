from enum import Enum, unique
import sys
import re
from typing import Dict, Optional


def _warning(msg: str, file_name: str):
    print('{}: {}'.format(file_name, msg), file=sys.stderr)


class Item:
    def resolve_refs(self, defs: dict):
        pass


def _maybe_resolve_refs(item: Optional[Item], defs: dict):
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
    def __init__(self, text: Optional[str] = None):
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
    def __init__(self, ref: Optional['Ref'] = None):
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
    def __init__(self, url: Optional[str] = None):
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
        self.file: Optional[str] = None
        self.line: Optional[int] = None


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


_NON_SLUG_CHARS = re.compile('[^a-z-]+')


class SymbolDef:
    def slug(self):
        assert isinstance(self, Def)
        slug = self.name.lower()
        scope_parent = self.scope_parent
        while scope_parent is not None and not isinstance(scope_parent, IndexDef):
            slug = '{}-{}'.format(scope_parent.name.lower(), slug)
            scope_parent = scope_parent.scope_parent
        return _NON_SLUG_CHARS.sub('', slug)


class PathDef:
    def slug(self):
        assert isinstance(self, Def)
        slug = self.name.lower()
        file_parent = self.file_parent
        while file_parent is not None and not isinstance(file_parent, IndexDef):
            slug = '{}-{}'.format(self.file_parent.name.lower(), slug)
            file_parent = file_parent.file_parent
        return _NON_SLUG_CHARS.sub('', slug)


class Def(Item):
    def __init__(self):
        self.id: Optional[str] = None
        self.name: Optional[str] = None
        self.qualified_name: Optional[str] = None
        self.brief_description: Optional[Markup] = None
        self.detailed_description: Optional[Markup] = None
        self.in_body_text: Optional[Markup] = None
        self.location: Optional[Location] = None
        self.visibility: Optional[Visibility] = None
        self.attributes: [Attribute]
        self.page: Optional[str] = None
        self.href: Optional[str] = None
        self.file_parent: Optional[Def] = None
        self.scope_parent: Optional[Def] = None

    def kind(self) -> Optional[str]:
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
        while scope_parent is not None and not isinstance(scope_parent, IndexDef) \
                and scope_parent not in context:
            text = '::'.join((scope_parent.name, text))
            scope_parent = scope_parent.scope_parent
        return text + self.name

    def qualified_name_html(self, context: set):
        scope_parent = self.scope_parent
        html = ''
        while scope_parent is not None and not isinstance(scope_parent, IndexDef) \
                and scope_parent not in context:
            html = '<a class="ref ref-{}" href="{}">{}</a><span class="scope">::</span>'.format(
                scope_parent.kind(), scope_parent.href, scope_parent.name) + html
            scope_parent = scope_parent.scope_parent
        return '{}<a class="ref ref-{}" href="{}">{}</a>'.format(
            html, self.kind(), self.href, self.name)

    def path_plaintext(self, short=False):
        file_parent = self.file_parent
        text = self.name
        while not short and file_parent is not None and not isinstance(file_parent, IndexDef):
            text = '{}/{}'.format(file_parent.name, text)
            file_parent = file_parent.file_parent
        return text

    def path_html(self, short=False):
        file_parent = self.file_parent
        html = '<a class="ref ref-{}" href="{}">{}</a>'.format(self.kind(), self.href, self.name)
        while not short and file_parent is not None and not isinstance(file_parent, IndexDef):
            html = '<a class="ref ref-{}" href="{}">{}</a>/{}'.format(
                file_parent.kind(), file_parent.href, file_parent.name, html)
            file_parent = file_parent.file_parent
        return html

    def signature_html(self, context, fully_qualified=False):
        if isinstance(self, PathDef):
            sig = self.path_html(short=not fully_qualified)
        else:
            sig = self.qualified_name_html(context if not fully_qualified else set())
        return None, '{} {}'.format(self.kind(), sig)

    def signature_plaintext(self, context, fully_qualified=False):
        if isinstance(self, PathDef):
            sig = self.path_plaintext(short=not fully_qualified)
        else:
            sig = self.qualified_name_plaintext(context if not fully_qualified else set())
        return '{} {}'.format(self.kind(), sig)


class Ref:
    def resolve(self, defs: Dict[str, Def]) -> 'Ref':
        return self


class SymbolicRef(Ref):
    def __init__(self, id: str, name: Optional[str]):
        self.id = id
        self.name = name

    def resolve(self, defs: Dict[str, Def]) -> 'Ref':
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
        self.file: Optional[Ref] = None
        self.local: Optional[bool] = None

    def resolve_refs(self, defs: Dict[str, Def]):
        if self.file:
            self.file = self.file.resolve(defs)


class MacroDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.params = []
        self.substitution = None

    def kind(self) -> Optional[str]:
        return 'macro'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.substitution, defs)

    def signature_html(self, context, fully_qualified=False):
        return None, '<span class="preprocessor">#define</span> ' \
               '<a class="ref ref-macro" href="{}">{}</a>({})'.format(
            self.href, self.name, ', '.join('<span class="param macro-param">{}</span>'.format(p)
                                            for p in self.params))

    def signature_plaintext(self, context, fully_qualified=False):
        return '#define {}({})'.format(self.name, ', '.join(p for p in self.params))

    def slug(self):
        return 'm-' + super().slug()


class TypedefDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.template_params: [Param] = []
        self.type = None
        self.definition = None

    def kind(self) -> Optional[str]:
        return 'typedef'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for param in self.template_params:
            param.resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.definition, defs)

    def signature_html(self, context, fully_qualified=False):
        template_html = None
        if self.template_params:
            template_html = 'template&lt;{}&gt; '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        html = 'using {} = {}'.format(
            self.qualified_name_html(context if not fully_qualified else set()),
            self.type.render_html(context))
        return template_html, html

    def signature_plaintext(self, context, fully_qualified=False):
        text = 'using {} = {}'.format(
            self.qualified_name_plaintext(context if not fully_qualified else set()),
            self.type.render_plaintext(context))
        if self.template_params:
            text += '<>'
        return text

    def slug(self):
        return 't-' + super().slug()


class Param(Item):
    def __init__(self):
        self.name: Optional[str] = None
        self.type: Optional[Markup] = None
        self.default: Optional[Markup] = None

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
        self.return_type: Optional[Markup] = None
        self.template_params: [Param] = []
        self.parameters: [Param] = []
        self.variant: Optional[FunctionDef.Variant] = None

    def kind(self) -> Optional[str]:
        return self.variant.name.lower() if self.variant is not None else None

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.return_type, defs)
        for param in self.template_params:
            param.resolve_refs(defs)
        for param in self.parameters:
            param.resolve_refs(defs)

    def signature_html(self, context, fully_qualified=False):
        template_html = None
        if self.template_params:
            template_html = 'template&lt;{}&gt; '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        html = ''.join('{} '.format(a.render_html()) for a in attr_before)
        if self.return_type:
            html += '<span class="type return-type">{}</span> '.format(
                self.return_type.render_html(context))
        html += '{}({})'.format(self.qualified_name_html(context if not fully_qualified else set()),
                                ', '.join(p.render_html(context) for p in self.parameters))
        html += ''.join(' {}'.format(a.render_html()) for a in attr_after)
        return template_html, html

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

    def slug(self):
        return 'fn-' + super().slug()


class VariableDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.type = None
        self.initializer = None

    def kind(self) -> Optional[str]:
        return 'variable'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)
        _maybe_resolve_refs(self.initializer, defs)

    def signature_html(self, context, fully_qualified=False):
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        html = ''.join('{} '.format(a.render_html()) for a in attr_before)
        if self.type:
            html += '<span class="type var-type">{}</span> '.format(
                self.type.render_html(context))
        html += self.qualified_name_html(context if not fully_qualified else set())
        html += ''.join(' {}'.format(a.render_html()) for a in attr_after)
        return None, html

    def signature_plaintext(self, context, fully_qualified=False):
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        text = ''.join('{} '.format(a.render_plaintext()) for a in attr_before)
        if self.type:
            text += self.type.render_plaintext(context) + ' '
        text += self.qualified_name_plaintext(context if not fully_qualified else set())
        text += ''.join(' {}'.format(a.render_plaintext()) for a in attr_after)
        return text

    def slug(self):
        return 'v-' + super().slug()


# stub
class PropertyDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.type = None

    def kind(self) -> Optional[str]:
        return 'property'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.type, defs)

    def slug(self):
        return 'p-' + super().slug()


class FriendDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.template_params: [Param] = []
        self.definition = None

    def kind(self) -> Optional[str]:
        return 'friend'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.definition, defs)

    def signature_html(self, context, fully_qualified=False):
        template_html = None
        if self.template_params:
            template_html = 'template&lt;{}&gt; '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        html = self.definition.render_html(context if not fully_qualified else set())
        return template_html, html

    def signature_plaintext(self, context, fully_qualified=False):
        return self.definition.render_plaintext(context if not fully_qualified else set())

    def slug(self):
        return 'fr-' + super().slug()


class CompoundDef(Def):
    def __init__(self):
        super().__init__()
        self.language: Optional[str] = None
        self.members: [Ref] = []

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for i in range(len(self.members)):
            self.members[i] = self.members[i].resolve(defs)


class EnumVariantDef(Def, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.initializer = None

    def kind(self) -> Optional[str]:
        return 'enum-variant'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.initializer, defs)

    def slug(self):
        return 'ev-' + super().slug()

    def signature_html(self, context, fully_qualified=False):
        html = self.qualified_name_html(context if not fully_qualified else set())
        if self.initializer is not None:
            html = '{} {}'.format(html, self.initializer.render_html(context))
        return None, html

    def signature_plaintext(self, context, fully_qualified=False):
        text = self.qualified_name_plaintext(context if not fully_qualified else set())
        if self.initializer is not None:
            text = '{} {}'.format(text, self.initializer.render_plaintext(context))
        return text


class EnumDef(CompoundDef, SingleDef, SymbolDef):
    def __init__(self):
        super().__init__()
        self.underlying_type = None
        self.strong = None

    def kind(self) -> Optional[str]:
        return 'enum'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        _maybe_resolve_refs(self.underlying_type, defs)

    def signature_html(self, context, fully_qualified=False):
        html = '{} {}'.format(
            'enum class' if self.strong else 'enum',
            self.qualified_name_html(context if not fully_qualified else set()))
        if self.underlying_type is not None:
            html += ': {}'.format(self.underlying_type.render_html(context))
        return None, html

    def signature_plaintext(self, context, fully_qualified=False):
        text = '{} {}'.format(
            'enum class' if self.strong else 'enum',
            self.qualified_name_plaintext(context if not fully_qualified else set()))
        if self.underlying_type is not None:
            text += ': {}'.format(self.underlying_type.render_plaintext(context))
        return text

    def slug(self):
        return 'e-' + super().slug()


class DirectoryDef(CompoundDef, SingleDef, PathDef):
    def kind(self) -> Optional[str]:
        return 'directory'

    def slug(self):
        return 'dir-' + super().slug()


class FileDef(CompoundDef, SingleDef, PathDef):
    def __init__(self):
        super().__init__()
        self.includes: [Include] = []

    def kind(self) -> Optional[str]:
        return 'file'

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for include in self.includes:
            include.resolve_refs(defs)

    def slug(self):
        return 'file-' + super().slug()


class NamespaceDef(CompoundDef, SymbolDef):
    def kind(self) -> Optional[str]:
        return 'namespace'

    def slug(self):
        return 'ns-' + super().slug()


class GroupDef(CompoundDef):
    def kind(self) -> Optional[str]:
        return 'group'

    def slug(self):
        return 'g-' + _NON_SLUG_CHARS.sub('', self.name.lower())


# Stub
class PageDef(CompoundDef):
    def kind(self) -> Optional[str]:
        return 'page'

    def slug(self):
        return 'page-' + _NON_SLUG_CHARS.sub('', self.name.lower())


class Inheritance(Item):
    def __init__(self):
        self.ref: Optional[Ref] = None
        self.visibility: Optional[Visibility] = None
        self.virtual: Optional[bool] = None

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
        self.variant: Optional[ClassDef.Variant] = None

    def kind(self) -> Optional[str]:
        return self.variant.name.lower() if self.variant is not None else None

    def resolve_refs(self, defs: dict):
        super().resolve_refs(defs)
        for param in self.template_params:
            param.resolve_refs(defs)
        for base in self.bases:
            base.resolve_refs(defs)

    def signature_html(self, context, fully_qualified=False):
        template_html = None
        if self.template_params:
            template_html = 'template&lt;{}&gt; '.format(
                ', '.join(p.render_html(context) for p in self.template_params))
        attr_before, attr_after = cpp_order_attributes(self.attributes)
        html = ''.join('{} '.format(a.render_html()) for a in attr_before)
        html += '{} {}'.format(
            self.kind(), self.qualified_name_html(context if not fully_qualified else set()))
        html += ''.join(' {}'.format(a.render_html()) for a in attr_after)
        return template_html, html

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

    def slug(self):
        return 'c-' + super().slug()


class IndexDef(CompoundDef):
    def __init__(self, id: str, name: str):
        super().__init__()
        self.id = id
        self.name = name

    def signature_html(self, context, fully_qualified=False):
        return None, self.qualified_name_html(context)

    def signature_plaintext(self, context, fully_qualified=False):
        return self.qualified_name_plaintext(context)

    def kind(self) -> Optional[str]:
        return 'index'

    def slug(self):
        return self.id
