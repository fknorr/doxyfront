import os

from doxyfront import depgraph, source, doctree

if __name__ == '__main__':
    files = [f for f in os.listdir(os.getcwd()) if f.endswith('.xml')]
    defs = source.load(files)
    # depgraph.depgraph(defs, 1)
    doctree.doctree(defs, '/tmp/doc')

