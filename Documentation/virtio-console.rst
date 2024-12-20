.. highlight:: none

General
--------

virtio-console as the name implies is a console over virtio transport. Here is
a simple head to head comparison of the virtio-console vs regular 8250 console:

8250 serial console:

 - Requires CONFIG_SERIAL_8250=y and CONFIG_SERIAL_8250_CONSOLE=y kernel configs,
which are enabled almost everywhere.
 - Doesn't require guest-side changes.
 - Compatible with older guests.

virtio-console:

 - Requires CONFIG_VIRTIO_CONSOLE=y (along with all other virtio dependencies),
which got enabled only in recent kernels (but not all of them).
 - Much faster.
 - Consumes less processing resources.
 - Requires guest-side changes.

Enabling virtio-console
------------------------

First, make sure guest kernel is built with CONFIG_VIRTIO_CONSOLE=y. Once this
is done, the following has to be done inside guest image:

 - Add the following line to /etc/inittab:
	'hvc0:2345:respawn:/sbin/agetty -L 9600 hvc0'
 - Add 'hvc0' to /etc/securetty (so you could actually log on)
 - Start the guest with '--console virtio'

Common errors
--------------

Q: I don't see anything on the screen!
A: Make sure CONFIG_VIRTIO_CONSOLE=y is enabled in the *guest* kernel, also
make sure you've updated /etc/inittab

Q: It won't accept my username/password, but I enter them correctly!
A: You didn't add 'hvc0' to /etc/securetty
