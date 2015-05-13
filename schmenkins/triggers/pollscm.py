import datetime
import logging
from croniter import croniter

def run(schmenkins, job, info):
    # This sucks
    cron = info.replace('H/', '*/')
    next_poll = croniter(cron, schmenkins.base_timestamp).get_next(datetime.datetime)
    if next_poll < schmenkins.now:
        logging.debug('%s should have been polled %s. Polling now.' % (job.name, next_poll))
        job.should_poll = True
