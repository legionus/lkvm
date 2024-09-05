# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import glob
import os
import re

from typing import Dict, List, Any

import lkvm
import lkvm.config
import lkvm.kernel

logger = lkvm.logger


def executable(arch: str) -> str | lkvm.Error:
    exe = f"qemu-system-{arch}"
    ecode, _, _ = lkvm.run_command([exe, "-version"])

    if ecode != 0:
        return lkvm.Error(f"qemu not found for archicture: {arch}")

    return exe

def arg_simple(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if isinstance(value, list):
        ret = []
        for arg in value:
            ret.extend([f"-{key}", str(arg)])
        return ret

    if isinstance(value, bool):
        ret = []
        if value:
            ret = [f"-{key}"]
        return ret

    if value:
        return [f"-{key}", str(value)]

    return []

def arg_no_simple(key: str, config: Dict[str, Any]) -> List[str]:
    if not config[key]:
        return [f"-no-{key}"]
    return []

def arg_boot(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not value:
        return []
    if "," in value:
        return ["-boot", value]
    return ["-boot", f"order={value}"]

def arg_virtfs(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    ret: List[str] = []

    if not isinstance(value, list):
        return ret

    for i, virtfs in enumerate(value):
        if "," in virtfs:
            ret.extend(["-virtfs", virtfs])
        elif ":" in virtfs:
            path, tag = virtfs.split(":", 1)
            ret.extend(["-virtfs", f"local,id=virtfs-{i},path={path},security_model=none,mount_tag={tag},multidevs=remap"])

    return ret

def arg_disk(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not isinstance(value, list):
        return []

    ret: List[str] = []

    for disk in value:
        if "," in disk:
            ret.extend(["-drive", disk])
        else:
            ret.extend(["-drive", f"file={disk},if=virtio,cache=writeback"])

    return ret

def arg_random(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if value == "none":
        return []

    # random=virtio,/dev/random
    if value.startswith("virtio,/"):
        data = value[len("virtio,"):]
        return [
            "-object", f"rng-random,filename={data},id=rng0",
            "-device", "virtio-rng-pci,rng=rng0",
        ]

    # random=egd,host=10.66.4.212,port=1024
    if value.startswith("egd,"):
        data = value[len("egd,"):]
        return [
			"-chardev", f"socket,id=chr0,${data}",
            "-object", "rng-egd,chardev=chr0,id=rng0",
			"=device", "virtio-rng-pci,rng=rng0",
        ]

    logger.critical("BUG: Unknown random type: %s", value)
    return []

def arg_memory(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if value:
        return ["-m", str(value)]
    return []

def arg_graphic(key: str, config: Dict[str, Any]) -> List[str]:
    if not config[key]:
        return ["-nographic"]
    return []

def arg_monitor(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not value:
        return []

    if value == "none":
        return ["-monitor", "none"]

    if value.startswith("qmp:"):
        return ["-qmp", value[len("qmp:"):]]

    if value.startswith("monitor:"):
        return ["-monitor", value[len("monitor:"):]]

    return []

def arg_console(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not value or value == "none":
        return []

    ret: List[str] = []

    if value == "serial":
        (columns, lines) = os.get_terminal_size()

        lkvm.kernel.CMDLINE["winsize"] = f"{lines}x{columns}"
        lkvm.kernel.CMDLINE["console"] = "ttyS0"

        ret.extend(["-serial", "chardev:stdio"])

    elif value == "virtio":
        lkvm.kernel.CMDLINE["console"] = "hvc0"

        config["graphic"] = True

        ret.extend([
            "-display", "none",
            "-device", "virtio-serial",
            "-device", "virtconsole,chardev=stdio",
        ])

    else:
        logger.critical("BUG: Unknown console type: %s", value)
        return []

    ret.extend([
        "-chardev", "stdio,mux=on,id=stdio,signal=off",
        "-mon",     "chardev=stdio,mode=readline",
    ])

    return ret

def arg_network(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not value or not isinstance(value, list):
        return []

    ret: List[str] = []

    for v in value:
        if v == "none":
            ret.extend(["-net", "none"])

        elif v == "user" or v.startswith("user,"):
            # user,model=virtio-net-pci
            data = v[len("user"):]
            ret.extend(["-nic", f"user{data}"])

        elif v.startswith("netdev,"):
            data = v[len("netdev,"):]
            ret.extend(["-netdev", data])

        else:
            logger.critical("BUG: Unknown network type: %s", v)
            return []

    return ret

def arg_kernel(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not value:
        return []

    if value.startswith("find,"):
        path = value[len("find,"):]

        res = []

        for img in glob.glob(f'{path}/arch/*/boot/*Image'):
            statinfo = os.stat(img)
            res.append((statinfo.st_mtime, img))

        if len(res) > 0:
            sorted(res, key=lambda x: x[0], reverse=True)
            value = res[0][1]

    return ["-kernel", str(value)]

def arg_cmdline(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if value:
        for param in value.split(" "):
            if m := re.match(r"^\s*(?P<name>[^=]+)\s*=\s*(?P<value>.*)\s*$", param):
                lkvm.kernel.CMDLINE[m.group("name")] = m.group("value")

    return ["-append", lkvm.kernel.CMDLINE.join()]

def dump(a: List[str]) -> None:
    is_option = False
    prev_is_option = False

    for v in a:
        is_option = v.startswith("-")

        if is_option:
            print(("\\\n" if prev_is_option else ""), "\t", v, " ", sep='', end='')
        else:
            print("'", v, "' \\\n", sep='', end='')

        prev_is_option = is_option

    if is_option:
        print(" \\\n", sep='', end='')

    print("\t#")
