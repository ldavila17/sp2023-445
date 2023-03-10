#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Christian Maugg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.



CHANGELOG
=========

1.2
===
* exceptions in an event-decorated function are now reraised when no transition failure handler was
registered

1.1
===
* added a decorator for registering a class' method as exception handler when an 'event'-decorated method
fails. multiple methods may be registered as transition failure handler: they are invoked in the order
given by the optional 'calling_sequence' keyword

1.0
===
* first public release
"""

import functools
import inspect

__author__ = 'Christian Maugg <software@christianmaugg.de>'
__version__ = version = '1.2'


class InvalidStateTransition(Exception):
    pass


class StateInfo(object):

    @staticmethod
    def get_states(cls):
        if not inspect.isclass(cls):
            raise TypeError('"{0}" is no class object!'.format(cls))
        if not hasattr(cls, '___pystatemachine_cls_states'):
            states = tuple(state for _, state in inspect.getmembers(cls, lambda member: isinstance(member, State)))
            setattr(cls, '___pystatemachine_cls_states', states)
        return getattr(cls, '___pystatemachine_cls_states')

    @staticmethod
    def get_initial_state(cls):
        if not inspect.isclass(cls):
            raise TypeError('"{0}" is no class object!'.format(cls))
        if not hasattr(cls, '___pystatemachine_cls_initial_state'):
            states = StateInfo.get_states(cls)
            initial_states = [state for state in states if state.is_initial]
            assert initial_states, 'no initial state found!'
            assert len(initial_states) == 1, 'found multiple initial states! initial states: {0}'.format(
                ' ,'.join(str(state) for state in initial_states))
            initial_state = initial_states[0]
            setattr(cls, '___pystatemachine_cls_initial_state', initial_state)
        return getattr(cls, '___pystatemachine_cls_initial_state')

    @staticmethod
    def get_current_state(obj):
        if not hasattr(obj, '___pystatemachine_obj_current_state'):
            initial_state = StateInfo.get_initial_state(obj.__class__)
            setattr(obj, '___pystatemachine_obj_current_state', initial_state)
        return getattr(obj, '___pystatemachine_obj_current_state')

    @staticmethod
    def set_current_state(obj, state):
        assert isinstance(state, State), 'invalid state type!'
        setattr(obj, '___pystatemachine_obj_current_state', state)


class State(object):

    def __init__(self, name, initial=False):
        super(State, self).__init__()
        self.is_initial = True if initial else False
        self.name = name.upper()

    def __str__(self):
        return '<{0}.State[{1}] object at 0x{2:X}>'.format(__name__, self.name, id(self))


def event(from_states=None, to_state=None):
    """ a decorator for transitioning from certain states to a target state. must be used on bound methods of a class
    instance, only. """
    from_states_tuple = (from_states, ) if isinstance(from_states, State) else tuple(from_states or [])
    if not len(from_states_tuple) >= 1:
        raise ValueError()
    if not all(isinstance(state, State) for state in from_states_tuple):
        raise TypeError()
    if not isinstance(to_state, State):
        raise TypeError()

    def wrapper(wrapped):

        @functools.wraps(wrapped)
        def transition(instance, *a, **kw):
            if instance.current_state not in from_states_tuple:
                print(instance.current_state,from_states_tuple)
                raise InvalidStateTransition()
            try:
                result = wrapped(instance, *a, **kw)
            except Exception as error:
                error_handlers = getattr(instance, '___pystatemachine_transition_failure_handlers', [])
                for error_handler in error_handlers:
                    error_handler(instance, wrapped, instance.current_state, to_state, error)
                if not error_handlers:
                    raise error
            else:
                StateInfo.set_current_state(instance, to_state)
                return result

        return transition

    return wrapper


def transition_failure_handler(calling_sequence=0):
    def wrapper(wrapped):
        setattr(wrapped, '___pystatemachine_is_transition_failure_handler', True)
        setattr(wrapped, '___pystatemachine_transition_failure_handler_calling_sequence', int(calling_sequence))
        return wrapped

    return wrapper


def acts_as_state_machine(cls):
    """
    a decorator which sets two properties on a class:
        * the 'current_state' property: a read-only property, returning the state machine's current state, as 'State' object
        * the 'states' property: a tuple of all valid state machine states, as 'State' objects
    class objects may use current_state and states freely
    :param cls:
    :return:
    """
    assert not hasattr(cls, 'current_state'), '{0} already has a "current_state" attribute!'.format(cls)
    assert not hasattr(cls, 'states'), '{0} already has a "states" attribute!'.format(cls)

    def get_states(obj):
        return StateInfo.get_states(obj.__class__)

    def is_transition_failure_handler(obj):
        return all([
            any([
                inspect.ismethod(obj),  # python2
                inspect.isfunction(obj),  # python3
            ]),
            getattr(obj, '___pystatemachine_is_transition_failure_handler', False),
        ])

    transition_failure_handlers = sorted(
        [value for name, value in inspect.getmembers(cls, is_transition_failure_handler)],
        key=lambda m: getattr(m, '___pystatemachine_transition_failure_handler_calling_sequence', 0),
    )
    setattr(cls, '___pystatemachine_transition_failure_handlers', transition_failure_handlers)
    cls.current_state = property(fget=StateInfo.get_current_state)
    cls.states = property(fget=get_states)
    return cls


if __name__ == '__main__':
    @acts_as_state_machine
    class Turnstile(object):
        locked = State('locked', initial=True)
        unlocked = State('unlocked')

        @event(from_states=(locked, unlocked), to_state=unlocked)
        def coin(self):
            assert random.random() > .5, 'failing for demonstration purposes, only ..'
            print('*blingbling* .. unlocked!')

        @event(from_states=(locked, unlocked), to_state=locked)
        def push(self):
            print('*push* .. locked!')

        @transition_failure_handler(calling_sequence=2)
        def turnstile_malfunction(self, method, from_state, to_state, error):
            print('state transition from {0.name} to {1.name} failed. Reason: {2}'.format(from_state, to_state, error))

        @transition_failure_handler(calling_sequence=1)
        def before_turnstile_malfunction(self, method, from_state, to_state, error):
            print('before state transition failure handler ..')

    import random

    turnstile = Turnstile()
    for _ in range(10):
        handler = random.choice([turnstile.coin, turnstile.push])
        handler()
