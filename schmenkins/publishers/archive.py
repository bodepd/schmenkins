import os
import os.path
import shutil
from glob import glob

def publish(schmenkins, job, info, build):
    workspace = job.workspace()
    artifact_dir = build.artifact_dir()

    artifacts = info['artifacts']
    oldpath = os.getcwd()

    os.chdir(workspace)

    files = []
    for artifact in artifacts.split(','):
        files += glob(artifact)

    os.chdir(oldpath)

    for f in files:
        src_path = os.path.join(workspace, f)
        dst_path = os.path.join(artifact_dir, f)

        destdir = os.path.dirname(dst_path)

        if not os.path.isdir(destdir):
            os.makedirs(destdir)

        shutil.copy(src_path, dst_path)
