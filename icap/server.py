__all__ = [
    'hooks',
    'run',
    'stop',
]


class Hooks(dict):
    """Dispatch class for providing hooks at certain parts of the ICAP
    transaction.

    Used like so:

    >>> from icap import hooks
    >>> @hooks('options_headers')
    >>> def extra_headers():
    ...     return {'new': 'headers'}


    Available hooks:
        options_headers:
            Return dictionary of additional headers to add to the OPTIONS
            response.

            arguments: None.

        is_tag:
            Return a string to be used for a custom ISTag header on the
            response. String will be sliced to maximum of 32 bytes.

            arguments: request object, may be None.

        before_handling:
            Called with an ICAP request before it is passed to a handler.

            arguments: ICAP request object.

        before_serialization:
            Called with an ICAP request and response before serializing the
            response.

            arguments: ICAP request object, ICAP response object.

    """
    def __getitem__(self, name):
        """Return the callable hook matching *name*.

        Always returns a callable that won't raise an exception.

        """

        if name in self:
            func, default = dict.__getitem__(self, name)
        else:
            func = lambda *args: None
            default = None

        def safe_callable(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                return default
        return safe_callable

    def __call__(self, name, default=None, override=False):
        """Register a hook function with *name*, and *default* return value.

        Unless *override* is True, then *default* will only be saved the for
        the first time. This is to ensure sane defaults are used in the event
        that an error occurs in the registered hook.

        """
        # we want to keep the original default, as it will be used if the new
        # one fails, e.g. for the ISTag header.
        if name in self and not override:
            _oldfunc, default = dict.__getitem__(self, name)

        def wrapped(func):
            self[name] = func, default
        return wrapped


hooks = Hooks()

_server = None

def run(host='127.0.0.1', port=1334, *, factory_class=None, **kwargs):
    """Run the ICAP server.

    Keyword arguments:
        ``host`` - the interface to use. Defaults to listening locally only.
        ``port`` - the port to listen on.
        ``factory_class`` - the callable to use for creating new protocols.
                            Defauls to `~icap.asyncio.ICAPProtocolFactory`.

        Any other keyword arguments will be passed to ``factory_class`` before
        starting the server. See `~icap.asyncio.ICAPProtocolFactory` for
        accepted values.

    """
    global _server

    if factory_class is None:
        from .asyncio import ICAPProtocolFactory
        factory_class = ICAPProtocolFactory

    from .criteria import sort_handlers
    sort_handlers()

    factory = factory_class(**kwargs)

    loop = asyncio.get_event_loop()
    f = loop.create_server(factory, host, port)
    _server = loop.run_until_complete(f)

    loop.run_forever()


def stop():
    """Stop the server. Assumes it is already running."""
    global server
    assert _server is not None
    _server.close()
    _serevr = None
