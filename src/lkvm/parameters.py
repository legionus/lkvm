# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os
import argparse

from typing import Dict, Any, Optional

import lkvm.qemu


class Parameter:
    def __init__(self, name: str, cmdline: Optional[str],
                 confname: str, action: str,
                 default: Any, qemu_arg: Any, desc: str):
        self.name     = name
        self.cmdline  = cmdline
        self.confname = confname
        self.action   = action
        self.qemu_arg = qemu_arg
        self.desc     = desc

        if callable(default):
            self.default = default.__call__()
        else:
            self.default = default


    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        if not self.cmdline:
            return

        args = [ f"--{self.cmdline}" ]

        kwargs: Dict[str, Any] = {
            'dest'    : f"qemu_{self.name}",
            'action'  : self.action,
            'help'    : self.desc,
            'default' : None,
        }

        if self.default:
            kwargs['help'] += f' (default: {self.default})'
        kwargs['help'] += '.'

        if self.action not in ('store_true', 'store_false'):
            kwargs["metavar"] = self.name.upper()

        parser.add_argument(*args, **kwargs)


    def add_config(self, args: argparse.Namespace, config: Dict[str, Any]) -> None:
        if not self.confname:
            return

        if self.confname not in config:
            config[self.confname] = self.default

        try:
            value = getattr(args, f"qemu_{self.name}")

            if value is not None:
                config[self.confname] = value

        except AttributeError:
            pass


def detect_arch() -> str:
    return os.uname().machine


def detect_cpu() -> str:
    if detect_arch() in ('x86_64'):
        return 'kvm64'
    return 'kvm32'


def detect_cpus() -> int:
    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except ModuleNotFoundError:
        pass
    return 1


def detect_memory() -> str:
    cpus = detect_cpus()
    num = 64 * (cpus + 3)
    return f"{num}M"


def detect_kvm() -> bool:
    return os.access("/dev/kvm", os.R_OK)


def set_monitor() -> str:
    return 'qmp:unix:${profile}/socket,server,nowait'


PARAMS = [
    Parameter('mode'    , None         , 'mode'       , 'store'      , '9p'            , None                    , 'Profile mode')                                                                          ,
    Parameter('arch'    , 'arch'       , 'arch'       , 'store'      , detect_arch     , None                    , 'Specifies target architecture')                                                         ,
    Parameter('machine' , 'machine'    , 'machine'    , 'store'      , 'accel=kvm:tcg' , lkvm.qemu.arg_simple    , 'Specifies the emulated machine')                                                        ,
    Parameter('cpu'     , 'cpu'        , 'cpu'        , 'store'      , detect_cpu      , lkvm.qemu.arg_simple    , 'Specifies CPU model')                                                                   ,
    Parameter('smp'     , 'smp'        , 'smp'        , 'store'      , detect_cpus     , lkvm.qemu.arg_simple    , 'Simulates an SMP system with n CPUs')                                                   ,
    Parameter('kvm'     , 'enable-kvm' , 'enable-kvm' , 'store_true' , detect_kvm      , lkvm.qemu.arg_simple    , 'Enables KVM full virtualization support')                                               ,
    Parameter('memory'  , 'memory'     , 'memory'     , 'store'      , detect_memory   , lkvm.qemu.arg_memory    , 'Specifies virtual RAM size')                                                            ,
    Parameter('console' , 'console'    , 'console'    , 'store'      , 'serial'        , lkvm.qemu.arg_console   , 'Specifies console type')                                                                ,
    Parameter('random'  , 'random'     , 'random'     , 'store'      , 'none'          , lkvm.qemu.arg_random    , 'Use specified a random number generator backend')                                       ,
    Parameter('reboot'  , 'reboot'     , 'reboot'     , 'store_true' , False           , lkvm.qemu.arg_no_simple , 'Exit instead of rebooting')                                                             ,
    Parameter('monitor' , 'monitor'    , 'monitor'    , 'store'      , set_monitor     , lkvm.qemu.arg_monitor   , 'Redirects the monitor to host device')                                                  ,
    Parameter('graphic' , 'graphic'    , 'graphic'    , 'store_true' , False           , lkvm.qemu.arg_graphic   , 'Disables graphical output')                                                             ,
    Parameter('network' , 'network'    , 'network'    , 'append'     , []              , lkvm.qemu.arg_network   , 'Specifies the mode network stack')                                                      ,
    Parameter('disk'    , 'disk'       , 'disk'       , 'append'     , []              , lkvm.qemu.arg_disk      , 'Defines which disk image to use with this drive')                                       ,
    Parameter('virtfs'  , 'virtfs'     , 'virtfs'     , 'append'     , []              , lkvm.qemu.arg_virtfs    , 'Specifies the export path for the file system device')                                  ,
    Parameter('object'  , 'object'     , 'object'     , 'append'     , []              , lkvm.qemu.arg_simple    , 'Adds a new object of type typename setting properties in the order they are specified') ,
    Parameter('device'  , 'device'     , 'device'     , 'append'     , []              , lkvm.qemu.arg_simple    , 'Adds device driver and sets driver properties')                                         ,
    Parameter('boot'    , 'boot'       , 'boot'       , 'store'      , ''              , lkvm.qemu.arg_boot      , 'Specifies boot order drives as a string of drive letters')                              ,
    Parameter('kernel'  , 'kernel'     , 'kernel'     , 'store'      , ''              , lkvm.qemu.arg_kernel    , 'Specifies bzImage as kernel image')                                                     ,
    Parameter('initrd'  , 'initrd'     , 'initrd'     , 'store'      , ''              , lkvm.qemu.arg_simple    , 'Specifies file as initial ram disk')                                                    ,
    Parameter('cmdline' , 'cmdline'    , 'cmdline'    , 'store'      , ''              , lkvm.qemu.arg_cmdline   , 'Specifies cmdline as kernel command line')                                              ,
]

CONFNAMES = [ p.confname for p in PARAMS ]
