import mock
import unittest
import importlib
from contextlib import nested
import json
import os
import copy

class SchmenkinsTriggerPrb(unittest.TestCase):
    def setUp(self, *args, **kwargs):
        self.plugin = importlib.import_module('schmenkins.triggers.github-pull-request')
    def test_poll(self):
        def github_calls(*args, **kwargs):
            if args[0] == 'https://api.github.com/users/bodepd':
                return {'name': 'Dan', 'email': 'bodepd@gmails.com'}
            elif args[0] == 'pr_url_1':
                return {
                    'head': {'user': {'url': 'https://api.github.com/users/bodepd'}, 'ref': 'head/ref', 'sha': 'sha'},
                    'base': {'ref': '234'},
                    'user': {'url': 'https://api.github.com/users/bodepd'},
                    'number': '11',
                    'url': 'pr_url_result',
                    'title': 'pr_title',
                    'merge_commit_sha': '123',
                }
            elif args[0] == 'https://api.github.com/repos/bodepd/test_repo/pulls?head=bodepd:patch':
                return [{
                    'head': {'user': {'url': 'https://api.github.com/users/bodepd'}, 'ref': 'head/ref', 'sha': 'sha'},
                    'base': {'ref': '234'},
                    'user': {'url': 'https://api.github.com/users/bodepd'},
                    'number': '11',
                    'url': 'pr_url_result',
                    'title': 'pr_title',
                    'merge_commit_sha': '123',
                }]
            else:
                return None
        with nested(
            mock.patch.object(self.plugin, 'get_events'),
            mock.patch.object(self.plugin, 'get_github_data')
        ) as (events, data):
            data.side_effect = github_calls
            # create a shit-ton of github data
            pr_event = {
                'id': '1',
                'created_at': '2015-10-13T17:56:30Z',
                u'type': u'PullRequestEvent',
                u'actor': {u'login': u'bodepd', 'url': 'https://api.github.com/users/bodepd'},
                u'payload': {u'action': 'opened', 'pull_request': {'url': 'pr_url_1'}}
            }
            push_event = {

                'id': '2',
                'created_at': '2015-10-13T17:56:30Z',
                u'type': u'PushEvent',
                u'actor': {u'login': u'bodepd', 'url': 'https://api.github.com/users/bodepd'},
                u'payload': {u'action': 'created', u'comment': {u'body': 'test'}, 'ref': 'refs/heads/patch', "head": "75fa92144119b1f23217a99fbaca64af77d0ff41"},
                "repo": {"id": 8662629,
                         "name": "bodepd/test_repo",
                         "url": "https://api.github.com/repos/bodepd/test_repo"}
            }
            issue_comment = {
                'id': '5',
                'created_at': '2015-10-13T17:56:30Z',
                u'type': u'IssueCommentEvent',
                u'actor': {u'login': u'bodepd'},
                u'payload': {u'action': 'created', u'comment': {u'body': 'test', 'user':{'url': 'https://api.github.com/users/bodepd'}}, 'issue': {'pull_request': {'url': 'pr_url_1'}, 'user': {'url': 'https://api.github.com/users/bodepd'}}}
            }
            # test 1 - a valid issue comment should generate an event
            events.return_value = [issue_comment]
            test_data = {'admin-list': ['bodepd'], 'permit-all': False, 'trigger-phrase': 'test'}
            x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data, None)
            self.assertEquals(x, [{'time': '2015-10-13T17:56:30Z', 'mergeable': True, 'build_params': {'sha1': 'origin/pr/11/merge', 'ghprbPullDescription': 'GitHub pull request #11 of commit 123, no merge conflicts.', 'merge_commit_sha1': '123', 'ghprbPullTitle': 'pr_title', 'ghprbSourceBranch': 'head/ref', 'ghprbActualCommit': 'sha', 'ghprbPullAuthorEmail': 'bodepd@gmails.com', 'ghprbPullLink': 'pr_url_result', 'ghprbActualCommitAuthor': 'Dan', 'ghprbTriggerAuthor': 'Dan', 'ghprbTargetBranch': '234', 'ghprbPullId': '11', 'ghprbTriggerAuthorEmail': 'bodepd@gmails.com', 'ghprbActualCommitAuthorEmail': 'bodepd@gmails.com'}, 'id': '5'}])
            # update the issue string
            test_data = {'admin-list': ['bodepd'], 'permit-all': False, 'trigger-phrase': 'blah'}
            x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data, None)
            self.assertEquals(x, [])
            # if admin list does not match
            test_data = {'admin-list': ['bode'], 'permit-all': False, 'trigger-phrase': 'test'}
            x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data, None)
            self.assertEquals(x, [])
            # if trigger-phrase regex mathes
            test_data = {'admin-list': ['bodepd'], 'permit-all': False, 'trigger-phrase': 't'}
            x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data, None)
            self.assertEquals(len(x), 1)
            invalid_issue = copy.deepcopy(issue_comment)
            invalid_issue['actor']['login'] = 'dan'
            events.return_value = [issue_comment, invalid_issue]
            self.assertEquals(len(x), 1)
            # permit all current means use push events and pr events, but not
            # issue comments
            events.return_value = [issue_comment, issue_comment]
            test_data = {'admin-list': ['bodepd'], 'permit-all': False, 'trigger-phrase': 'test'}
            x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data, None)
            # should ignore issue comments
            self.assertEquals(len(x), 2)
            events.return_value = [pr_event, push_event]
            test_data = {'admin-list': ['bodepd'], 'permit-all': True}
            x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data, None)
            self.assertEquals(len(x), 2)

