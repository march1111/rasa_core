from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import json

import pytest
from builtins import str
from httpretty import httpretty

from rasa_core.actions import action
from rasa_core.actions.action import (
    ActionRestart, UtterAction,
    ActionListen, RemoteAction)
from rasa_core.domain import Domain
from rasa_core.events import Restarted, SlotSet, UserUtteranceReverted
from rasa_core.trackers import DialogueStateTracker
from rasa_core.utils import EndpointConfig


def test_restart(default_dispatcher_collecting, default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)
    events = ActionRestart().run(default_dispatcher_collecting, tracker,
                                 default_domain)
    assert events == [Restarted()]


def test_text_format():
    assert "{}".format(ActionListen()) == \
           "Action('action_listen')"
    assert "{}".format(UtterAction("my_action_name")) == \
           "UtterAction('my_action_name')"


def test_action_instantiation_from_names():
    instantiated_actions = action.actions_from_names(
            ["random_name", "utter_test"], None, ["random_name", "utter_test"])
    assert len(instantiated_actions) == 2
    assert isinstance(instantiated_actions[0], RemoteAction)
    assert instantiated_actions[0].name() == "random_name"

    assert isinstance(instantiated_actions[1], UtterAction)
    assert instantiated_actions[1].name() == "utter_test"


def test_domain_action_instantiation():
    domain = Domain(
            intent_properties={},
            entities=[],
            slots=[],
            templates={},
            action_names=["my_module.ActionTest", "utter_test"])

    instantiated_actions = domain.actions(None)

    assert len(instantiated_actions) == 5
    assert instantiated_actions[0].name() == "action_listen"
    assert instantiated_actions[1].name() == "action_restart"
    assert instantiated_actions[2].name() == "action_default_fallback"
    assert instantiated_actions[3].name() == "my_module.ActionTest"
    assert instantiated_actions[4].name() == "utter_test"


def test_domain_fails_on_duplicated_actions():
    with pytest.raises(ValueError):
        Domain(intent_properties={},
               entities=[],
               slots=[],
               templates={},
               action_names=["random_name", "random_name"])


def test_remote_action_runs(default_dispatcher_collecting, default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)

    endpoint = EndpointConfig("https://abc.defg/webhooks/actions")
    remote_action = action.RemoteAction("my_action",
                                        endpoint)

    httpretty.register_uri(
            httpretty.POST,
            'https://abc.defg/webhooks/actions',
            body='{"events": [], "responses": []}')

    httpretty.enable()
    remote_action.run(default_dispatcher_collecting,
                      tracker,
                      default_domain)
    httpretty.disable()

    assert (httpretty.latest_requests[-1].path ==
            "/webhooks/actions")

    b = httpretty.latest_requests[-1].body.decode("utf-8")

    assert json.loads(b) == {
        'domain': default_domain.as_dict(),
        'next_action': 'my_action',
        'sender_id': 'default',
        'tracker': {
            'latest_message': {
                'entities': [],
                'intent': {},
                'text': None
            },
            'sender_id': 'default',
            'paused': False,
            'latest_event_time': None,
            'followup_action': 'action_listen',
            'slots': {'name': None},
            'events': []
        }
    }


def test_remote_action_logs_events(default_dispatcher_collecting,
                                   default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)

    endpoint = EndpointConfig("https://abc.defg/webhooks/actions")
    remote_action = action.RemoteAction("my_action",
                                        endpoint)

    response = {
        "events": [
            {"event": "slot", "value": "rasa", "name": "name"}],
        "responses": [{"text": "test text",
                       "buttons": [{"title": "cheap", "payload": "cheap"}]},
                      {"template": "utter_greet"}]}

    httpretty.register_uri(
            httpretty.POST,
            'https://abc.defg/webhooks/actions',
            body=json.dumps(response))

    httpretty.enable()
    events = remote_action.run(default_dispatcher_collecting,
                               tracker,
                               default_domain)
    httpretty.disable()

    assert (httpretty.latest_requests[-1].path ==
            "/webhooks/actions")

    b = httpretty.latest_requests[-1].body.decode("utf-8")

    assert json.loads(b) == {
        'domain': default_domain.as_dict(),
        'next_action': 'my_action',
        'sender_id': 'default',
        'tracker': {
            'latest_message': {
                'entities': [],
                'intent': {},
                'text': None
            },
            'sender_id': 'default',
            'paused': False,
            'followup_action': 'action_listen',
            'latest_event_time': None,
            'slots': {'name': None},
            'events': []
        }
    }

    assert events == [SlotSet("name", "rasa")]

    channel = default_dispatcher_collecting.output_channel
    assert channel.messages == [
        {"text": "test text", "recipient_id": "my-sender",
         "buttons": [{"title": "cheap", "payload": "cheap"}]},
        {"text": "hey there None!", "recipient_id": "my-sender"}]


def test_remote_action_wo_endpoint(default_dispatcher_collecting,
                                   default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)

    remote_action = action.RemoteAction("my_action", None)

    with pytest.raises(Exception) as execinfo:
        remote_action.run(default_dispatcher_collecting,
                          tracker,
                          default_domain)
    assert "you didn't configure an endpoint" in str(execinfo.value)


def test_remote_action_endpoint_not_running(default_dispatcher_collecting,
                                            default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)

    endpoint = EndpointConfig("https://abc.defg/webhooks/actions")
    remote_action = action.RemoteAction("my_action", endpoint)

    with pytest.raises(Exception) as execinfo:
        remote_action.run(default_dispatcher_collecting,
                          tracker,
                          default_domain)
    assert "Failed to execute custom action." in str(execinfo.value)


def test_remote_action_endpoint_responds_500(default_dispatcher_collecting,
                                             default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)

    endpoint = EndpointConfig("https://abc.defg/webhooks/actions")
    remote_action = action.RemoteAction("my_action", endpoint)

    httpretty.register_uri(
            httpretty.POST,
            'https://abc.defg/webhooks/actions',
            status=500,
            body='')

    httpretty.enable()
    with pytest.raises(Exception) as execinfo:
        remote_action.run(default_dispatcher_collecting,
                          tracker,
                          default_domain)
    httpretty.disable()
    assert "Failed to execute custom action." in str(execinfo.value)


def test_default_action(default_dispatcher_collecting,
                        default_domain):
    tracker = DialogueStateTracker("default",
                                   default_domain.slots)

    fallback_action = action.ActionDefaultFallback()

    events = fallback_action.run(default_dispatcher_collecting,
                                 tracker,
                                 default_domain)

    channel = default_dispatcher_collecting.output_channel
    assert channel.messages == [
        {u'text': u'default message', u'recipient_id': u'my-sender'}]
    assert events == [UserUtteranceReverted()]
