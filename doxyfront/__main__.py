from . import source

files = [f for f in os.listdir(os.getcwd()) if f.endswith('.xml')]
defs = source.load(files)
