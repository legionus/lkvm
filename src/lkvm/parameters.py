# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os
import argparse

from typing import Dict, Any, Optional

import lkvm.qemu


class Parameter:
    def __init__(self,
                 name: str,
                 cmdline: Optional[str],
                 confname: str,
                 action: str,
                 default: Any,
                 qemu_arg: Any,
                 desc: str):
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


PARAMS = [
    Parameter(name     = 'mode',
              cmdline  = None,
              confname = 'mode',
              action   = 'store',
              default  = '9p',
              qemu_arg = None,
              desc     = 'Profile mode'),

    Parameter(name     = 'arch',
              cmdline  = 'arch',
              confname = 'arch',
              action   = 'store',
              default  = detect_arch,
              qemu_arg = None,
              desc     = 'Specifies target architecture'),

    Parameter(name     = 'machine',
              cmdline  = 'machine',
              confname = 'machine',
              action   = 'store',
              default  = 'accel=kvm:tcg',
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Specifies the emulated machine'),

    Parameter(name     = 'cpu',
              cmdline  = 'cpu',
              confname = 'cpu',
              action   = 'store',
              default  = detect_cpu,
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Specifies CPU model'),

    Parameter(name     = 'smp',
              cmdline  = 'smp',
              confname = 'smp',
              action   = 'store',
              default  = detect_cpus,
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Simulates an SMP system with n CPUs'),

    Parameter(name     = 'kvm',
              cmdline  = 'enable-kvm',
              confname = 'enable-kvm',
              action   = 'store_true',
              default  = detect_kvm,
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Enables KVM full virtualization support'),

    Parameter(name     = 'memory',
              cmdline  = 'memory',
              confname = 'memory',
              action   = 'store',
              default  = detect_memory,
              qemu_arg = lkvm.qemu.arg_memory,
              desc     = 'Specifies virtual RAM size'),

    Parameter(name     = 'console',
              cmdline  = 'console',
              confname = 'console',
              action   = 'store',
              default  = 'serial',
              qemu_arg = lkvm.qemu.arg_console,
              desc     = 'Specifies console type'),

    Parameter(name     = 'random',
              cmdline  = 'random',
              confname = 'random',
              action   = 'store',
              default  = 'none',
              qemu_arg = lkvm.qemu.arg_random,
              desc     = 'Use specified a random number generator backend'),

    Parameter(name     = 'reboot',
              cmdline  = 'reboot',
              confname = 'reboot',
              action   = 'store_true',
              default  = False,
              qemu_arg = lkvm.qemu.arg_no_simple,
              desc     = 'Exit instead of rebooting'),

    Parameter(name     = 'monitor',
              cmdline  = 'monitor',
              confname = 'monitor',
              action   = 'store',
              default  = 'qmp:unix:${profile}/socket,server,nowait',
              qemu_arg = lkvm.qemu.arg_monitor,
              desc     = 'Redirects the monitor to host device'),

    Parameter(name     = 'graphic',
              cmdline  = 'graphic',
              confname = 'graphic',
              action   = 'store_true',
              default  = False,
              qemu_arg = lkvm.qemu.arg_graphic,
              desc     = 'Disables graphical output'),

    Parameter(name     = 'network',
              cmdline  = 'network',
              confname = 'network',
              action   = 'append',
              default  = [],
              qemu_arg = lkvm.qemu.arg_network,
              desc     = 'Specifies the mode network stack'),

    Parameter(name     = 'disk',
              cmdline  = 'disk',
              confname = 'disk',
              action   = 'append',
              default  = [],
              qemu_arg = lkvm.qemu.arg_disk,
              desc     = 'Defines which disk image to use with this drive'),

    Parameter(name     = 'virtfs',
              cmdline  = 'virtfs',
              confname = 'virtfs',
              action   = 'append',
              default  = [],
              qemu_arg = lkvm.qemu.arg_virtfs,
              desc     = 'Specifies the export path for the file system device'),

    Parameter(name     = 'object',
              cmdline  = 'object',
              confname = 'object',
              action   = 'append',
              default  = [],
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Adds a new object of type typename setting properties in the order they are specified'),

    Parameter(name     = 'device',
              cmdline  = 'device',
              confname = 'device',
              action   = 'append',
              default  = [],
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Adds device driver and sets driver properties'),

    Parameter(name     = 'nfsport',
              cmdline  = 'nfsport',
              confname = 'nfsport',
              action   = 'store',
              default  = '2049',
              qemu_arg = None,
              desc     = 'Specifies port on which the NFS server will listen in case of nfs mode.'),

    Parameter(name     = 'boot',
              cmdline  = 'boot',
              confname = 'boot',
              action   = 'store',
              default  = '',
              qemu_arg = lkvm.qemu.arg_boot,
              desc     = 'Specifies boot order drives as a string of drive letters'),

    Parameter(name     = 'debugger',
              cmdline  = 'debugger',
              confname = 'debugger',
              action   = 'store',
              default  = '',
              qemu_arg = lkvm.qemu.arg_debugger,
              desc     = 'Allows to debug guest code'),

    Parameter(name     = 'kernel',
              cmdline  = 'kernel',
              confname = 'kernel',
              action   = 'store',
              default  = '',
              qemu_arg = lkvm.qemu.arg_kernel,
              desc     = 'Specifies bzImage as kernel image'),

    Parameter(name     = 'initrd',
              cmdline  = 'initrd',
              confname = 'initrd',
              action   = 'store',
              default  = '',
              qemu_arg = lkvm.qemu.arg_simple,
              desc     = 'Specifies file as initial ram disk'),

    Parameter(name     = 'cmdline',
              cmdline  = 'cmdline',
              confname = 'cmdline',
              action   = 'store',
              default  = '',
              qemu_arg = lkvm.qemu.arg_cmdline,
              desc     = 'Specifies cmdline as kernel command line'),

    Parameter(name     = 'qemu',
              cmdline  = None,
              confname = 'qemu',
              action   = 'append',
              default  = [],
              qemu_arg = lkvm.qemu.arg_unknown,
              desc     = 'Extra qemu arguments'),
]

CONFNAMES = [ p.confname for p in PARAMS ]
