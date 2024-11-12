# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import argparse
import threading

from typing import Dict, List, Any

import lkvm
import lkvm.config
import lkvm.parameters
import lkvm.qemu

if lkvm.HAVE_NFS:
    import lkvm.nfs

logger = lkvm.logger


def arguments(config: Dict[str, Any]) -> List[str] | lkvm.Error:
    retlist: List[str] = []

    for param in lkvm.parameters.PARAMS:
        if not param.confname or not param.qemu_arg:
            continue

        if args := param.qemu_arg(param.confname, config):
            retlist.extend(args)

    return retlist


def main(cmdargs: argparse.Namespace) -> int:
    profile = cmdargs.profile

    config = lkvm.config.read("~/vm", profile)

    if isinstance(config, lkvm.Error):
        logger.critical("%s", config.message)
        return lkvm.EX_FAILURE

    for p in lkvm.parameters.PARAMS:
        p.add_config(cmdargs, config["vm"])

    config = lkvm.config.expandvars(config)

    if isinstance(config, lkvm.Error):
        logger.critical("%s", config.message)
        return lkvm.EX_FAILURE

    qemu_exe = lkvm.qemu.executable(config["vm"]["arch"])

    if isinstance(qemu_exe, lkvm.Error):
        logger.critical("%s", qemu_exe.message)
        return lkvm.EX_FAILURE

    qemu_args = arguments(config["vm"])

    if isinstance(qemu_args, lkvm.Error):
        logger.critical("%s", qemu_args.message)
        return lkvm.EX_FAILURE

    if cmdargs.dry_run:
        print("Command to execute:\n")
        lkvm.qemu.dump([qemu_exe] + qemu_args)
        return lkvm.EX_SUCCESS

    if lkvm.HAVE_NFS and config["vm"]["mode"] == "nfs":
        t = threading.Thread(
                target=lkvm.nfs.thread,
                kwargs={
                    "rootfs"      : config["global"]["rootfs"].encode("utf-8"),
                    "mountpoints" : { b"/host": b"/" },
                    "nfsport"     : int(config["vm"]["nfsport"]),
                })
        t.daemon = True
        t.start()

    lkvm.exec_command([qemu_exe] + qemu_args)

    return lkvm.EX_SUCCESS
