.. highlight:: none

This document describes how to test each device, which is required when
modifying the common I/O infrastructure.


9P
--

  CONFIG_NET_9P_VIRTIO

Without a --disk parameter, lkvm shares part of the host filesystem
with the guest using 9p.


NFS
---

  CONFIG_ROOT_NFS=y
  CONFIG_NFS_V2=y
  CONFIG_NFS_V3=y

Another way to share part of the host filesystem with the guest is builtin nfs
server.


BLOCK
-----

  CONFIG_VIRTIO_BLK

	$ lkvm run ... --disk <raw or qcow2 image>


CONSOLE
-------

	$ lkvm run ... --console virtio

See also virtio-console.txt
