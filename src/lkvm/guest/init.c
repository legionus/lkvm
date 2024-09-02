// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

#include <sys/mount.h>
#include <sys/syscall.h>
#include <unistd.h>

static char *prog[] = {"/virt/init", NULL};

void _start(void)
{
	syscall(SYS_mount, "hostfs", "/host", "9p", MS_RDONLY, "trans=virtio,version=9p2000.L");
	syscall(SYS_execve, prog[0], prog, NULL);
	syscall(SYS_exit, 0);
}
