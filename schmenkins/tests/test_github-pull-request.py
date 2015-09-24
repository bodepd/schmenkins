import mock
import unittest
import importlib

class SchmenkinsTriggerPrb(unittest.TestCase):
    def setUp(self, *args, **kwargs):
        self.plugin = importlib.import_module('schmenkins.triggers.github-pull-request')
    def test_poll(self):
        with mock.patch.object(self.plugin, 'get_events') as events:
            events.return_value = [
                {
                    u'type': u'PullRequestEvent',
                    u'actor': {u'login': u'bodepd'},
                    u'payload': {u'action': 'opened'}
                },
                {
                    u'type': u'PushEvent',
                    u'actor': {u'login': u'bodepd'}
                },
                {
                    u'type': u'IssueCommentEvent',
                    u'actor': {u'login': u'bodepd'},
                    u'payload': {u'action': 'created', u'comment': {u'body': 'test'}}
                },
                {
                    u'type': u'IssueCommentEvent',
                    u'actor': {u'login': u'dan'},
                    u'payload': {u'action': 'created', u'comment': {u'body': 'test'}}
                },
                {
                    u'type': u'IssueCommentEvent',
                    u'actor': {u'login': u'bode'},
                    u'payload': {u'action': 'created', u'comment': {u'body': 'test'}}
                }
            ]
            # should pull out admin events with trigger-phrase
            #test_data = {'admin-list': ['bodepd'], 'permit-all': False, 'trigger-phrase': 'test'}
            #x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data)
            #self.assertEquals(len(x), 1)
            #test_data = {'admin-list': ['bodepd'], 'permit-all': True}
            #x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data)
            #self.assertEquals(len(x), 2)
        test_data = {'admin-list': ['bodepd'], 'permit-all': True, 'trigger-phrase': 'test'}
        x = self.plugin.poll('http://github.com/bodepd/test_repo', test_data)
