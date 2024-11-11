# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import abc
import asyncio
import datetime
import errno
import hmac
import os
import os.path
import secrets
import stat
import struct
import time
import weakref

from typing import Optional, Sequence, Dict, Tuple, Union, Any

from shenaniganfs.fs          import FileType, BaseFSEntry, BaseFS, NFSError, FSException, DecodedFileHandle # type: ignore[import-untyped]
from shenaniganfs.fs_manager  import EvictingFileSystemManager, FileSystemManager, create_fs                 # type: ignore[import-untyped]
from shenaniganfs.nfs2        import MountV1Service, NFSV2Service                                            # type: ignore[import-untyped]
from shenaniganfs.nfs3        import MountV3Service, NFSV3Service                                            # type: ignore[import-untyped]
from shenaniganfs.server      import TCPTransportServer                                                      # type: ignore[import-untyped]
from shenaniganfs.statd       import StatDV1Server                                                           # type: ignore[import-untyped]

import lkvm

logger = lkvm.logger


ERRNO_MAPPING = {
    errno.EACCES       : NFSError.ERR_ACCES,
    errno.EDQUOT       : NFSError.ERR_DQUOT,
    errno.EEXIST       : NFSError.ERR_EXIST,
    errno.EFBIG        : NFSError.ERR_FBIG,
    errno.EIO          : NFSError.ERR_IO,
    errno.EISDIR       : NFSError.ERR_ISDIR,
    errno.ENAMETOOLONG : NFSError.ERR_NAMETOOLONG,
    errno.ENODEV       : NFSError.ERR_NODEV,
    errno.ENOENT       : NFSError.ERR_NOENT,
    errno.ENOSPC       : NFSError.ERR_NOSPC,
    errno.ENOTDIR      : NFSError.ERR_NOTDIR,
    errno.ENOTEMPTY    : NFSError.ERR_NOTEMPTY,
    errno.ENXIO        : NFSError.ERR_NXIO,
    errno.EPERM        : NFSError.ERR_PERM,
    errno.EROFS        : NFSError.ERR_ROFS,
    errno.ESTALE       : NFSError.ERR_STALE,
}


class FSEntry(BaseFSEntry): # type: ignore
    fs_source: bytes
    fs_stat: os.stat_result


class FSEntryLink:
    """Quick way to make fake hardlinks with different names like `.` and `..`"""

    def __init__(self, base: FSEntry, replacements: Dict[str, Any]):
        self.base = base
        self.replacements = replacements

    def __getattr__(self, item: str) -> Any:
        if item in self.replacements:
            return self.replacements[item]
        return getattr(self.base, item)


class FSinodes(abc.ABC):
    def __init__(self) -> None:
        self.inodes: Dict[Tuple[int,int],int] = {}
        self.last_inode = 0

    def get(self, dev: int, ino: int) -> int:
        v = (dev, ino)
        if v not in self.inodes:
            self.last_inode += 1
            self.inodes[v] = self.last_inode
        return self.inodes[v]

    def put(self, dev: int, ino: int) -> None:
        v = (dev, ino)
        del self.inodes[v]


def nfserror_from_errno(errnum: int) -> Any:
    return ERRNO_MAPPING.get(errnum, NFSError.ERR_IO)

def fill_fsentry(entry: FSEntry, st: os.stat_result) -> FSEntry:
    kwargs: Dict[str, Any] = {
            "fs_stat" : st,
            "mode"    : st.st_mode,
            "size"    : st.st_size,
            "blocks"  : st.st_blocks,
            "uid"     : st.st_uid,
            "gid"     : st.st_gid,
            "rdev"    : (os.major(st.st_rdev), os.minor(st.st_rdev)) if st.st_rdev else (0, 0),
            "atime"   : datetime.datetime.fromtimestamp(st.st_atime, datetime.UTC),
            "mtime"   : datetime.datetime.fromtimestamp(st.st_mtime, datetime.UTC),
            "ctime"   : datetime.datetime.fromtimestamp(st.st_ctime, datetime.UTC),
    }

    for k, v in kwargs.items():
        setattr(entry, k, v)
    return entry

