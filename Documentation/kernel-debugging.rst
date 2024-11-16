.. highlight:: none

Debugging
=========

This document explains how to debug a guests' kernel.

Using kgdb
----------

The kgdb requires support to be enabled in the kernel.

  CONFIG_KGDB=y
  CONFIG_KGDB_SERIAL_CONSOLE=y
  CONFIG_DEBUG_INFO=y

1. Run the guest:
	lkvm run <profile> --debug kgdb

2. Run GDB on the host:
	gdb [vmlinux]

3. Connect to the guest (from within GDB):
	target remote /home/user/vm/<profile>/gdb-socket

4. Start debugging! (enter 'continue' to continue boot).

For more info see :ref:`https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/Documentation/dev-tools/kgdb.rst`


Using gdb
---------

1. Run the guest:
	lkvm run <profile> --debug gdb

The rest of the steps will be the same as for kgdb.

For more info see :ref:`https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/Documentation/dev-tools/gdb-kernel-debugging.rst`


Using crash
-----------

It is possible to analyze the guest kernel using the crash utility.

1. Run the guest:
	lkvm run <profile>

2. Dump guest' memory into the file:
	lkvm vm <profile> --dump-memory /tmp/vmcore.img

3. Run crash:
	crash /path/to/vmlinux /tmp/vmcore.img

4. Profit!

For more :ref:`https://crash-utility.github.io/crash_whitepaper.html`
