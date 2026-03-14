"""
Setup script for WeeViewer
"""

from setuptools import setup, find_packages
import os

# Read README for long description
def read_file(filename):
    """Read file content."""
    with open(os.path.join(os.path.dirname(__file__), filename), encoding='utf-8') as f:
        return f.read()

setup(
    name='weeviewer',
    version='1.0.0',
    description='WeeViewer - A lightweight JSON/XML data viewer tool',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    author='WeeViewer Contributors',
    author_email='',
    url='https://github.com/yourusername/weeviewer',
    license='MIT',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    python_requires='>=3.13',
    install_requires=[
        'wxPython>=4.2.0',
        'lxml>=4.9.0',
        'pyperclip>=1.8.0',
        'reportlab>=3.6.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'mypy>=1.0.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'weeviewer=weeviewer.main:main',
        ],
    },
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.13',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ],
    keywords='json xml viewer data structure tree',
)