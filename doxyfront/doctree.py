import os

from . import source


def doctree(defs: [source.Def], outdir: str):
    for d in defs:
        with open(os.path.join(outdir, d.id + '.html'), 'w') as f:
            print('<!DOCTYPE html><html><head><title>{1}</title></head><body><h1>{0} {1}</h1><ul>'.format(
                d.kind(), d.name), file=f)
            if isinstance(d, source.CompoundDef):
                for m in d.members:
                    if isinstance(m, source.ResolvedRef):
                        e = m.definition
                        print('<li><a href="{}.html">{} {}</a></li>'.format(e.id, e.kind(), e.name), file=f)
            print('</ul></body></html>', file=f)
