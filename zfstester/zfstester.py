#!/usr/bin/env python3

# pylint: disable=C0111  # docstrings are always outdated and wrong
# pylint: disable=W0511  # todo is encouraged
# pylint: disable=C0301  # line too long
# pylint: disable=R0902  # too many instance attributes
# pylint: disable=C0302  # too many lines in module
# pylint: disable=C0103  # single letter var names, func name too descriptive
# pylint: disable=R0911  # too many return statements
# pylint: disable=R0912  # too many branches
# pylint: disable=R0915  # too many statements
# pylint: disable=R0913  # too many arguments
# pylint: disable=R1702  # too many nested blocks
# pylint: disable=R0914  # too many local variables
# pylint: disable=R0903  # too few public methods
# pylint: disable=E1101  # no member for base
# pylint: disable=W0201  # attribute defined outside __init__
# pylint: disable=R0916  # Too many boolean expressions in if statement


import os
import sys
import time
from pathlib import Path

import click
from kcl.pathops import path_is_block_special
from sh import (chmod, chown, cp, dd, grub_install, kpartx, ln, losetup, ls,
                mke2fs, mount, parted, sudo, umount)


def eprint(*args, **kwargs):
    if 'file' in kwargs.keys():
        kwargs.pop('file')
    print(*args, file=sys.stderr, **kwargs)


try:
    from icecream import ic  # https://github.com/gruns/icecream
except ImportError:
    ic = eprint


#from getdents import files

# import pdb; pdb.set_trace()
# from pudb import set_trace; set_trace(paused=False)


@click.command()
@click.argument("destination_folder",
                type=click.Path(exists=True,
                                dir_okay=True,
                                file_okay=False,
                                path_type=str,
                                allow_dash=False),
                nargs=1,
                required=True)
@click.option("--loop",
              type=click.Path(exists=True,
                              dir_okay=False,
                              file_okay=True,
                              path_type=str,
                              allow_dash=False),
              nargs=1,
              required=True)
@click.option('--verbose', is_flag=True)
@click.option('--debug', is_flag=True)
@click.option('--ipython', is_flag=True)
@click.option('--record-count', type=int)
@click.option("--printn", is_flag=True)
def cli(destination_folder,
        loop,
        verbose,
        debug,
        record_count,
        ipython,
        printn,):

    if os.getuid() != 0:
        ic('must be root')
        sys.exit(1)

    timestamp = time.time()
    ic(timestamp)

    if not path_is_block_special(loop):
        raise ValueError("loop device path {} is not block special".format(loop))

    if ipython:
        import IPython
        IPython.embed()

    loops_in_use = losetup("-l")
    ic(loops_in_use)
    if loop in loops_in_use:
        raise ValueError("loop device {} already in use".format(loop))

    os.cwd(destination_folder)
    os.makedirs(timestamp)
    os.cwd(timestamp)

    test_pool_file = "test_pool_{}".format(str(timestamp))
    ic(test_pool_file)
    sys.exit(0)
    dd("if=/dev/zero", "of={}".format(test_pool_file), "bs=64M", "count=1")
    #dd if=/dev/urandom of=temp_zfs_key bs=32 count=1 || exit 1
    #key_path=`readlink -f temp_zfs_key`

    losetup(loop, test_pool_file, loop)
    ic(losetup("-l"))

#zpool create -O atime=off -O compression=lz4 -O mountpoint=none "${test_pool_file}" "${loop}" || exit 1
#zfs create -o mountpoint=/"${test_pool_file}"/spacetest "${test_pool_file}"/spacetest || exit 1
#
## disabled just for pure space tests
##zfs create -o encryption=on -o keyformat=raw -o keylocation=file://"${key_path}" -o mountpoint=/"${test_pool_file}"/spacetest_enc "${test_pool_file}"/spacetest_enc || exit 1
#
#df -h | grep "${test_pool_file}" || exit 1
#
#cd /"${test_pool_file}"/spacetest || exit 1
#/bin/ls -alh || exit 1
#
## empty dirs 20M -> 205M
## > ~400000 -> "No space left on device"
##python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.makedirs(uuid.uuid4().hex) for _ in range(100000)]" || exit 1
#
## 64M -> 85325 dirs
##python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.makedirs(uuid.uuid4().hex) for _ in range($record_count)]"
#
## empty files 20M -> 106M
##python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.mknod(uuid.uuid4().hex) for _ in range(100000)]" || exit 1
#
##64M -> 108595 files
##python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.mknod(uuid.uuid4().hex) for _ in range($record_count)]" || exit 1
#
## broken symlinks 25M -> 101M
##python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.symlink(uuid.uuid4().hex, uuid.uuid4().hex) for _ in range(100000)]" || exit 1
#
## 64M -> 78693
##python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.symlink(uuid.uuid4().hex, uuid.uuid4().hex) for _ in range($record_count)]" || exit 1
#
## 64M -> 108465
#python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.symlink('None', uuid.uuid4().hex) for _ in range($record_count)]" || exit 1
#
#df -h | grep "${test_pool_file}" || exit 1
#/bin/ls -alh || exit 1
#
## disabled for pure space tests
##cp -ar * /"${test_pool_file}"/spacetest_enc/
#
#
#df -h | grep "${test_pool_file}"
#
#zfs get all | grep "${test_pool_file}"



