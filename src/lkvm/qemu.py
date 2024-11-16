# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os
import re
import sys

from typing import Dict, List, Any

import lkvm
import lkvm.config
import lkvm.kernel

logger = lkvm.logger
serial = 0


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
			"-device", "virtio-rng-pci,rng=rng0",
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
    global serial

    value = config[key]

    if not value or value == "none":
        return []

    ret: List[str] = []

    if value == "serial":
        (columns, lines) = os.get_terminal_size()

        lkvm.kernel.CMDLINE["winsize"] = f"{lines}x{columns}"
        lkvm.kernel.CMDLINE["console"] = f"ttyS{serial}"
        serial += 1

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

def arg_debugger(key: str, config: Dict[str, Any]) -> List[str]:
    global serial

    ret: List[str] = []

    value = config[key]

    if not value:
        return ret

    socket = '${profile}/gdb-socket'

    if m := re.match(r".*,socket=(?P<socket>[^,]+)", value):
        socket = m.group("socket")

    if value == "none":
        return ret

    elif value.startswith("kgdb"):
        ret.extend([
            "-chardev", f"socket,id=kgdb0,path={socket},server=on,wait=off",
            "-device", "pci-serial,id=serial0,chardev=kgdb0"
        ])

        lkvm.kernel.CMDLINE["kgdboc"] = f"ttyS{serial}"
        lkvm.kernel.CMDLINE["kgdbwait"] = True
        serial += 1

    elif value.startswith("gdb"):
        ret.extend([
            "-chardev", f"socket,id=gdb0,path={socket},server=on,wait=off",
            "-gdb", "chardev:gdb0", "-S",
        ])

    else:
        logger.critical("Unknown debugger type: %s (gdb or kgdb expected)", value)
        sys.exit(lkvm.EX_FAILURE)

    #
    # From Documentation/dev-tools/kgdb.rst
    #
    # If the architecture that you are using enable KASLR by default, you should
    # consider turning it off. KASLR randomizes the virtual address where the
    # kernel image is mapped and confuse gdb which resolve kernel symbol address
    # from symbol table of vmlinux.
    #
    lkvm.kernel.CMDLINE["nokaslr"] = True

    return ret

def arg_kernel(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if not value:
        return []

    if value == "find" or value.startswith("find,"):
        if value.startswith("find,"):
            path = value[len("find,"):]
        else:
            path = os.getcwd()

        if img := lkvm.kernel.find_image(path, os.environ):
            value = img
        else:
            logger.critical("Unable to find kernel image in path `%s'", path)
            return []

    return ["-kernel", str(value)]


def arg_cmdline(key: str, config: Dict[str, Any]) -> List[str]:
    value = config[key]

    if value:
        for param in value.split(" "):
            if m := re.match(r"^(?P<name>[^=]+)=(?P<value>.*)", param):
                if m.group("value"):
                    lkvm.kernel.CMDLINE[m.group("name")] = m.group("value")
                else:
                    lkvm.kernel.CMDLINE[m.group("name")] = None
            else:
                lkvm.kernel.CMDLINE[param] = True

    required_params: Dict[str, Any] = {}
    optional_params: Dict[str, Any] = {}

    if config["mode"] == "nfs":
        required_params["init"]        = "/virt/init"
        required_params["root"]        = "/dev/nfs"
        required_params["nfsroot"]     = "/,tcp,port=${nfsport},mountport=${nfsport}"
        required_params["nfsrootdebug"]= True
        required_params["earlyprintk"] = "serial"
        required_params["ip"]          = "dhcp"
        optional_params["rw"]          = True


    if config["mode"] == "9p":
        required_params["init"]        = "/init"
        required_params["rootflags"]   = "trans=virtio,version=9p2000.L"
        required_params["rootfstype"]  = "9p"
        required_params["earlyprintk"] = "serial"
        optional_params["rw"]          = True
        optional_params["ip"]          = "dhcp"

    for k, v in required_params.items():
        lkvm.kernel.CMDLINE[k] = v

    for k, v in optional_params.items():
        if k not in lkvm.kernel.CMDLINE:
            lkvm.kernel.CMDLINE[k] = v

    # pylint: disable-next=consider-using-dict-items
    for k in lkvm.kernel.CMDLINE.keys():
        v = lkvm.kernel.CMDLINE[k]

        if isinstance(v, str):
            lkvm.kernel.CMDLINE[k] = lkvm.config.expandvars_string(config, v)

    if len(lkvm.kernel.CMDLINE) > 0:
        return ["-append", lkvm.kernel.CMDLINE.join()]

    return []

def arg_unknown(key: str, config: Dict[str, Any]) -> List[str]:
    ret: List[str] = []
    value = config[key]

    if isinstance(value, list):
        for v in value:
            ret.extend(v.split())

    return ret


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
