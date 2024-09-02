#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os
import re
import subprocess

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py as build_py_orig


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


def find_version(source):
    version_file = read(source)
    version_match = re.search(r"^__VERSION__ = ['\"]([^'\"]*)['\"]", version_file, re.M)

    if version_match:
        return version_match.group(1)

    raise RuntimeError("Unable to find version string.")


class BuildGuestInitCommand(build_py_orig):
        def run(self):
            cc = os.getenv("CC", "gcc")
            srcdir = "src/lkvm/guest"

            subprocess.check_call([cc, "-s", "-static", "-Os", "-nostartfiles",
                                   "-o", f"{srcdir}/init", f"{srcdir}/init.c"])
            super().run()

NAME = "lkvm"

setup(
        version=find_version("src/lkvm/__init__.py"),
        url="https://github.com/legionus/lkvm.git",
        name=NAME,
        description="DESCRIPTION",
        author="Alexey Gladkov",
        author_email="legion@kernel.org",
        license="GPLv2+",
        python_requires=">=3.11",
        entry_points={"console_scripts": ["lkvm=lkvm.command:cmd"]},
        packages=["lkvm", "lkvm/guest"],
        package_dir={"": "src"},
        cmdclass={"build_py": BuildGuestInitCommand},
        include_package_data=True,
)
