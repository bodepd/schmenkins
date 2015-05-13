from schmenkins import SchmenkinsJob

from schmenkins.exceptions import UnsupportedConfig
from schmenkins.utils import itpl

def publish(schmenkins, job, info, build):
    for _info in info:
        _publish(schmenkins, job, _info, build)

def _publish(schmenkins, job, info, build):
    if info['project'] not in schmenkins.jobs:
        raise Exception('Unknown job %s' % (info['project'],))

    if 'condition' in info:
        if info['condition'] == 'UNSTABLE_OR_BETTER':
            if job.state == 'FAILED':
                return
        else:
            raise UnsupportedConfig('%s' % (info['condition'],))

    parameters = {}

    for l in info['predefined-parameters'].split('\n'):
         if '=' not in l:
             continue
         k, v = l.split('=', 1)
         parameters[k] = itpl(v, build.parameters())

    trigger_job = SchmenkinsJob(schmenkins,
                                schmenkins.jobs[info['project']])
    triggered_build = trigger_job.run(parameters=parameters)

