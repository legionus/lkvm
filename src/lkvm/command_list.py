# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import argparse
import os
import os.path

import lkvm
import lkvm.config

logger = lkvm.logger


# pylint: disable-next=unused-argument
def main(cmdargs: argparse.Namespace) -> int:
    basedir = os.path.expanduser("~/vm")

    names  = ["NAME", "MODE", "PROFILE"]
    header = [ len(n) for n in names ]
    output = []

    try:
        for ent in os.scandir(basedir):
            if not ent.is_dir() or not os.path.isfile(os.path.join(ent.path, "config")):
                continue

            config = lkvm.config.read("~/vm", ent.name)

            if isinstance(config, lkvm.Error):
                logger.critical("%s", config.message)
                continue

            if ( sz := len(ent.name)) > header[0]:
                header[0] = sz
            if ( sz := len(config["vm"].get("mode", "9p"))) > header[1]:
                header[1] = sz
            if ( sz := len(ent.path)) > header[2]:
                header[2] = sz

            output.append([ent.name, config["vm"].get("mode", "9p"), ent.path])

    except FileNotFoundError:
        return lkvm.EX_SUCCESS

    fmt = "".join([ '{:<' + str(e + 1) + '}' for e in header ])

    print(fmt.format(*names))
    print("-" * (sum(header) + len(header)))

    for e in output:
        print(fmt.format(*e))

    return lkvm.EX_SUCCESS
