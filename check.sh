#!/bin/sh -fux
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

REAL_SCRIPT=$(realpath -e ${BASH_SOURCE[0]})
SCRIPT_TOP="${SCRIPT_TOP:-$(dirname ${REAL_SCRIPT})}"

export PYTHONPATH="${SCRIPT_TOP}/src:${SCRIPT_TOP}/src/ShenanigaNFS"

find src/lkvm -type f -name '*.py' -a \! -name '*_tab.py' |
	xargs -r pylint --disable=R --disable=W0603,W0621,W0718 --disable=C0103,C0114,C0115,C0116,C0301,C0415,C3001

find src/lkvm -type f -name '*.py' -a \! -name '*_tab.py' |
	xargs -r mypy --strict
