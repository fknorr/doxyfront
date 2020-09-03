import os
from . import source, doctree
from argparse import ArgumentParser

parser = ArgumentParser('doxyfront')
parser.add_argument('xml-dir')
parser.add_argument('output-dir')
args = parser.parse_args()

xml_dir = args.__dict__['xml-dir']
output_dir = args.__dict__['output-dir']
files = [os.path.join(xml_dir, f) for f in os.listdir(xml_dir) if f.endswith('.xml')]
defs = source.load(files)
os.makedirs(output_dir, exist_ok=True)
doctree.doctree(defs, output_dir)
