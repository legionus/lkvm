# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import logging
import os
import os.path
import re
import subprocess

from typing import Optional, Dict, Tuple, List, Union, Any
from collections.abc import Iterator

HAVE_NFS = False

try:
    import shenaniganfs # type: ignore[import-untyped]
    HAVE_NFS = True
except ImportError:
    pass

__VERSION__ = '1-dev'

EX_SUCCESS = 0 # Successful exit status.
EX_FAILURE = 1 # Failing exit status.

logger = logging.getLogger("lkvm")


class Error:
    def __init__(self, message: str):
        self.message = message


def exec_command(cmdargs: List[str]) -> int:
    ecode = 0
    try:
        res = subprocess.run(cmdargs, check=True)
        ecode = res.returncode

    except subprocess.CalledProcessError as e:
        ecode = e.returncode

    return ecode


def run_command(cmdargs: List[str], stdin: Optional[bytes] = None,
                rundir: Optional[str] = None) -> Tuple[int, bytes, bytes]:
    if rundir:
        logger.debug("changing dir to %s", rundir)
        curdir = os.getcwd()
        os.chdir(rundir)
    else:
        curdir = None

    logger.debug("running %s", cmdargs)
    try:
        sp = subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        (output, error) = sp.communicate(input=stdin)
        returncode = sp.returncode
    except FileNotFoundError:
        (returncode, output, error) = (127, b'', b'')

    if curdir:
        logger.debug("changing back into %s", curdir)
        os.chdir(curdir)

    return returncode, output, error


def setup_logger(logger: logging.Logger, level: int, fmt: str) -> logging.Logger:
    formatter = logging.Formatter(fmt=fmt, datefmt="%H:%M:%S")

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(handler)

    return logger
