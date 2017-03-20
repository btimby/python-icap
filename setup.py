"""Package setup."""
from setuptools import find_packages
from setuptools import setup

with open('requirements.txt') as f:
    required = f.read().splitlines()

required = [r for r in required if not r.startswith('git')]

setup(
    name='python-icap',
    version="0.1",
    description='Python asyncio ICAP server.',
    author='Nathan Hoad',
    author_email='nhoad@nhoad.com',  # Dunno his email...
    url='https://github.com/nathan-hoad/python-icap',
    packages=find_packages(),
    install_requires=required,
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
)
