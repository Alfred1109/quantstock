#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

with open('requirements.txt', 'r', encoding='utf-8') as f:
    requirements = f.read().splitlines()

setup(
    name="pyramid_trading",
    version="0.5.0",
    author="Pyramid Trading Team",
    author_email="info@pyramid-trading.com",
    description="金字塔交易法量化交易系统",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/username/pyramid-trading-system",
    packages=find_packages(include=['src', 'src.*']),
    install_requires=requirements,
    python_requires='>=3.8',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    entry_points={
        'console_scripts': [
            'pyramid=main:main',
        ],
    },
    include_package_data=True,
) 