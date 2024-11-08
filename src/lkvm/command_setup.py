# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os
import os.path
import argparse
import importlib.resources
import shutil

from typing import List

import lkvm
import lkvm.config
import lkvm.parameters
import lkvm.guest

logger = lkvm.logger


def copy_resource(name: str, filename: str, mode: int) -> None:
    with importlib.resources.open_binary(lkvm.guest, name) as src:
        with open(filename, "w+b") as dst:
            shutil.copyfileobj(src, dst)
        os.chmod(filename, mode)


def make_symlink(src: str, dst: str) -> None:
    if not os.path.lexists(dst):
        os.symlink(src, dst)


def write_file(filename: str, data: List[str]) -> None:
    with open(filename, "w", encoding="utf-8") as fd:
        for line in data:
            print(line, file=fd)


def setup_rootfs(rootfs: str, confdata: List[str]) -> None:
    for path in ["dev", "etc", "host", "proc", "sys", "tmp", "var/lib", "virt/home"]:
        os.makedirs(os.path.join(rootfs, path), mode=0o755, exist_ok=True)

    for path in ["bin", "home", "lib", "lib64", "sbin", "usr", "etc/ld.so.conf"]:
        make_symlink(os.path.join("/host", path), os.path.join(rootfs, path))

    make_symlink("../proc/self/mounts", os.path.join(rootfs, "etc/mtab"))

    copy_resource("init",    os.path.join(rootfs, "init"),      mode=0o755)
    copy_resource("init.sh", os.path.join(rootfs, "virt/init"), mode=0o755)

    write_file(os.path.join(rootfs, "etc/passwd"), ["root:x:0:0:root:/virt/home:/bin/bash"])
    write_file(os.path.join(rootfs, "etc/group"),  ["root:x:0:"])

    confdata.extend([
        "\tvirtfs = ${rootfs}:/dev/root",
        "\tvirtfs = /:hostfs",
    ])


def main(cmdargs: argparse.Namespace) -> int:
    profile = cmdargs.profile

    config = lkvm.config.read("~/vm", profile)

    if isinstance(config, lkvm.Error):
        logger.critical("%s", config.message)
        return lkvm.EX_FAILURE

    for p in lkvm.parameters.PARAMS:
        p.add_config(cmdargs, config["vm"])

    config["vm"]["mode"] = cmdargs.mode

    data = [
        "[vm]",
    ]

    for k, v in config["vm"].items():
        if isinstance(v, list):
            for e in v:
                data.append(f"\t{k} = {e}")
        elif isinstance(v, (bool, str)):
            if v:
                data.append(f"\t{k} = {v}")

    if cmdargs.mode == "9p":
        setup_rootfs(config["global"]["rootfs"], data)
        data.append("\t# kernel = /path/to/linux/bzImage")

    if cmdargs.mode == "disk":
        data.append("\t# disk = /path/to/disk.qcow2")

    os.makedirs(config["global"]["profile"], mode=0o755, exist_ok=True)
    write_file(config["global"]["config"], data)

    if cmdargs.mode == "9p":
        logger.warning("for 9p mode it is necessary to specify a kernel to run.")
    else:
        logger.warning("for disk mode it is necessary to specify a disks to run.")

    return lkvm.EX_SUCCESS
