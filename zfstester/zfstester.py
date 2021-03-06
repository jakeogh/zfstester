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

# pylint: disable=no-name-in-module  # sh

import atexit
import os
import sys
import time
import uuid
from math import inf
from pathlib import Path

import click
#from with_chdir import chdir
import sh
#from getdents import paths
from kcl.pathops import path_is_block_special
from pathstat import display_results
from pathstat import pathstat
from run_command import run_command


def eprint(*args, **kwargs):
    if 'file' in kwargs.keys():
        kwargs.pop('file')
    print(*args, file=sys.stderr, **kwargs)


try:
    from icecream import ic  # https://github.com/gruns/icecream
except ImportError:
    ic = eprint


def make_things(root, count, thing_function):
    assert thing_function in [os.makedirs, os.mknod, os.symlink]
    target = str(time.time())
    target = Path(root) / Path(target)
    os.makedirs(target)
    if count != inf:
        for _ in range(count):
            thing_function(target / Path(uuid.uuid4().hex))
    else:
        while True:
            thing_function(target / Path(uuid.uuid4().hex))


def check_df(match):
    if isinstance(match, Path):
        match = match.as_posix()
    df_result = sh.df("-h").splitlines()
    found = False
    for line in df_result:
        if match in line:
            ic(line)
            found = True
    if not found:
        raise ValueError("{} not in df -h output".format(match))


def cleanup_loop_device(device):
    print(sh.losetup("-d", device))


def umount_zfs_filesystem(mountpoint):
    print(sh.umount(mountpoint))


def destroy_zfs_filesystem(filesystem):
    destroy_command = ["zfs", "destroy", filesystem]
    run_command(destroy_command, verbose=True)


def destroy_zfs_pool(pool):
    zpool_destroy_command = ["zpool", "destroy", pool]
    run_command(zpool_destroy_command, verbose=True)


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
              required=False)
@click.option('--verbose', is_flag=True)
@click.option('--debug', is_flag=True)
@click.option('--ipython', is_flag=True)
@click.option('--record-count', type=int)
@click.option('--zpool-size-mb', type=int, default=64)
@click.option('--recordsize', type=str, default="128K")  # The size specified must be a power of two greater than or equal to 512 and less than or equal to 128 Kbytes man zprops
@click.option("--printn", is_flag=True)
def cli(destination_folder: str,
        loop: str,
        zpool_size_mb: int,
        recordsize: str,
        verbose: bool,
        debug: bool,
        record_count: int,
        ipython: bool,
        printn: bool,
        ):

    if os.getuid() != 0:
        ic('must be root')
        sys.exit(1)

    if zpool_size_mb < 64:
        raise ValueError('minimum zpool size is 64MB')

    timestamp = str(time.time())
    if verbose:
        ic(timestamp)

    if not loop:
        loop = '/dev/loop0'

    if not path_is_block_special(loop):
        raise ValueError("loop device path {} is not block special".format(loop))

    loops_in_use = sh.losetup("-l").splitlines()
    #ic(loops_in_use)
    for line in loops_in_use:
        if loop in loops_in_use:
            raise ValueError("loop device {} already in use".format(loop))

    destination = Path(destination_folder) / Path('zfstester_' + timestamp)
    os.makedirs(destination)

    destination_pool_file = destination / Path("test_pool_{}".format(timestamp))
    if verbose:
        ic(destination_pool_file)
    sh.dd("if=/dev/zero", "of={}".format(destination_pool_file), "bs={}M".format(zpool_size_mb), "count=1")
    #dd if=/dev/urandom of=temp_zfs_key bs=32 count=1 || exit 1
    #key_path=`readlink -f temp_zfs_key`

    sh.losetup(loop, destination_pool_file, loop)
    atexit.register(cleanup_loop_device, loop)
    if verbose:
        ic(sh.losetup("-l"))

    zpool_name = destination_pool_file.name
    if verbose:
        ic(zpool_name)
    zpool_create_command = ["zpool",
                            "create",
                            "-O", "atime=off",
                            "-O", "compression=lz4",
                            "-O", "mountpoint=none",
                            "-O", "recordsize=" + recordsize,
                            zpool_name,
                            loop]
    run_command(zpool_create_command, verbose=True)
    #atexit.register(destroy_zfs_pool, zpool_name)

    zfs_mountpoint = "{}_mountpoint".format(destination_pool_file)
    zfs_filesystem = "{}/spacetest".format(zpool_name)
    zfs_create_command = ["zfs", "create", "-o", "mountpoint={}".format(zfs_mountpoint), "-o", "recordsize=" + recordsize, zfs_filesystem]
    run_command(zfs_create_command, verbose=True)
    #atexit.register(destroy_zfs_filesystem, zfs_filesystem)
    atexit.register(umount_zfs_filesystem, zfs_mountpoint)

    ## disabled just for pure space tests
    ##zfs create -o encryption=on -o keyformat=raw -o keylocation=file://"${key_path}" -o mountpoint=/"${destination_pool_file}"/spacetest_enc "${destination_pool_file}"/spacetest_enc || exit 1

    check_df(destination_pool_file)

    try:
        make_things(root=zfs_mountpoint,
                    count=inf,
                    thing_function=os.makedirs)
    except Exception as e:
        ic(e)

    ic(sh.ls("-alh", zfs_mountpoint))

    check_df(destination_pool_file)

    sh.sync()
    pathstat_results = pathstat(path=zfs_mountpoint, verbose=verbose)
    display_results(pathstat_results, verbose=verbose)
    # 128K recordsize: 81266
    # 512  recordsize: 80894

    zfs_get_all_command = ["zfs", "get", "all"]
    output = run_command(zfs_get_all_command).decode('utf8')
    for line in output.splitlines():
        if destination_pool_file.name in line:
            print(line)

    df_inodes = str(sh.df('-i'))
    #ic(df_inodes)
    print()
    for index, line in enumerate(df_inodes.splitlines()):
        if index == 0:
            print(line)  # df -i header
        if destination_pool_file.name in line:
            print(line)


    destination_pool_file_rzip = destination_pool_file.as_posix() + '.rz'
    sh.rzip('-k', '-9', '-o', destination_pool_file_rzip, destination_pool_file.as_posix())
    compressed_file_size = os.stat(destination_pool_file_rzip).st_size
    #ic(compressed_file_size)

    print('\nSummary:')
    #ic(pathstat_results)
    bytes_in_names = pathstat_results['bytes_in_names']
    objects_created = pathstat_results[4]
    print('Why did this {zpool_size_mb}MB pool run out of space?\nExactly {bytes_in_names} bytes were written to it by creating {objects_created} empty directories (with random uncompressable names) under the root of the zfs filesystem.\nCompressed, the pool file takes {compressed_file_size} bytes.'.format(zpool_size_mb=zpool_size_mb, compressed_file_size=compressed_file_size, bytes_in_names=bytes_in_names, objects_created=objects_created))

    compression_ratio = (compressed_file_size / (zpool_size_mb * 1024 * 1024)) * 100
    print(str(round(compression_ratio, 2)) + 'X')

    print("\nHow can more 64byte randomly named empty directories be created under the root of this {zpool_size_mb}MB pool?".format(zpool_size_mb=zpool_size_mb))
    if ipython:
        import IPython
        IPython.embed()


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
#df -h | grep "${destination_pool_file}" || exit 1
#/bin/ls -alh || exit 1
#
## disabled for pure space tests
##cp -ar * /"${destination_pool_file}"/spacetest_enc/
#
#
#df -h | grep "${destination_pool_file}"

