#!/usr/bin/env python3
# _*_ coding: utf-8 _*_

__author__ = 'acezen(Ace Zeng)'


import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

from apis import APIError

# 装饰器get和post, 用于增加__method__和__route__属性
def get(path):
    '''
    Define decorator @get('/path')
    '''
    def decorator(func):
        @functools.wraps(func):
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

def post(path):
    '''
    Define decorator @post('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

# inspect.Parameter可类型有以下：
# POSITIONAL_ONLY  只能是位置参数
# POSITIONAL_OR_KEYWORD 可以是位置参数或关键字参数
# VAR_POSITIONAL 相当于 *args
# KEYWORD_ONLY  关键字参数且提供可key，相当于*, key
# VAR_KEYWORD 相当于 **kw

# Parameter.default

# 当前函数判断fn的参数位置是否正确
def get_required_kw_args(fn):
    '''
    获取必须的关键字参数
    '''
    args = []
    # 返回一个包含inspect.Parameter类型的dict
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.empty:
            args.append(name)
    return tuple(args)

def get_named_kw_args(fn):
    '''
    获取关键字参数
    '''
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
        return tuple(args)

def has_named_kw_args(fn):
    '''
    判断是否需要关键字参数
    '''
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

def has_var_kw_arg(fn):
    '''
    判断是否有**kw参数
    '''
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

def has_request_arg(fn):
    '''
    判断request参数是否存在并且是否在其他参数之后
    '''
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
    return found

# RequestHandler从URL函数中分析其所需要接收的参数，从request中获取必要的参数，
# 调用URL函数，然后把结果转换为web.Response对象，这样，就完全符合aiohttp框架的要求了

class RequestHandler(object):

    def __init__(self, app, fn):
        self._app = app
        self._func = fn 
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_args(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._name_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    # __call__:
    # kw: 保存参数
    # 判断request对象是否存在参数，如存在则根据POST还是GET方法将内容保存到kw
    # 判断之后如kw为空（说明request没有传递参数)， 则将match_info列表里的资源映射表传给kw,
    # 如果不为空则把命名关键字参数内容给kw
    # 完善
    @asyncio.coroutine
    def __call__(self, request):
        kw = None
        # 有无参数
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                # POST方法的解析参数
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = yield from request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = yield from request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
                if request.method == 'GET':
                    # GET方法下的参数解析
                    qs = request.query_string
                    if qs:
                        kw = dict()
                        for k, v in parse.parse_qs(qs, True).items():
                            kw[k] = v[0]
                if kw is None:
                    # kw为空，取request.match_info
                    kw = dict(**request.match_info)
                else:
                    if not self._has_var_kw_arg and self._name_kw_args:
                        # remove all unamed kw:
                        copy = dict()
                        for name in self._named_kw_args:
                            if name in kw:
                                copy[name] = kw[name]
                        kw = copy
                    # check named arg:
                    for k, v in request.match_info.items():
                        if k in kw:
                            logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                        kw[k] = v

                if self._has_request_arg:
                    kw['request'] = request
                # check required kw:
                if self._required_kw_args:
                    for name in self._required_kw_args:
                        if not name in kw:
                            return web.HTTPBadRequest('Missing argument: %s' % name)

                logging.info('call with args: %s' % str(kw))
                try:
                    r = yield from self._func(**kw)
                    return r
                except APIError as e:
                    return dict(error=e.error, data=e.data, message=e.message)

# 添加静态页面的路径：
def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))

def add_router(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))

    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)

    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', 'join(inspect.signature(fn).parameters.key())))
    app.router.add_route(method, path, RequestHandler(app, fn))

def add_routes(app, module_name):
    n = module_name.rfind('.')
    if n == (-1):
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)

    for attr in dir(mod):
        if attr.startswith('_'):
            continue

        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)
