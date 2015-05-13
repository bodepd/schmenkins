import os
import tempfile

from schmenkins.utils import run_cmd

def run(schmenkins, job, info, build):
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        try:
            os.chmod(fp.name, 0o0700)
            fp.write(info)
            fp.close()

            maybe_shebang = info.split('\n')[0]

            if maybe_shebang.startswith('#!'):
                cmd = maybe_shebang[2:].split(' ')
            else:
                cmd = [os.environ.get('SHELL', '/bin/sh'), '-ex']

            cmd += [fp.name]

            run_cmd(cmd, cwd=job.workspace(), dry_run=schmenkins.dry_run,
                    logger=build.logger)
        finally:
            os.unlink(fp.name)

