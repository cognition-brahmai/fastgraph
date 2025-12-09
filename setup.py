"""
Setup script for FastGraph package.

This setup.py is provided for legacy compatibility.
For modern usage, pyproject.toml is the preferred configuration.
"""

from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
def read_requirements(filename):
    """Read requirements from file."""
    with open(os.path.join(this_directory, filename), 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#') and not line.startswith('-r')]

try:
    install_requires = read_requirements('requirements.txt')
except FileNotFoundError:
    install_requires = [
        'msgpack>=1.0.0',
        'click>=8.0.0', 
        'pyyaml>=6.0',
        'typing-extensions>=4.0.0'
    ]

try:
    extras_require = {
        'dev': read_requirements('requirements-dev.txt'),
        'docs': [
            'sphinx>=5.0.0',
            'sphinx-rtd-theme>=1.0.0',
            'myst-parser>=0.18.0'
        ],
        'performance': [
            'psutil>=5.9.0',
            'memory-profiler>=0.60.0'
        ]
    }
    extras_require['all'] = [
        dep for deps in extras_require.values() for dep in deps
    ]
except FileNotFoundError:
    extras_require = {
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=4.0.0',
            'black>=22.0.0',
            'flake8>=5.0.0',
            'mypy>=1.0.0'
        ],
        'docs': [
            'sphinx>=5.0.0',
            'sphinx-rtd-theme>=1.0.0',
            'myst-parser>=0.18.0'
        ],
        'performance': [
            'psutil>=5.9.0',
            'memory-profiler>=0.60.0'
        ]
    }

setup(
    name='fastgraph',
    version='2.0.0',
    description='High-performance in-memory graph database',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='BRAHMAI',
    author_email='hello@brahmai.in',
    maintainer='BRAHMAI',
    maintainer_email='hello@brahmai.in',
    url='https://github.com/cognition-brahmai/fastgraph',
    project_urls={
        'Source': 'https://github.com/cognition-brahmai/fastgraph',
        'Tracker': 'https://github.com/cognition-brahmai/fastgraph/issues',
    },
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'fastgraph': ['*.yaml', '*.yml', '*.json'],
    },
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'fastgraph=fastgraph.cli.main:main',
        ],
    },
    keywords=[
        'graph', 'database', 'graph-database', 'in-memory', 
        'high-performance', 'network-analysis', 'graph-algorithms'
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Database',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    zip_safe=False,
)