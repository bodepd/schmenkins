import datetime
import logging
import re
import httplib
import json
from croniter import croniter
import pprint

github_get_lookuphash = {}

#
# take some params, reads stuff from scm, determines if a build should launch,
# sets some env vars
#
def run(schmenkins, job, info):
    """
    run method that determines if a job should run
    """
    cron = info['cron'].replace('H/', '*/')
    next_poll = croniter(cron, schmenkins.base_timestamp).get_next(datetime.datetime)
    if True:
    #if next_poll < schmenkins.now:
        scm = job._job_dict['scm']
        if len(scm) != 1:
            print "Expecting 1 scm entry, found %s, this plugin doesn't know what to do with that" % len(scm)
        logging.debug('%s should have run by: %s, polling github repo now' % (job.name, next_poll))
        repo_url = scm[0]['git']['url']
        return poll(repo_url, info)
    else:
        return None

# takes the specified rules and determines if a job should be triggered.
# needs to pass in the info for that event so that we know what to do with it.
def poll(repo_url, info):
    print get_github_data('/rate_limit')
    warn_unsupported_args(info)
    repo_a = get_repo_name_and_org(repo_url)
    data = get_events(
        repo_a[0],
        repo_a[1],
        get_last_poll_time()
    )
    data_to_keep = []
    if data is not None:
        for i in data:
          #print "\n\n\n\n"
          #  pp = pprint.PrettyPrinter(indent=1)
          #  pp.pprint(i)
            if keep_event(
                i,
                info.get('admin-list', []) + info.get('white-list', []),
                info.get('white-list-target-branches', ['master']),
                info.get('permit-all', False),
                info.get('trigger-phrase', 'Please test this')
            ):
                data_to_keep.append(i)
    return convert_events_to_build_params(data_to_keep)
    # search the results to see if there are any events that we care about
    # write the current time into our state

def convert_events_to_build_params(events):
    build_params = []
    for event in events:
        env = {}
        if event['type'] == 'IssueCommentEvent':
            issue = event['payload']['issue']
            user = get_github_data(event['payload']['comment']['user']['url'])
            pr = get_github_data(issue['pull_request']['url'])
            commit_user = get_github_data(pr['head']['user']['url'])
            pull_request_user = get_github_data(pr['user']['url'])
            env = env_from_github_objects(
                user,
                commit_user,
                pull_request_user,
                pr
            )
            print env
        elif event['type'] == 'PullRequestEvent':
            user = get_github_data(event['actor']['url'])
            pr = get_github_data(event['payload']['pull_request']['url'])
            commit_user = get_github_data(pr['head']['user']['url'])
            pull_request_user = get_github_data(pr['user']['url'])
            env = env_from_github_objects(
                user,
                commit_user,
                pull_request_user,
                pr
            )
        elif event['type'] == 'PushEvent':
            user = get_github_data(event['actor']['url'])
            ref = event['payload']['ref'].rpartition('/')[2]
            head_ref = event['payload']['head']
            pulls = get_github_data(
                "%s/%s?head=%s:%s" % (event['repo']['url'], 'pulls', event['actor']['login'], ref)
            )
            if len(pulls) == 1:
                pr = pulls[0]
                pull_request_user = get_github_data(pr['user']['url'])
                commit_user = get_github_data(pr['head']['user']['url'])
                env = env_from_github_objects(
                    user,
                    commit_user,
                    pull_request_user,
                    pr
                )
            else:
                print "Found %s matches for ref, ingnoring" % len(pulls)
        else:
            print "Unexpected event type %s" % event['type']
        build_hash = {'build_params': env}
        if env['merge_commit_sha1'] is None:
            build_hash['mergeable'] = False
        else:
            build_hash['mergeable'] = True
        build_params.append(build_hash)
    return build_params

def env_from_github_objects(
    user,
    commit_user,
    pr_user,
    pr
):
    env = {}
    env['ghprbTriggerAuthor'] = user['name']
    env['ghprbTriggerAuthorEmail'] = user['email']
    env['ghprbPullId'] = pr['number']
    env['ghprbPullLink'] = pr['url']
    env['ghprbPullTitle'] = pr['title']
    env['merge_commit_sha1'] = pr['merge_commit_sha']
    if env.get('merge_commit_sha1', False):
        merge_message = 'no merge conflicts'
        env['sha1'] = "origin/pr/%s/merge" % pr['number']
    else:
        merge_message = 'has merge conflicts'
        env['sha1'] = None
    env['ghprbSourceBranch'] = pr['head']['ref']
    env['ghprbActualCommit'] = pr['head']['sha']
    env['ghprbTargetBranch'] = pr['base']['ref']
    env['ghprbPullAuthorEmail'] = pr_user['email']
    env['ghprbActualCommitAuthorEmail'] = commit_user['email']
    env['ghprbActualCommitAuthor'] = commit_user['name']
    env['ghprbPullDescription'] = "GitHub pull request #%s of commit %s, %s." % (pr['number'], pr['merge_commit_sha'], merge_message)
    return env

def get_last_poll_time():
    return None

def get_github_data(
    url,
    time_since = None,
):
    if github_get_lookuphash.get(url, None) is not None:
        return github_get_lookuphash[url]
    else:
        print url
        conn = httplib.HTTPSConnection('api.github.com')
        conn.request('GET', url, {}, {'User-Agent': 'Schmenkins'})
        # embed time_since into request HEADER
        res = conn.getresponse()
        if res.status != 200:
            print "Got an error from github api call: %s:%s" % (res.status, res.reason)
            return None
        data = json.loads(res.read())
        conn.close()
        github_get_lookuphash[url] = data
        return data

def get_events(
    repo_name,
    repo_org,
    time_since,
):
    """
    get a list of events for all pull requests that need to be actioned
    """
    # TODO starting with the repo event api, I might really want issues though...
    url = "/repos/%s/%s/events" % (repo_org, repo_name)
    return get_github_data(url, time_since)

def keep_event(
    event,
    users,
    branches,
    permit_all,
    trigger_phrase
):
    """""
    Stores the rules that we use to determine if a github event is a keeper
    """""
    #if event['type'] not in types:
    #    return False
    print event['type']
    if event['actor']['login'] not in users:
        # don't return an event if the users aren't authorized
        return False
    if permit_all:
        # if permitting all, then all pull requests and pr updates from
        # approved users should be used as events
        if event['type'] == 'PullRequestEvent':
            if event['payload']['action'] == 'opened':
                return event
            else:
                print "Unexpected PR event action %s" % event['payload']['action']
        # if we permit all, trigger for all new patches and for all updates to patches
        elif event['type'] == 'PushEvent':
            return event
    else:
        # if not permitting all, you have to match the trigger phrase, this
        # means that we only care about issues when they are created
        if event['type'] == 'IssueCommentEvent' and event['payload']['action'] == 'created':
            # does the body actually match our trigger_phrases?
            print event['payload']['comment']['body']
            if re.search(trigger_phrase, event['payload']['comment']['body']):
                return event
    return False


def get_repo_name_and_org(url):
    url_a = url.split('/')
    return [url_a.pop(), url_a.pop()]

def warn_unsupported_args(info):
    unsupported = ['org-list', 'auto-close-on-fail', 'allow-whitelist-orgs-as-admins', 'permit-all', 'github-hooks']
    for x in unsupported:
        if info.get(x):
            print "Warning, %s is not currently supported"
