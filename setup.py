#!/usr/bin/env python
#
#   Copyright 2015 Linux2Go
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
from setuptools import setup, find_packages

def load_requirements(fname):
    with open('requirements.txt', 'r') as fp:
        requirements = [x.strip() for x in fp]

requirements = load_requirements('requirements.txt')
test_requirements = load_requirements('test-requirements.txt')

setup(
    name='schmenkins',
    description='Jenkins Schmenkins',
    author='Soren Hansen',
    author_email='soren@linux2go.dk',
    url='http://schmenkins.net/',
    version='0.8',
    packages=find_packages(),
    install_requires=requirements,
    tests_require=test_requirements,
    entry_points={'console_scripts': ['schmenkins=schmenkins:main']},
    include_package_data=True
)

