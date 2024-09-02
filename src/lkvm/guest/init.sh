#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

if [ -z "${__SETSID-}" ]; then
	export __SETSID=1
	exec setsid -c "$0"
	exit 1
fi

set_env()
{
	export "PATH=/sbin:/usr/sbin:/usr/local/sbin:/bin:/usr/bin:/usr/local/bin:/virt/bin"
	export "TERM=linux"
	export "HOME=/virt/home"
	export "PS1=[shell \\W]# "
}

set_ttysz()
{
	local stty='' esc='' cols='' rows=''

	stty="$(type -P stty)" ||
		return 0

	if [ -z "$cols" ] || [ -z "$rows" ]; then
		#
		# https://en.m.wikipedia.org/wiki/ANSI_escape_code#CSI_(Control_Sequence_Introducer)_sequences
		#
		# "\033[s"          -- save current cursor position.
		# "\033[9999;9999H" -- cursor should move as far as it can.
		# "\033[6n"         -- ask for cursor position
		# "\033[u"          -- restore saved cursor position.
		# "R"               -- terminates the response
		#
		echo -ne "\033[s\033[9999;9999H\033[6n\033[u"
		IFS=';[' read -s -t2 -dR esc rows cols
	fi

	if [ -z "$cols" ] || [ -z "$rows" ]; then
		if esc="$(grep -m1 -o 'winsize=[^[:space:]]\+' /proc/cmdline 2>/dev/null)"; then
			esc="${esc#winsize=}"
			rows="${esc%x*}"
			cols="${esc#*x}"
		fi
	fi

	[ -z "$cols" ] || [ -z "$rows" ] ||
		"$stty" rows "$rows" cols "$cols"
}

do_mount()
{
	if [ -d "$1" ]; then
		set -- "$@" "$1"
		shift
		mount "$@"
	fi
}


do_mount /proc -n -t proc     proc
do_mount /sys  -n -t sysfs    sysfs
do_mount /tmp  -n -t tmpfs    tmpfs
do_mount /dev  -n -t devtmpfs devtmpfs

mkdir -p -m755 /dev/pts

do_mount /dev/pts -n -t devpts devpts

set_ttysz
set_env

prog="/virt/sandbox.sh"
[ -x "$prog" ] || prog="$BASH"

"$prog"

if [ -w /proc/sysrq-trigger ]; then
	#
	# Documentation/admin-guide/sysrq.rst
	#
	for n in e i s b; do
		echo "$n" > /proc/sysrq-trigger
	done
fi

exit 0
