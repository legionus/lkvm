# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

#!/usr/bin/env python3
import os
import sys
import socket
import termios
import tty
import time
import selectors

import lkvm
import lkvm.qemu

logger = lkvm.logger


def main() -> int:
    if not hasattr(socket, "AF_VSOCK"):
        logger.critical("AF_VSOCK is not supported")
        return lkvm.EX_FAILURE

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()

    old = termios.tcgetattr(stdin_fd)
    sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)

    timeout = 0
    while True:
        time.sleep(1)
        try:
            sock.connect((lkvm.qemu.vsock_cid, lkvm.qemu.vsock_port))
            break
        except OSError as e:
            if timeout > 5:
                logger.critical("connect failed: %s (after %d seconds)", e, timeout)
        timeout += 1

    sock.setblocking(False)
    os.set_blocking(stdin_fd, False)

    sel = selectors.DefaultSelector()
    sel.register(sock, selectors.EVENT_READ)
    sel.register(stdin_fd, selectors.EVENT_READ)

    finish = False

    try:
        tty.setraw(stdin_fd)

        while not finish:
            for key, _ in sel.select(timeout=0.2):
                if key.fileobj == stdin_fd:
                    while True:
                        try:
                            data = os.read(stdin_fd, 4096)
                            break
                        except BlockingIOError:
                            pass
                    if not data:
                        finish = True
                        break
                    sock.sendall(data)
                else:
                    data = sock.recv(4096)
                    if not data:
                        finish = True
                        break
                    os.write(stdout_fd, data)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old)
        sel.close()
        sock.close()
        os.write(stdout_fd, b"\n")

    lkvm.qemu.kill()
    return 0
