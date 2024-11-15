# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os
import os.path
import glob

from typing import Optional, Dict, List, Any
from collections.abc import Mapping

import lkvm

logger = lkvm.logger


def find_image(srctree: str, env: Optional[Mapping[str,str]]=None) -> Optional[str]:
    if env is not None:
        for envname in ["KBUILD_OUTPUT", "KBUILD_ABS_SRCTREE"]:
            value = env.get(envname)

            if value and os.access(value, os.X_OK):
                srctree = value
                break

    res = []

    for img in glob.glob(f'{srctree}/arch/*/boot/*Image'):
        statinfo = os.stat(img)
        res.append((statinfo.st_mtime, img))

    if len(res) == 0:
        return None

    sorted(res, key=lambda x: x[0], reverse=True)

    logger.debug("Found kernel image: %s", res[0][1])
    return os.path.realpath(res[0][1])


class KernelCmdline:
    def __init__(self, init: Dict[str, Any]):
        self._mode = "ro"
        self._dict: Dict[str,str] = {}
        for k, v in init.items():
            self[k] = v

    def __contains__(self, key: str) -> bool:
        if key in ["rw", "ro"]:
            return self._mode == key
        return key in self._dict

    def __getitem__(self, key: str) -> Any:
        return self._dict[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key in ["rw", "ro"]:
            self._mode = key
            return
        self._dict[key] = value

    def __len__(self) -> int:
        n = 0
        for _, v in self._dict.items():
            if v is None:
                continue
            n += 1
        return n

    def keys(self) -> List[str]:
        return list(self._dict.keys())

    def join(self) -> str:
        ret = [ self._mode ]
        for k in sorted(self._dict.keys()):
            if self._dict[k] is None:
                continue
            if isinstance(self._dict[k], bool):
                ret.append(k)
            else:
                ret.append(f"{k}={self._dict[k]}")
        return " ".join(ret)


CMDLINE = KernelCmdline({})
