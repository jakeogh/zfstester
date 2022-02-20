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
from typing import Callable
from typing import Optional
from typing import Union

import click
import sh
from asserttool import ic
# from with_chdir import chdir
from clicktool import click_add_options
from clicktool import click_global_options
from clicktool import tv
from pathstat import display_results
from pathstat import pathstat
# from getdents import paths
from pathtool import path_is_block_special
from run_command import run_command
from timetool import timeit


@timeit
def make_things(
    root: Path, count: Optional[int], thing_function: Callable[[Path], None]
) -> None:
    assert thing_function in [os.makedirs, os.mknod, os.symlink]
    timestamp = str(time.time())
    target = root / Path(timestamp)
    os.makedirs(target)
    if count:
        for _ in range(count):
            thing_function(target / Path(uuid.uuid4().hex))
    else:
        while True:
            thing_function(target / Path(uuid.uuid4().hex))


def check_df(path: Path):
    _path = path.as_posix()
    df_result = sh.df("-h").splitlines()
    found = False
    for line in df_result:
        if _path in line:
            ic(line)
            found = True
    if not found:
        raise ValueError(f"{_path} not in df -h output")


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
@click.argument(
    "destination_folder",
    type=click.Path(
        exists=True, dir_okay=True, file_okay=False, path_type=Path, allow_dash=False
    ),
    nargs=1,
    required=True,
)
@click.option("--verbose", is_flag=True)
@click.option("--ipython", is_flag=True)
@click.option("--loopback", is_flag=True)
@click.option("--record-count", type=int)
@click.option("--zpool-size-mb", type=int, default=64)
@click.option(
    "--recordsize", type=str, default="128K"
)  # The size specified must be a power of two greater than or equal to 512 and less than or equal to 128 Kbytes man zprops
@click_add_options(click_global_options)
@click.pass_context
def cli(
    ctx,
    destination_folder: Path,
    zpool_size_mb: int,
    recordsize: str,
    verbose: Union[bool, int, float],
    verbose_inf: bool,
    loopback: bool,
    record_count: int,
    ipython: bool,
):

    tty, verbose = tv(
        ctx=ctx,
        verbose=verbose,
        verbose_inf=verbose_inf,
    )

    if os.getuid() != 0:
        ic("must be root")
        sys.exit(1)

    if zpool_size_mb < 64:
        raise ValueError("minimum zpool size is 64MB")

    timestamp = str(time.time())
    if verbose:
        ic(timestamp)

    if loopback:
        free_loop = sh.losetup("--find").splitlines()
        loop = Path(free_loop[0])

        if not path_is_block_special(loop):
            raise ValueError(f"loop device path {loop} is not block special")

        loops_in_use = sh.losetup("-l").splitlines()
        # ic(loops_in_use)
        for line in loops_in_use:
            if loop in loops_in_use:
                raise ValueError(f"loop device {loop} already in use")

    destination = Path(destination_folder) / Path(f"zfstester_{timestamp}")
    os.makedirs(destination)

    destination_pool_file = destination / Path(f"test_pool_{timestamp}")
    if verbose:
        ic(destination_pool_file)
    sh.dd(
        "if=/dev/zero",
        f"of={destination_pool_file.as_posix()}",
        f"bs={zpool_size_mb}M",
        "count=1",
    )
    # dd if=/dev/urandom of=temp_zfs_key bs=32 count=1 || exit 1
    # key_path=`readlink -f temp_zfs_key`

    if loopback:
        sh.losetup(loop, destination_pool_file, loop)
        atexit.register(cleanup_loop_device, loop)
        if verbose:
            ic(sh.losetup("-l"))

    zpool_name = destination_pool_file.name
    if verbose:
        ic(zpool_name)
    zpool_create_command = sh.Command("zpool")
    zpool_create_command = zpool_create_command.bake(
        "create",
        "-O",
        "atime=off",
        "-O",
        "compression=lz4",
        "-O",
        "mountpoint=none",
        "-O",
        f"recordsize={recordsize}",
        zpool_name,
    )
    if loopback:
        zpool_create_command = zpool_create_command.bake(loop)
    else:
        zpool_create_command = zpool_create_command.bake(destination_pool_file)

    zpool_create_command_result = zpool_create_command().splitlines()
    ic(zpool_create_command_result)

    # run_command(zpool_create_command, verbose=True)
    # atexit.register(destroy_zfs_pool, zpool_name)

    zfs_mountpoint = Path(f"{destination_pool_file.as_posix()}_mountpoint")
    zfs_filesystem = f"{zpool_name}/spacetest"
    zfs_create_command = sh.Command("zfs")
    zfs_create_command = zfs_create_command.bake(
        "create",
        "-o",
        f"mountpoint={zfs_mountpoint.as_posix()}",
        "-o",
        f"recordsize={recordsize}",
        zfs_filesystem,
    )
    zfs_create_command_result = zfs_create_command().splitlines()
    ic(zfs_create_command_result)

    atexit.register(umount_zfs_filesystem, zfs_mountpoint)
    # atexit.register(destroy_zfs_filesystem, zfs_filesystem)

    # disabled just for pure space tests
    # zfs create -o encryption=on -o keyformat=raw -o keylocation=file://"${key_path}" -o mountpoint=/"${destination_pool_file}"/spacetest_enc "${destination_pool_file}"/spacetest_enc || exit 1

    check_df(destination_pool_file)

    try:
        make_things(root=zfs_mountpoint, count=None, thing_function=os.makedirs)
    except Exception as e:
        ic(e)

    ic(sh.ls("-alh", zfs_mountpoint))

    check_df(destination_pool_file)

    sh.sync()
    pathstat_results = pathstat(path=zfs_mountpoint, verbose=verbose)
    display_results(pathstat_results, verbose=verbose)
    # 128K recordsize: 81266
    # 512  recordsize: 80894

    zfs_get_all_command_results_interesting_lines = []
    zfs_get_all_command = sh.Command("zfs")
    zfs_get_all_command = zfs_get_all_command.bake("get", "all")
    zfs_get_all_command_results = zfs_get_all_command().splitlines()
    interesting_fields = [
        "used",
        "available",
        "referenced",
        "compressratio",
        "recordsize",
        "checksum",
        "compression",
        "xattr",
        "copies",
        "version",
        "usedbysnapshots",
        "usedbydataset",
        "usedbychildren",
        "usedbyrefreservation",
        "dedup",
        "dnodesize",
        "refcompressratio",
        "written",
        "logicalused",
        "logicalreferenced",
        "acltype",
        "redundant_metadata",
        "encryption",
        "snapshot_count",
        "special_small_blocks",
    ]
    for line in zfs_get_all_command_results:
        if destination_pool_file.name in line:
            if line.split()[1] in interesting_fields:
                zfs_get_all_command_results_interesting_lines.append(line)
            print(line)

    print("\nInteresting lines from above:")
    for line in zfs_get_all_command_results_interesting_lines:
        print(line)

    df_inodes = str(sh.df("-i"))
    # ic(df_inodes)
    print()
    for index, line in enumerate(df_inodes.splitlines()):
        if index == 0:
            print(line)  # df -i header
        if destination_pool_file.name in line:
            df_line = line
            print(df_line)
            Inodes, IUsed, IFree, IUse = df_line.split()[1:5]

    destination_pool_file_rzip = destination_pool_file.as_posix() + ".rz"
    sh.rzip(
        "-k", "-9", "-o", destination_pool_file_rzip, destination_pool_file.as_posix()
    )
    compressed_file_size = os.stat(destination_pool_file_rzip).st_size

    destination_pool_file_sparse_copy = Path(
        destination_pool_file.as_posix() + ".sparse"
    )
    sh.cp(
        "-v",
        "-i",
        "--sparse=always",
        destination_pool_file,
        destination_pool_file_sparse_copy,
    )
    destination_pool_file_sparse_copy_file_size = (
        os.stat(destination_pool_file_sparse_copy).st_blocks * 512
    )

    # ic(compressed_file_size)

    print("\nSummary:")
    # ic(pathstat_results)
    print("pool file:")
    os.system(" ".join(["/bin/ls", "-al", destination_pool_file.as_posix()]))
    bytes_in_names = pathstat_results["bytes_in_names"]
    objects_created = pathstat_results[4]
    print()
    print(
        f"The {zpool_size_mb}MB pool ran out of free inodes (there are {IFree} out of {Inodes} left) after {bytes_in_names} bytes were written by creating {objects_created} empty directories (with random uncompressable names, under the root).\nCompressed, the pool file takes {compressed_file_size} bytes."
    )

    compression_ratio = (compressed_file_size / (zpool_size_mb * 1024 * 1024)) * 100
    print("compresson ratio:", str(round(compression_ratio, 2)) + "x")
    print(
        f"A sparse copy of the pool file is {destination_pool_file_sparse_copy_file_size}B (~{int(destination_pool_file_sparse_copy_file_size/1024/1024)}MB)"
    )

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
# python3 -c "import os; import time; import uuid; target=str(time.time()); os.makedirs(target); os.chdir(target); [os.symlink('None', uuid.uuid4().hex) for _ in range($record_count)]" || exit 1
#
# df -h | grep "${destination_pool_file}" || exit 1
# /bin/ls -alh || exit 1
#
## disabled for pure space tests
##cp -ar * /"${destination_pool_file}"/spacetest_enc/
#
#
# df -h | grep "${destination_pool_file}"