def close_no_exc(fd: int) -> None:
    try:
        if fd >= 0:
            os.close(fd)
    except Exception:
        pass

def set_fd_attrs(fd: int, attrs: Dict[str, Any]) -> None:
    if "uid" in attrs or "gid" in attrs:
        uid = attrs.get("uid", -1)
        gid = attrs.get("gid", -1)
        os.fchown(fd, uid, gid)

    if "mode" in attrs:
        os.fchmod(fd, attrs["mode"])

    if "atime" in attrs or "mtime" in attrs:
        atime = mtime = int(time.time())

        if "atime" in attrs and attrs["atime"] is not None:
            atime = int(attrs["atime"].timestamp())

        if "mtime" in attrs and attrs["mtime"] is not None:
            mtime = int(attrs["mtime"].timestamp())

        os.utime(fd, times=(atime, mtime))


class OverlayFS(BaseFS): # type: ignore
    root_dir: Optional[FSEntry]

    def __init__(self,
                 rootfs: bytes,
                 read_only: bool = False,
                 size_quota: Optional[int] = None,
                 entries_quota: Optional[int] = None,
                 mountpoints: Optional[Dict[bytes, bytes]] = None) -> None:
        super().__init__()

        self.num_blocks = 1
        self.free_blocks = 0
        self.avail_blocks = 0

        self.read_only = read_only
        self.size_quota = size_quota
        self.entries_quota = entries_quota
        self.mountpoints = mountpoints or {}
        self.entries: Dict[int, FSEntry] = {}
        self.inodes = FSinodes()

        self.root_dir = None
        self.root_dir = self.create_fsentry(rootfs)
        self.track_entry(self.root_dir)

    def create_fsentry(self, path: bytes,
                       parent: Optional[FSEntry] = None,
                       fstat: Optional[os.stat_result] = None) -> FSEntry:
        types = {
            stat.S_IFDIR : FileType.DIR,
            stat.S_IFCHR : FileType.CHR,
            stat.S_IFBLK : FileType.BLK,
            stat.S_IFREG : FileType.REG,
            stat.S_IFIFO : FileType.FIFO,
            stat.S_IFLNK : FileType.LNK,
            stat.S_IFSOCK: FileType.SOCK,
        }

        path = os.path.abspath(path)
        parent_id = None
        overlay_path = None
        fs_path = path

        if self.root_dir:
            overlay_path = self.mountpoints.get(path[len(self.root_dir.fs_source):])
            if overlay_path:
                fs_path = overlay_path

        if parent:
            parent_id = parent.fileid

        if fstat is None:
            fstat = os.lstat(fs_path)

        entry = fill_fsentry(FSEntry(), fstat)

        kwargs: Dict[str, Any] = {
                "fs_source" : fs_path,
                "fs_links"  : 0,
                "fs"        : weakref.ref(self),
                "type"      : types.get(stat.S_IFMT(entry.fs_stat.st_mode),
                                        FileType.REG),
                "name"      : os.path.basename(path),
                "parent_id" : parent_id,
                "fileid"    : self.inodes.get(entry.fs_stat.st_dev,
                                              entry.fs_stat.st_ino),
                "nlink"     : 2,
        }

        for k, v in kwargs.items():
            setattr(entry, k, v)
        return entry

    def track_entry(self, entry: FSEntry) -> None:
        if entry.fileid not in self.entries:
            logger.debug("add entry: inode=%s: %s", entry.fileid, entry.fs_source)
            self.entries[entry.fileid] = entry

        logger.debug("get entry: inode=%s: %s", entry.fileid, entry.fs_source)
        entry.fs_links += 1

    def remove_entry(self, entry: FSEntry) -> None:
        if entry.fileid in self.entries:
            logger.debug("dec entry: inode=%s: %s", entry.fileid, entry.fs_source)
            entry.fs_links -= 1

        if entry.fs_links > 0:
            return

        logger.debug("put entry: inode=%s: %s", entry.fileid, entry.fs_source)

        self.inodes.put(entry.fs_stat.st_dev, entry.fs_stat.st_ino)
        del self.entries[entry.fileid]

    def get_child_by_name(self, directory: FSEntry, name: bytes) -> Optional[Union[FSEntry, FSEntryLink]]:
        return self.lookup(directory, name)

    def get_entry_by_id(self, fileid: int) -> Optional[FSEntry]:
        return self.entries.get(fileid)

    def get_dir_childs(self, directory: FSEntry) -> Dict[bytes, Union[FSEntry, FSEntryLink]]:
        self._verify_owned(directory)

        if directory.type != FileType.DIR:
            raise FSException(NFSError.ERR_NOTDIR)

        parent = directory.fs().root_dir

        if directory.parent_id:
            parent = self.get_entry_by_id(directory.parent_id)

        childs: Dict[bytes, Union[FSEntry, FSEntryLink]] = {
                b"." : FSEntryLink(directory, {"name": b"." }),
                b"..": FSEntryLink(parent,    {"name": b".."}),
        }

        try:
            fd = -1
            fd = os.open(directory.fs_source, os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NOCTTY)

            for name in os.listdir(fd):
                fname = name.encode("utf-8")
                st = os.lstat(fname, dir_fd=fd)

                if cur := self.get_entry_by_id(self.inodes.get(st.st_dev, st.st_ino)):
                    childs[fname] = cur
                    continue

                new = self.create_fsentry(os.path.join(directory.fs_source, fname),
                                          directory, fstat=st)
                childs[fname] = new
                self.track_entry(new)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        finally:
            close_no_exc(fd)

        directory.nlink = len(childs)

        return childs

    def lookup(self, directory: FSEntry, name: bytes) -> Optional[Union[FSEntry, FSEntryLink]]:
        logger.debug("CALL: lookup: dir=%s name=%s", directory.fs_source, name)

        childs = self.get_dir_childs(directory)
        return childs.get(name)

    def readdir(self, directory: FSEntry) -> Sequence[Union[FSEntry, FSEntryLink]]:
        logger.debug("CALL: readdir: dir=%s", directory.fs_source)

        childs = self.get_dir_childs(directory)
        return list(childs.values())

    def mkdir(self, dest: FSEntry, name: bytes, attrs: Dict[str, Any]) -> FSEntry:
        logger.debug("CALL: mkdir: dir=%s name=%s", dest.fs_source, name)

        self._verify_owned(dest)
        self._verify_writable()

        path = os.path.join(dest.fs_source, name)

        try:
            fd1 = -1
            fd1 = os.open(dest.fs_source, os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NOCTTY)

            os.mkdir(name, mode=0o700, dir_fd=fd1)

            fd2 = -1
            fd2 = os.open(name, os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NOCTTY, dir_fd=fd1)

            set_fd_attrs(fd2, attrs)
            st = os.fstat(fd2)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in mkdir(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd1)
            close_no_exc(fd2)

        entry = self.create_fsentry(path, dest, fstat=st)
        self.track_entry(entry)

        return entry

    def rmdir(self, entry: FSEntry) -> None:
        logger.debug("CALL: rmdir: entry=%s", entry.fs_source)

        self._verify_owned(entry)
        self._verify_writable()

        if entry.type != FileType.DIR:
            raise FSException(NFSError.ERR_NOTDIR, "Not a directory")

        if entry == self.root_dir:
            raise FSException(NFSError.ERR_NOTEMPTY, "Trying to remove root dir")

        try:
            os.rmdir(entry.fs_source)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in rmdir(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc

        self.remove_entry(entry)

    def rename(self, source: FSEntry, to_dir: FSEntry, new_name: bytes) -> None:
        logger.debug("CALL: rename: src=%s dst=%s name=%s", source.fs_source, to_dir.fs_source, new_name)

        self._verify_owned(source)
        self._verify_owned(to_dir)
        self._verify_writable()

        if to_dir.type != FileType.DIR:
            raise FSException(NFSError.ERR_NOTDIR, "Not a directory")

        path = os.path.join(to_dir.fs_source, new_name)

        try:
            fd1 = -1
            fd1 = os.open(to_dir.fs_source, os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NOCTTY)

            os.rename(source.fs_source, new_name, dst_dir_fd=fd1)
            st = os.lstat(new_name, dir_fd=fd1)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in rename(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd1)

        entry = self.create_fsentry(path, to_dir, fstat=st)
        self.track_entry(entry)

        self.remove_entry(source)

    def create_file(self, dest: FSEntry, name: bytes, attrs: Dict[str, Any]) -> FSEntry:
        logger.debug("CALL: create_file: dst=%s name=%s", dest.fs_source, name)

        self._verify_owned(dest)
        self._verify_writable()

        path = os.path.join(dest.fs_source, name)

        try:
            fd = -1
            fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NOCTTY)
            set_fd_attrs(fd, attrs)
            st = os.fstat(fd)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in create_file(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd)

        entry = self.create_fsentry(path, dest, fstat=st)
        self.track_entry(entry)

        return entry

    def rm(self, entry: FSEntry) -> None:
        logger.debug("CALL: remove: entry=%s", entry.fs_source)

        self._verify_owned(entry)
        self._verify_writable()

        try:
            os.remove(entry.fs_source)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in rm(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc

        self.remove_entry(entry)

    def read(self, entry: FSEntry, offset: int, count: int) -> bytes:
        logger.debug("CALL: read: entry=%s offset=%s count=%s", entry.fs_source, offset, count)

        self._verify_owned(entry)

        if entry.type != FileType.REG:
            raise FSException(NFSError.ERR_IO)

        try:
            fd = -1
            fd = os.open(entry.fs_source, os.O_RDONLY|os.O_NOFOLLOW|os.O_NOCTTY)
            res = os.pread(fd, count, offset)

            fill_fsentry(entry, os.fstat(fd))

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in read(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd)

        return res

    def write(self, entry: FSEntry, offset: int, data: bytes) -> int:
        logger.debug("CALL: write: entry=%s", entry.fs_source)

        self._verify_owned(entry)
        self._verify_writable()

        if entry.type != FileType.REG:
            raise FSException(NFSError.ERR_IO, "Not a regular file!")

        try:
            fd = -1
            fd = os.open(entry.fs_source, os.O_WRONLY|os.O_NOFOLLOW|os.O_NOCTTY)
            res = os.pwrite(fd, data, offset)

            fill_fsentry(entry, os.fstat(fd))

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in write(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd)

        return res

    def readlink(self, entry: FSEntry) -> bytes:
        logger.debug("CALL: readlink: entry=%s", entry.fs_source)

        self._verify_owned(entry)

        if entry.type != FileType.LNK:
            raise FSException(NFSError.ERR_IO)

        try:
            res = os.readlink(entry.fs_source)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in readlink(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc

        return res

    def symlink(self, dest: FSEntry, name: bytes, attrs: Dict[str, Any], val: bytes) -> FSEntry:
        logger.debug("CALL: symlink: dst=%s name=%s", dest.fs_source, name)

        self._verify_owned(dest)
        self._verify_writable()

        path = os.path.join(dest.fs_source, name)

        try:
            fd1 = -1
            fd1 = os.open(dest.fs_source, os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NOCTTY)

            os.symlink(val, name, dir_fd=fd1)

            fd2 = -1
            fd2 = os.open(name, os.O_NOFOLLOW|os.O_NOCTTY, dir_fd=fd1)

            set_fd_attrs(fd2, attrs)
            st = os.fstat(fd2)

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in symlink(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd1)
            close_no_exc(fd2)

        entry = self.create_fsentry(path, dest, fstat=st)
        self.track_entry(entry)

        return entry

    def setattrs(self, entry: FSEntry, attrs: Dict[str, Any]) -> None:
        logger.debug("CALL: setattrs: entry=%s attrs=%s", entry.fs_source, attrs)

        self._verify_owned(entry)
        self._verify_writable()

        try:
            fd = -1
            fd = os.open(entry.fs_source, os.O_WRONLY|os.O_NOFOLLOW|os.O_NOCTTY)

            set_fd_attrs(fd, attrs)
            fill_fsentry(entry, os.fstat(fd))

        except OSError as exc:
            raise FSException(nfserror_from_errno(exc.errno), exc.strerror) from exc
        except Exception as exc:
            logger.critical("Unexpected exception in setattrs(): %s", repr(exc))
            raise FSException(NFSError.ERR_IO) from exc
        finally:
            close_no_exc(fd)


class OverlayFileHandleEncoder(abc.ABC):
    """64bit FSID and FileID preceded by 128 or 256bit HMAC"""

    def __init__(self, hmac_secret: bytes) -> None:
        self.hmac_secret = hmac_secret

    @staticmethod
    def _mac_len(nfs_v2: bool = False) -> int:
        return 16 if nfs_v2 else 32

    def _calc_mac(self, data: bytes, nfs_v2: bool = False) -> bytes:
        # Truncated sha256 isn't recommended, but fine for our purposes.
        # We're limited to 32 byte FHs if we want to support NFSv2 so
        # we don't really have a choice.
        digest = hmac.new(self.hmac_secret, data, 'sha256').digest()

        return digest[:self._mac_len(nfs_v2)]

    def encode(self, entry: Union[FSEntry, DecodedFileHandle], nfs_v2: bool = False) -> bytes:
        payload = struct.pack("!QQ", entry.fileid, entry.fsid)

        return self._calc_mac(payload, nfs_v2) + payload

    def decode(self, fh: bytes, nfs_v2: bool = False) -> DecodedFileHandle:
        mac_len = self._mac_len(nfs_v2)
        expected_len = 16 + mac_len

        if len(fh) != expected_len:
            raise FSException(NFSError.ERR_IO, f"FH {fh!r} is not {expected_len} bytes")

        mac, payload = fh[:mac_len], fh[mac_len:]

        if not secrets.compare_digest(mac, self._calc_mac(payload, nfs_v2)):
            raise FSException(NFSError.ERR_IO, f"FH {fh!r} failed sig check")

        return DecodedFileHandle(*struct.unpack("!QQ", payload))


async def serve_nfs(fs_manager: FileSystemManager,
                    srvaddr: Tuple[str,int] = ("localhost", 2049)) -> None:

    transport_server = TCPTransportServer(srvaddr[0], srvaddr[1])
    transport_server.register_prog(MountV1Service(fs_manager))
    transport_server.register_prog(NFSV2Service(fs_manager))
    transport_server.register_prog(MountV3Service(fs_manager))
    transport_server.register_prog(NFSV3Service(fs_manager))
    transport_server.register_prog(StatDV1Server())
    await transport_server.notify_rpcbind()

    server = await transport_server.start()

    async with server:
        await server.serve_forever()


async def main(rootfs: bytes,
               mountpoints: Dict[bytes, bytes],
               nfsport: int) -> None:
    fs_manager = EvictingFileSystemManager(
        OverlayFileHandleEncoder(os.urandom(32)),
        factories = {
            b"/": lambda ctx: create_fs(OverlayFS, ctx,
                                        rootfs=rootfs,
                                        mountpoints=mountpoints),
        },
    )
    await serve_nfs(fs_manager, srvaddr=("localhost", nfsport))


def thread(rootfs: bytes,
           mountpoints: Dict[bytes, bytes],
           nfsport: int) -> None:
    asyncio.run(main(rootfs, mountpoints, nfsport))
