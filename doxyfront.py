import os
import sys

from doxyfront import depgraph, source

if __name__ == '__main__':
    files = [f for f in os.listdir(os.getcwd()) if f.endswith('.xml')]
    defs = source.load(files)
    depgraph.depgraph(defs, sys.stdout)
