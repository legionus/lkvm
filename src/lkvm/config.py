# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2024  Alexey Gladkov <legion@kernel.org>

import os.path
import re

from typing import Dict, List, Tuple, Any
from collections.abc import Generator

import lkvm
import lkvm.parameters

logger = lkvm.logger


class Mapping:
    def __init__(self, arg: Dict[str, Any]):
        self.arg = arg

    def __walk(self, d: Dict[str, Any], p: List[str]) -> Generator[Tuple[str, Any], None, None]:
        for k, v in d.items():
            n = p + [k]
            if isinstance(v, dict):
                yield from self.__walk(v, n)
            yield ".".join(n), v

    def walk(self) -> Generator[Tuple[str, Any], None, None]:
        return self.__walk(self.arg, [])


# pylint: disable-next=unused-argument
def subst_str(mapping: Mapping, key: List[str], value: str) -> str:
    varlist: List[str] = []

    while True:
        newlist = re.findall(r'\$\{(?P<name>[A-Za-z0-9_.-]+)\}', value)

        if newlist == varlist:
            break

        varlist = newlist

        for k, v in mapping.walk():
            if k.startswith("global."):
                k = k[len("global."):]
            if k in varlist:
                value = re.sub(re.escape(f"${{{k}}}"), str(v), value)

    return value


def subst(mapping: Mapping, key: List[str], value: Any) -> Any:
    if isinstance(value, str):
        return subst_str(mapping, key, value)

    if isinstance(value, dict):
        for k, v in value.items():
            value[k] = subst(mapping, key + [k], v)
        return value

    if isinstance(value, list):
        return list(map(lambda x: subst(mapping, key, x), value))

    return value


def expandvars(config: Dict[str,Any]) -> Dict[str,Any] | lkvm.Error:
    ret = subst(Mapping(config), [], config)

    if not isinstance(ret, dict):
        return lkvm.Error("unable to parse config file")

    return ret


def add_value(config: Dict[str, Any], name: str, value: Any) -> None:
    conf_type = "store"

    if name in lkvm.parameters.CONFNAMES:
        i = lkvm.parameters.CONFNAMES.index(name)
        conf_type = lkvm.parameters.PARAMS[i].action

    if conf_type in ["append"]:
        if name not in config:
            config[name] = []

        config[name].append(value)

    elif conf_type in ["store_true", "store_false"]:
        config[name] = value.upper() in ["1", "ON", "YES", "TRUE"]
    else:
        config[name] = value
    return


def read(basedir: str, name: str) -> Dict[str, Any] | lkvm.Error:
    basedir  = os.path.expanduser(f"{basedir}")
    profile  = f"{basedir}/{name}"
    conffile = f"{profile}/config"
    rootfs   = f"{profile}/rootfs"

    section = "vm"
    subsection = ""

    config: Dict[str, Any] = {
        "global": {
            "name"   : name,
            "basedir": basedir,
            "profile": profile,
            "config" : conffile,
            "rootfs" : rootfs,
        },
        "env": {
            "home": os.getenv("HOME"),
            "user": os.getenv("USER"),
        },
        section: {},
    }

    if not os.path.exists(conffile):
        return config

    with open(conffile, "r", encoding="utf-8") as f:
        while line := f.readline():
            line = line.rstrip()

            if not line:
                continue

            if m := re.match(r"^\s*#.*", line):
                continue

            if m := re.match(r"^\s*\[(?P<name>\S+)(\s+[\"'](?P<subname>[^\"']+)[\"'])?\]\s*$", line):
                #section    = m.group("name")
                #subsection = m.group("subname") or ""
                continue

            if m := re.match(r"^\s*(?P<name>[A-Za-z0-9_.-]+)\s*=\s*(?P<value>.*)\s*$", line):
                if section not in config:
                    config[section] = {}

                if subsection:
                    if subsection not in config[section]:
                        config[section][subsection] = {}

                    add_value(config[section][subsection], m.group("name"), m.group("value"))
                else:
                    add_value(config[section], m.group("name"), m.group("value"))
                continue

            return lkvm.Error(f"unexpected config line: '{line}'")

    newconfig = expandvars(config)

    logger.info("config has been read")
    return newconfig
