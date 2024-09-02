# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import argparse
import os
import os.path

import lkvm

logger = lkvm.logger


# pylint: disable-next=unused-argument
def main(cmdargs: argparse.Namespace) -> int:
    basedir = os.path.expanduser("~/vm")

    names  = ["NAME", "ROOTFS"]
    header = [ len(names[0]), len(names[1]) ]
    output = []

    try:
        for ent in os.scandir(basedir):
            if not ent.is_dir() or not os.path.isfile(os.path.join(ent.path, "config")):
                continue

            if ( sz := len(ent.name)) > header[0]:
                header[0] = sz
            if ( sz := len(ent.path)) > header[1]:
                header[1] = sz

            output.append([ent.name, ent.path])

    except FileNotFoundError:
        return lkvm.EX_SUCCESS

    fmt = ' {:<' + str(header[0] + 1) + '}{:<' + str(header[1] + 1) + '}'

    print(fmt.format(*names))
    print("-" * (1 + sum(header) + len(header)))

    for e in output:
        print(fmt.format(*e))

    return lkvm.EX_SUCCESS
