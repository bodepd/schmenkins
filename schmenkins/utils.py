import logging
import os
import os.path
import re
import subprocess

from schmenkins import exceptions

itpl_regex = re.compile('\$({)?([a-z_][a-z0-9_]*)(?(1)})', re.VERBOSE | re.IGNORECASE)

def itpl(s, params):
    return itpl_regex.sub(lambda m:str(params.get(m.group(2), '')), s)

def run_cmd(args, cwd=None, dry_run=False, logger=None):
    if dry_run:
        logging.info('Would have run command: %r' % (args,))
        return ''
    else:
        logging.info('Running command: %r' % (args,))

        proc = subprocess.Popen(args, cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        buf = ''
        while True:
            l = proc.stdout.readline()
            if l == '':
                break

            logging.info(l.rstrip('\n'))

            if logger:
                logger.debug(l.rstrip('\n'))
            buf += l

        proc.communicate()
        logging.warning('Command returned: %r' % (buf,))

        if proc.returncode != 0:
            raise exceptions.SchmenkinsCommandFailed('%r failed with return code %d.' % (args, proc.returncode))

        return buf

def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path

def ensure_dir_wrapper(func):
    def wrapper(*args, **kwargs):
        return ensure_dir(func(*args, **kwargs))
    return wrapper


