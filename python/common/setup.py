# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.
from setuptools import setup

setup(
    name="thief_common",
    version="0.0.0a1",  # Alpha Release
    description="Common functions for thief device and service apps",
    license="MIT License",
    url="https://github.com/Azure/iot-sdk-longhaul",
    author="Microsoft Corporation",
    author_email="opensource@microsoft.com",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT Software License",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    install_requires=[],
    python_requires=">=3.6, <4",
)