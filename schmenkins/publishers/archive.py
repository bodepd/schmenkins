import os
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
        shutil.copy(os.path.join(workspace, f), os.path.join(artifact_dir, f))
