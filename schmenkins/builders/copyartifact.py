import formic
import os.path
import shutil

from schmenkins import SchmenkinsJob
from schmenkins import SchmenkinsBuild
from schmenkins.exceptions import UnsupportedConfig
from schmenkins.utils import itpl, ensure_dir


def run(schmenkins, job, info, build):
    source_job = SchmenkinsJob(schmenkins,
                               schmenkins.jobs[itpl(info['project'],
                                                    build.parameters())])
    if info['which-build'] == 'specific-build':
        source_build = SchmenkinsBuild(source_job,
                                       build_number=itpl(info['build-number'],
                                                         build.parameters()))

    else:
        raise UnsupportedConfig(info['which-build'])

    target_dir = job.workspace()

    if 'target' in info:
        target_dir = os.path.join(target_dir, info['target'])

    ensure_dir(target_dir)

    source_dir = source_build.artifact_dir()

    fileset = formic.FileSet(directory=source_dir,
                             include=info['filter'])

    for f in fileset.qualified_files(absolute=False):
        shutil.copy(os.path.join(source_dir, f),
                    os.path.join(target_dir, f))


