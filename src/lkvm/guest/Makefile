# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

all: init

init: init.c
	$(CC) -Wall -Wextra -pedantic -Os -s -static -nostartfiles -o $@ $<

init: Makefile

clean:
	rm -f ./init
