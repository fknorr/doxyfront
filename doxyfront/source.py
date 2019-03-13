import xml.etree.ElementTree as xml
from enum import Enum, unique
import sys


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


class Markup(Item):
    def __init__(self):
        self.text = None

    @classmethod
    def deserialize(cls, node: xml.Element) -> 'Markup' or None:
        instance = cls()
        instance.text = node.text
        return instance


class Listing(Item):
    def __init__(self):
        self.code = None

    @classmethod
    def deserialize(cls, node: xml.Element) -> 'Listing' or None:
        instance = cls()
        instance.code = node.text
        return instance


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


def deserialize_attributes(node: xml.Element) -> [Attribute]:
    attrs = []
    for k, v in node.attrib.items():
        try:
            a = Attribute.__dict__[k.upper()]
            if _yesno_to_bool(v):
                attrs.append(a)
        except KeyError:
            pass
    return attrs


class Def(Item):
    def __init__(self):
        self.id: str or None = None
        self.name: str or None = None
        self.brief_text: Markup or None = None
        self.detail_text: Markup or None = None
        self.in_body_text: Markup or None = None
        self.location: Location or None = None
        self.visibility: Visibility or None = None
        self.attributes: [Attribute]

    def kind(self) -> str or None:
        raise NotImplementedError()

    def resolve_refs(self, defs: dict):
        _maybe_resolve_refs(self.brief_text, defs)
        _maybe_resolve_refs(self.detail_text, defs)
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
            if elem.tag in ['name', 'compoundname']:
                instance.name = _require_text(elem)
            elif elem.tag == 'briefdescription':
                instance.brief_text = Markup.deserialize(elem)
            elif elem.tag == 'detaileddescription':
                instance.detail_text = Markup.deserialize(elem)
            elif elem.tag == 'inbodydescription':
                instance.in_body_text = Markup.deserialize(elem)
            elif elem.tag == 'location':
                instance.location = Location.deserialize(elem)
        return instance


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


class MacroDef(Def):
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
                instance.substitution = Listing.deserialize(elem)
        return instance


class TypedefDef(Def):
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
                instance.type = Listing.deserialize(elem)
            elif elem.tag == 'definition':
                instance.definition = Listing.deserialize(elem)
        return instance


class Param(Item):
    def __init__(self):
        self.name: str or None = None
        self.type: Listing or None = None
        self.default: Listing or None = None

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
                instance.type = Listing.deserialize(elem)
            elif elem.tag == 'declname':
                declname = _maybe_text(elem)
            elif elem.tag == 'declname':
                defname = _maybe_text(elem)
            elif elem.tag == 'defval':
                instance.default = Listing.deserialize(elem)
        instance.name = declname if declname else defname
        return instance


class FunctionDef(Def):
    @unique
    class Variant(Enum):
        FUNCTION = 0
        SIGNAL = 1
        SLOT = 2

        @classmethod
        def deserialize(cls, repr: str) -> 'Variant' or None:
            try:
                return cls.__dict__[repr.upper()]
            except KeyError:
                return None

    def __init__(self):
        super().__init__()
        self.return_type: Listing or None = None
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
                instance.return_type = Listing.deserialize(elem)
            elif elem.tag == 'templateparamlist':
                for param in elem:
                    instance.template_params.append(Param.deserialize(param))
            elif elem.tag == 'param':
                instance.parameters.append(Param.deserialize(elem))
        return instance


class VariableDef(Def):
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
                instance.return_type = Listing.deserialize(elem)
            if elem.tag == 'initializer':
                instance.initializer = Listing.deserialize(elem)
        return instance


# stub
class PropertyDef(Def):
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
                instance.return_type = Listing.deserialize(elem)
        return instance


class EnumValueDef(Def):
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
                instance.initializer = Listing.deserialize(elem)
        return instance


class EnumDef(Def):
    def __init__(self):
        super().__init__()
        self.underlying_type = None
        self.strong = None
        self.values = []

    def kind(self) -> str or None:
        return 'enum class' if self.strong else 'enum'

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
                instance.underlying_type = Listing.deserialize(elem)
            if elem.tag == 'enumvalue':
                instance.values.append(EnumValueDef.deserialize(elem))
        return instance


class FriendDef(Def):
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
                instance.definition = Listing.deserialize(elem)
        return instance


class CompoundDef(Def):
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
                        instance.members.append(SymbolicRef(child.id, child.name))

        return instance, defs


class DirectoryDef(CompoundDef):
    def kind(self) -> str or None:
        return 'directory'


class FileDef(CompoundDef):
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


class CompoundSingleDef(CompoundDef):
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


def load(files: [str]) -> [Def]:
    defs = []
    global file_name
    for file_name in files:
        with open(file_name, 'rb') as f:
            defs += _parse(f)
    _resolve_refs(defs)
    return defs
