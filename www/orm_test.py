#!/usr/bin/env python3
# _*_ coding: utf-8 _*_

__author__ = 'acezen(Ace Zeng)'


import asyncio
import orm
from models import User, Blog, Comment

@asyncio.coroutine
def test_save(loop):
    yield from orm.create_pool(loop, user='www-data', password='www-data', db='awesome')

    u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')

    yield from u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test_save(loop))
loop.close()
