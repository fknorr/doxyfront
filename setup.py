import os
from setuptools import setup


def read_file(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='doxyfront',
    version='0.1.0',
    author='Fabian Knorr',
    author_email='git@fabian-knorr.info',
    description='Create C++-friendly web pages from Doxygen XML',
    long_description=read_file('README.md'),
    license='MIT',
    keywords='documentation generator',
    url='https://github.com/fknorr/doxyfront',
    packages=['doxyfront'],
    install_requires=['jinja2'],
    entry_points={
        'console_scripts': [
            'doxyfront=doxyfront',
        ]
    }
)
