# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import argparse
import sys
import logging

import lkvm
import lkvm.parameters

logger = lkvm.logger


def cmd_setup(cmdargs: argparse.Namespace) -> int:
    import lkvm.command_setup
    return lkvm.command_setup.main(cmdargs)


def cmd_list(cmdargs: argparse.Namespace) -> int:
    import lkvm.command_list
    return lkvm.command_list.main(cmdargs)


def cmd_run(cmdargs: argparse.Namespace) -> int:
    import lkvm.command_run
    return lkvm.command_run.main(cmdargs)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-v", "--verbose",
                        dest="verbose", action='count', default=0,
                        help="print a message for each action.")
    parser.add_argument('-q', '--quiet',
                        dest="quiet", action='store_true', default=False,
                        help='output critical information only.')
    parser.add_argument("-V", "--version",
                        action='version',
                        help="show program's version number and exit.",
                        version=lkvm.__VERSION__)
    parser.add_argument("-h", "--help",
                        action='help',
                        help="show this help message and exit.")


def add_qemu_arguments(parser: argparse.ArgumentParser) -> None:
    for p in lkvm.parameters.PARAMS:
        p.add_arguments(parser)


def setup_parser() -> argparse.ArgumentParser:
    epilog = "Report bugs to authors."

    description = """\
The program to run virtual machines and run programs in their virtual environment.
"""
    parser = argparse.ArgumentParser(
            prog="lkvm",
            formatter_class=argparse.RawTextHelpFormatter,
            description=description,
            epilog=epilog,
            add_help=False,
            allow_abbrev=True)

    add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="subcmd", help="")

    # command: setup
    sp0_description = """\
Setup a new virtual machine. This creates a new rootfs in the .vm folder
of your home directory.

"""
    sp0 = subparsers.add_parser("setup",
                                description=sp0_description, help=sp0_description,
                                epilog=epilog, add_help=False)
    sp0.set_defaults(func=cmd_setup)
    add_common_arguments(sp0)

    mode_choices = ["9p", "disk"]

    if lkvm.HAVE_NFS:
        mode_choices.append("nfs")

    sp0.add_argument("-m", "--mode",
                     dest="mode", action="store", default="9p", choices=mode_choices,
                     help="profile mode (default: %(default)s).")
    sp0.add_argument("profile", help="name of profile")

    # command: list
    sp1_description = """\
Print a list of running instances on the host. This is restricted to instances
started by the current user, as it looks in the .vm folder in your home
directory.

"""
    sp1 = subparsers.add_parser("list",
                                description=sp1_description, help=sp1_description,
                                epilog=epilog, add_help=False)
    sp1.set_defaults(func=cmd_list)
    add_common_arguments(sp1)

    # command: run
    sp2_description = """\
Starts a virtual machine according to specified profile.

"""
    sp2 = subparsers.add_parser("run",
                                description=sp2_description, help=sp2_description,
                                epilog=epilog, add_help=False)
    sp2.set_defaults(func=cmd_run)
    add_common_arguments(sp2)
    sp2.add_argument('-n', '--dry-run',
                     dest="dry_run", action='store_true', default=False,
                     help='show what should be launched.')
    add_qemu_arguments(sp2)
    sp2.add_argument("profile", help="name of profile")

    return parser


def setup_logger(cmdargs: argparse.Namespace) -> None:
    match cmdargs.verbose:
        case 0:
            level = logging.WARNING
        case 1:
            level = logging.INFO
        case _:
            level = logging.DEBUG

    if cmdargs.quiet:
        level = logging.CRITICAL

    lkvm.setup_logger(logger, level=level, fmt="[%(asctime)s] %(message)s")


def cmd() -> int:
    parser = setup_parser()
    cmdargs = parser.parse_args()

    setup_logger(cmdargs)

    if 'func' not in cmdargs:
        parser.print_help()
        return lkvm.EX_FAILURE

    ret: int = cmdargs.func(cmdargs)

    return ret


if __name__ == '__main__':
    sys.exit(cmd())
