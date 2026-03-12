================
vsock-console
================

Overview
========

``vsock-console`` is a lightweight mechanism to obtain an interactive
console in a QEMU guest using the ``virtio-vsock`` transport instead of
traditional TTY-based consoles (e.g. serial, virtio-console, or VGA).

The console channel is implemented using AF_VSOCK sockets between the
host and the guest.  Unlike conventional console mechanisms, this
approach does not require the Linux TTY subsystem in the guest kernel.

The mechanism relies on the following components:

- ``virtio-vsock`` device exposed by QEMU
- AF_VSOCK socket support in the guest kernel
- a userspace relay (e.g. ``socat``) inside the guest
- a client on the host side

This approach is useful for debugging minimal kernels where TTY support
is intentionally disabled.


Mechanism
=========

``virtio-vsock`` provides a socket-like communication channel between
host and guest.  Each VM is assigned a context identifier (CID), and
communication occurs over ``(CID, port)`` pairs.

The host connects to the guest using:

::

    VSOCK-CONNECT:<cid>:<port>

Inside the guest a userspace program listens on the corresponding port
and connects the socket to a shell.

For example, in the guest:

::

    socat EXEC:/bin/bash,pty,stderr VSOCK-LISTEN:1234,reuseaddr

On the host:

::

    socat -,raw VSOCK-CONNECT:5:1234

This provides an interactive console without requiring a kernel console
device.


QEMU Configuration
==================

The QEMU guest must expose a virtio-vsock device.  For example:

::

    -device vhost-vsock-pci,guest-cid=5

``guest-cid`` must be unique among running VMs.


Kernel Configuration
====================

The following kernel configuration options are required in the guest:

::

    CONFIG_VSOCKETS=y
    CONFIG_VSOCKETS_LOOPBACK=y
    CONFIG_VIRTIO_VSOCKETS=y

Optional (debugging support):

::

    CONFIG_VSOCKETS_DIAG=y


Userspace
=========

The guest userspace typically runs a small relay program.  The examples
in this document use ``socat``:

::

    socat EXEC:/bin/bash,pty,stderr VSOCK-LISTEN:1234,reuseaddr

This binds a shell to the vsock port.

The host can then attach using any AF_VSOCK-capable client.


Notes
=====

- This mechanism bypasses the kernel console and TTY infrastructure.
- It only becomes available once userspace is running in the guest.
- It is suitable for lightweight debugging environments and minimal
  initramfs systems.
