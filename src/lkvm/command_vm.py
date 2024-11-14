# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import argparse
import os
import os.path
import socket
import json

from typing import Dict, List, Any

import lkvm
import lkvm.config
import lkvm.qemu

logger = lkvm.logger


def qmp_send(sock: socket.socket, message: str) -> Dict[str, Any]:
    if message:
        logger.debug(">>> %s", message)
        sock.sendall(message.encode())

    res = {}

    while 'QMP' not in res and 'return' not in res and 'error' not in res:
        data: List[bytes] = []

        while data[-2:] != [b'\r', b'\n']:
            data.append(sock.recv(1))

        if not data:
            break

        res = json.loads(b''.join(data))
        logger.debug("<<< %s", res)

    if 'error' in res:
        if 'desc' in res['error']:
            logger.critical(res['error']['desc'])
        return {}

    return res


# pylint: disable-next=unused-argument
def main(cmdargs: argparse.Namespace) -> int:
    profile = cmdargs.profile

    config = lkvm.config.read("~/vm", profile)

    if isinstance(config, lkvm.Error):
        logger.critical("%s", config.message)
        return lkvm.EX_FAILURE

    qmp_socket = os.path.join(config["global"]["profile"], "socket")

    if not os.path.exists(qmp_socket):
        logger.critical("qmp socket does not exist. VM is running?")
        return lkvm.EX_FAILURE

    try:
        sock = None

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(qmp_socket)

        #
        # https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html
        #
        if not qmp_send(sock, '') or \
           not qmp_send(sock, '{"execute":"qmp_capabilities"}'):
            return lkvm.EX_FAILURE

        if cmdargs.vm_state == "quit":
            if not qmp_send(sock, '{"execute":"quit"}'):
                return lkvm.EX_FAILURE

        elif cmdargs.vm_state == "stop":
            if not qmp_send(sock, '{"execute":"stop"}'):
                return lkvm.EX_FAILURE

        elif cmdargs.vm_state == "continue":
            if not qmp_send(sock, '{"execute":"cont"}'):
                return lkvm.EX_FAILURE

        if cmdargs.dump_memory:
            cmd: Dict[str, Any] = {
                "execute": "dump-guest-memory",
                "arguments": {
                    "paging": False,
                    "protocol": f"file:{cmdargs.dump_memory}",
                },
            }
            if not qmp_send(sock, json.dumps(cmd)):
                return lkvm.EX_FAILURE
    finally:
        if sock is not None:
            sock.close()

    return lkvm.EX_SUCCESS
