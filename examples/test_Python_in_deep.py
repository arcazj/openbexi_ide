"""A runnable tour of Python 3.13, with assertions and visible results.

Run normally for every chapter, or use --chapter NAME, --list and --stream 200.
The stream option emits paced output for console scrolling experiments. This
example covers the major language constructs, not every standard-library API.
It needs only CPython 3.13; it makes no network requests and uses temporary files.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, asynccontextmanager, ExitStack
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from fractions import Fraction
from functools import lru_cache, wraps
import importlib.util
import inspect
import itertools
import json
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Protocol, runtime_checkable


CHAPTERS = {}


def chapter(function):
    CHAPTERS[function.__name__] = function
    return function


@chapter
def numbers_and_operators():
    """Integers, floats, complex, bases, arithmetic, comparison and bit operators."""
    assert 2 ** 100 > 2 ** 63 and divmod(-7, 3) == (-3, 2)
    assert 0xFF == 0b11111111 == 0o377 == 255
    assert (6 & 3, 6 | 3, 6 ^ 3, 1 << 3, 8 >> 2, ~0) == (2, 7, 5, 8, 2, -1)
    assert (2 + 3j).conjugate() == 2 - 3j and abs(3 + 4j) == 5
    assert Decimal('0.1') + Decimal('0.2') == Decimal('0.3')
    assert Fraction(1, 3) + Fraction(1, 6) == Fraction(1, 2)
    assert 1 < 2 <= 2 != 3 and round(1.234, 2) == 1.23


@chapter
def text_and_binary():
    """Unicode, escapes, formatting, slicing, bytes and writable memory views."""
    text = 'café 🐍'
    assert text.encode('utf-8').decode('utf-8') == text
    assert text[:4] == 'café' and 'abcdef'[::-2] == 'fdb'
    value = 12.345
    assert f'{value:.2f}' == '12.35' and f'{value=}' == 'value=12.345'
    assert ' a,b '.strip().split(',') == ['a', 'b']
    assert r'\n' != '\n' and '\N{GREEK SMALL LETTER PI}' == 'π'
    data = bytearray(b'ABC')
    view = memoryview(data)
    view[1] = ord('Z')
    assert bytes(data) == b'AZC'
    view.release()


@chapter
def collections_and_aliasing():
    """Lists, tuples, dictionaries, sets, identity, copying and unpacking."""
    values = [1, 2, 3]
    alias, copy = values, values[:]
    alias.append(4)
    assert alias is values and copy == [1, 2, 3]
    first, *middle, last = values
    assert (first, middle, last) == (1, [2, 3], 4)
    mapping = {'first': 1} | {'second': 2}
    assert list(mapping) == ['first', 'second'] and mapping.get('missing', 0) == 0
    assert {1, 2} & {2, 3} == {2} and {1, 2} - {2} == {1}
    assert frozenset({1, 2}) in {frozenset({1, 2})}
    del values[1:3]
    assert values == [1, 4] and (1,) + (2,) == (1, 2)


@chapter
def control_flow_and_matching():
    """if/elif, truthiness, short circuiting, loops, else, break, continue, match."""
    result = []
    for value in range(6):
        if value % 2:
            continue
        elif value == 4:
            break
        result.append(value)
    assert result == [0, 2]
    n = 2
    while n:
        n -= 1
    else:
        result.append('exhausted')
    for _ in ():
        raise AssertionError('unreachable')
    else:
        assert result[-1] == 'exhausted'
    assert ([] or 'default') == 'default' and not (False and 1 / 0)
    message = {'kind': 'point', 'values': [3, 4, 5]}
    match message:
        case {'kind': 'point', 'values': [x, y, *rest]} if x > 0:
            assert (x, y, rest) == (3, 4, [5])
        case _:
            raise AssertionError('pattern did not match')
    assert ('yes' if n == 0 else 'no') == 'yes'


@chapter
def comprehensions_and_iteration():
    """Comprehensions, assignment expressions, iterator exhaustion and itertools."""
    assert [x * x for x in range(5) if x % 2] == [1, 9]
    assert {x: x * 2 for x in range(2)} == {0: 0, 1: 2}
    assert {x % 2 for x in range(10)} == {0, 1}
    assert [size for text in ['a', 'long'] if (size := len(text)) > 2] == [4]
    assert sum(x * x for x in range(4)) == 14
    assert list(zip('ab', [1, 2], strict=True)) == [('a', 1), ('b', 2)]
    assert list(enumerate('ab', 1)) == [(1, 'a'), (2, 'b')]
    iterator = iter([7])
    assert next(iterator) == 7 and next(iterator, None) is None
    assert list(itertools.islice(itertools.count(10, 2), 3)) == [10, 12, 14]


@chapter
def functions_and_scopes():
    """Positional-only and keyword-only parameters, variadics, closures, lambda."""
    def combine(a, /, b=2, *extra, scale=1, **named):
        return (a + b + sum(extra) + sum(named.values())) * scale
    assert combine(1, 2, 3, scale=2, bonus=4) == 20
    def counter():
        value = 0
        def advance():
            nonlocal value
            value += 1
            return value
        return advance
    advance = counter()
    assert [advance(), advance()] == [1, 2]
    assert sorted(['aaa', 'b'], key=lambda value: len(value)) == ['b', 'aaa']
    assert combine(*[1, 3], **{'scale': 2}) == 8
    # Use a private module namespace to demonstrate global without altering ours.
    namespace = {}
    exec('value = 1\ndef change():\n global value\n value = 2\nchange()', namespace)
    assert namespace['value'] == 2


@chapter
def decorators_and_introspection():
    """Decorator factories, retained metadata, recursion, caching and signatures."""
    calls = []
    def record(label):
        def decorate(function):
            @wraps(function)
            def wrapped(*args, **kwargs):
                calls.append(label)
                return function(*args, **kwargs)
            return wrapped
        return decorate
    @record('sum')
    def add(a: int, b: int = 1) -> int:
        return a + b
    assert add(2) == 3 and calls == ['sum'] and add.__name__ == 'add'
    assert inspect.signature(add).parameters['b'].default == 1
    @lru_cache(maxsize=32)
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)
    assert fib(10) == 55 and fib.cache_info().hits > 0


@chapter
def generators_and_cleanup():
    """yield, send, yield from, return values, throw and deterministic close."""
    cleaned = []
    def accumulator():
        total = 0
        try:
            while True:
                total += yield total
        finally:
            cleaned.append(True)
    generator = accumulator()
    assert next(generator) == 0 and generator.send(5) == 5
    generator.close()
    assert cleaned == [True]
    def inner():
        yield 1
        return 42
    def outer():
        result = yield from inner()
        yield result
    assert list(outer()) == [1, 42]
    def recover():
        try:
            yield 'ready'
        except ValueError:
            yield 'recovered'
    generator = recover()
    assert next(generator) == 'ready' and generator.throw(ValueError('demo')) == 'recovered'
    generator.close()


@chapter
def exceptions_and_groups():
    """Custom exceptions, chaining, else/finally and split ExceptionGroup handling."""
    class InvalidRecord(ValueError):
        pass
    cleaned = []
    try:
        try:
            int('invalid')
        except ValueError as cause:
            raise InvalidRecord('bad record') from cause
    except InvalidRecord as error:
        assert isinstance(error.__cause__, ValueError)
    else:
        raise AssertionError('expected failure')
    finally:
        cleaned.append(True)
    handled = []
    try:
        raise ExceptionGroup('batch', [ValueError('value'), TypeError('type')])
    except* ValueError as group:
        handled.extend(type(e) for e in group.exceptions)
    except* TypeError as group:
        handled.extend(type(e) for e in group.exceptions)
    assert handled == [ValueError, TypeError] and cleaned == [True]


@chapter
def objects_and_data_model():
    """Inheritance, super, properties, slots, operators, protocols and class patterns."""
    class Named:
        def __init__(self, name):
            self.name = name
        def describe(self):
            return self.name
    class Sensor(Named):
        def describe(self):
            return super().describe() + ': active'
        @property
        def label(self):
            return self.name.upper()
        @classmethod
        def create(cls):
            return cls('demo')
        @staticmethod
        def units():
            return 'V'
    sensor = Sensor.create()
    assert sensor.label == 'DEMO' and sensor.describe() == 'demo: active'
    assert isinstance(sensor, Named) and sensor.units() == 'V'
    @dataclass(frozen=True, slots=True)
    class Vector:
        x: int
        y: int
        def __add__(self, other):
            return Vector(self.x + other.x, self.y + other.y)
        def __iter__(self):
            yield self.x
            yield self.y
        def __len__(self):
            return 2
    vector = Vector(1, 2) + Vector(3, 4)
    assert tuple(vector) == (4, 6) and len(vector) == 2
    match vector:
        case Vector(4, y):
            assert y == 6
        case _:
            raise AssertionError('class pattern failed')


@chapter
def descriptors_and_metaclasses():
    """Descriptor validation, __set_name__, metaclasses and subclass registration."""
    class Positive:
        def __set_name__(self, owner, name):
            self.storage = '_' + name
        def __get__(self, instance, owner=None):
            return self if instance is None else getattr(instance, self.storage)
        def __set__(self, instance, value):
            if value <= 0:
                raise ValueError('must be positive')
            setattr(instance, self.storage, value)
    class Tagged(type):
        def __new__(mcls, name, bases, namespace):
            namespace['tag'] = name.lower()
            return super().__new__(mcls, name, bases, namespace)
    children = []
    class Device(metaclass=Tagged):
        rate = Positive()
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__(**kwargs)
            children.append(cls.__name__)
    class Probe(Device):
        pass
    probe = Probe()
    probe.rate = 5
    assert probe.rate == 5 and probe.tag == 'probe' and children == ['Probe']
    try:
        probe.rate = 0
    except ValueError:
        assert probe.rate == 5
    else:
        raise AssertionError('descriptor accepted zero')


@chapter
def types_dataclasses_and_enums():
    """Generic classes/functions, type aliases, runtime protocols and enum patterns."""
    type Pair[T] = tuple[T, T]
    class Box[T]:
        def __init__(self, value: T):
            self.value = value
    def first[T](values: list[T]) -> T:
        return values[0]
    @runtime_checkable
    class Readable(Protocol):
        def read(self) -> str: ...
    @dataclass
    class Record:
        tags: list[str] = field(default_factory=list)
        def read(self):
            return ','.join(self.tags)
    class State(Enum):
        IDLE = auto()
        READY = auto()
    left, right = Record(), Record()
    left.tags.append('a')
    assert not right.tags and isinstance(left, Readable) and left.read() == 'a'
    assert Box[int](7).value == first([7, 8]) and Pair.__name__ == 'Pair'
    assert State['READY'] is State.READY and len(State) == 2


@chapter
def contexts_files_and_imports():
    """with, ExitStack, cleanup on errors, pathlib, UTF-8, JSON and module loading."""
    events = []
    @contextmanager
    def resource():
        events.append('open')
        try:
            yield 'handle'
        finally:
            events.append('close')
    with tempfile.TemporaryDirectory(prefix='python-in-depth-') as folder:
        root = Path(folder)
        with ExitStack() as stack:
            assert stack.enter_context(resource()) == 'handle'
            stream = stack.enter_context((root / 'data.json').open('w', encoding='utf-8'))
            json.dump({'text': 'café', 'values': [1, 2]}, stream, ensure_ascii=False)
        assert json.loads((root / 'data.json').read_text(encoding='utf-8'))['text'] == 'café'
        module_file = root / 'lesson_module.py'
        module_file.write_text('ANSWER = 6 * 7\n', encoding='utf-8')
        spec = importlib.util.spec_from_file_location('lesson_module', module_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.ANSWER == 42
        try:
            with resource():
                raise RuntimeError('exercise cleanup')
        except RuntimeError:
            pass
    assert events == ['open', 'close', 'open', 'close'] and not root.exists()


@chapter
def asynchronous_python():
    """Coroutines, await, async with/for, TaskGroup, async generators, cancellation."""
    async def exercise():
        events = []
        @asynccontextmanager
        async def resource():
            try:
                yield 'connected'
            finally:
                events.append('closed')
        async def numbers():
            for i in range(3):
                await asyncio.sleep(0)
                yield i
        async def square(value):
            await asyncio.sleep(0)
            return value * value
        async with resource() as handle:
            assert handle == 'connected'
            assert [i async for i in numbers()] == [0, 1, 2]
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(square(i)) for i in range(4)]
            assert [task.result() for task in tasks] == [0, 1, 4, 9]
        started = asyncio.Event()
        async def pending():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                events.append('cancelled')
        task = asyncio.create_task(pending())
        await started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert events == ['closed', 'cancelled']
    asyncio.run(exercise())


@chapter
def threads_and_standard_library():
    """Thread ownership, locks, futures, collections, regex and deterministic cleanup."""
    lock = threading.Lock()
    totals = Counter()
    def work(value):
        with lock:
            totals['completed'] += 1
        return value * value
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(work, range(8))) == [0, 1, 4, 9, 16, 25, 36, 49]
    assert totals['completed'] == 8
    bounded = deque(range(5), maxlen=3)
    assert list(bounded) == [2, 3, 4]
    assert re.findall(r'\b[A-Z]+\d+\b', 'TM1 ok TC22') == ['TM1', 'TC22']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List chapters without running them')
    parser.add_argument('--chapter', choices=tuple(CHAPTERS), action='append')
    parser.add_argument('--stream', type=int, default=0, metavar='LINES')
    parser.add_argument('--delay', type=float, default=.05, help='Seconds between stream lines')
    args = parser.parse_args(argv)
    if not 0 <= args.stream <= 100_000 or not 0 <= args.delay <= 10:
        parser.error('stream must be 0..100000 and delay must be 0..10')
    if not __debug__:
        parser.error('Run without -O so the example assertions remain active')
    selected = args.chapter or list(CHAPTERS)
    for name in selected:
        function = CHAPTERS[name]
        print(f'\n{name}: {function.__doc__}', flush=True)
        if not args.list:
            function()
            print('  PASS', flush=True)
    if not args.list:
        print(f'\nPython in depth: {len(selected)} chapters passed.', flush=True)
        for number in range(args.stream):
            print(f'Live output {number + 1:06d}/{args.stream:06d} — scroll, select, then choose Latest output.', flush=True)
            time.sleep(args.delay)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
