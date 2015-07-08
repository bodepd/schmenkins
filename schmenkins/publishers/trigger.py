from schmenkins.exceptions import UnsupportedConfig
from schmenkins.utils import itpl

def publish(schmenkins, job, info, build):
    if info['project'] not in schmenkins.jobs:
        raise Exception('Unknown job %s' % (info['project'],))

    if info.get('threshold', 'SUCCESS'):
        if build.state.state != 'SUCCESS':
            return
    else:
        raise UnsupportedConfig('%s' % (info['condition'],))

    trigger_job = schmenkins.get_job(info['project'])
    triggered_build = trigger_job.run()
