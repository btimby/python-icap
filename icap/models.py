"""
Various high-level classes representing HTTP and ICAP messages and parts
comprising them.

"""

from collections import namedtuple, OrderedDict
from urllib.parse import urlencode, parse_qs, urlparse
from http.cookies import SimpleCookie
from datetime import datetime, timedelta

from werkzeug import cached_property, parse_options_header

from .errors import (
    icap_response_codes,
    http_response_codes)

from .parsing import ICAPRequestParser


class RequestLine(namedtuple('RequestLine', 'method uri version')):
    """Parsed request line, e.g. GET / HTTP/1.1, or
    REQMOD / ICAP/1.1.

    Available attributes are ``method``, ``uri``, ``version`` and ``query``.

    This class is purposefully directly immutable. You may modify the
    attributes on the `uri` attribute all you want; they will be reserialized.

    You can replace attributes by constructing new instances from the old ones,
    like a namedtuple. For example:

    >>> from icap import RequestLine
    >>> RequestLine('GET', '/', 'HTTP/1.1')._replace(method='POST')
    RequestLine(method='POST', uri=ParseResult(scheme='', netloc='', path='/',
                params='', query={}, fragment=''), version='HTTP/1.1')

    But generally, try to restrict yourself to query parameter changes only,
    which don't involve this kludgery. It's generally poor form to change HTTP
    versions, and changing the method is very impolite.
    """
    __slots__ = ()

    # we're subclassing a tuple here, __new__ is necessary.
    def __new__(self, method, uri, version):
        uri = urlparse(uri)
        uri = uri._replace(query=parse_qs(uri.query))
        return super().__new__(self, method, uri, version)

    def __bytes__(self):
        method, uri, version = self
        uri = uri._replace(query=urlencode(uri.query, doseq=True)).geturl()
        return ' '.join([method, uri, version]).encode('utf8')

    @property
    def query(self):
        """Proxy attribute for ``self.uri.query``.

        Returns a reference, so modifications to the query via this property
        will be reserialised.

        """
        return self.uri.query


class StatusLine(namedtuple('StatusLine', 'version code reason')):
    """Parsed status line, e.g. HTTP/1.1 200 OK or ICAP/1.1 200 OK.

    This class is purposefully directly immutable.

    You can replace attributes by constructing new instances from the old ones,
    like a namedtuple. For example:

    >>> from icap import StatusLine
    >>> StatusLine('HTTP/1.1', '200', 'OK')._replace(version='ICAP/1.1')
    StatusLine(version='ICAP/1.1', code=200, reason='OK')

    But **don't do it without a good reason**. It's generally poor form to
    change these sorts of things.

    Instances can also be constructed without the ``reason`` attribute
    fulfilled. In these cases, it will be filled out from
    `icap.errors.icap_response_codes` or `icap.errors.http_response_codes`:

    >>> from icap import StatusLine
    >>> StatusLine('HTTP/1.1', '204')
    StatusLine(version='HTTP/1.1', code=204, reason='No Content')
    """
    __slots__ = ()

    def __new__(self, version, code, *args):
        code = int(code)
        if args:
            reason, = args
        elif version.startswith('HTTP'):
            reason = http_response_codes[code]
        else:
            reason = icap_response_codes[code]

        return super().__new__(self, version, code, reason)

    def __bytes__(self):
        return ' '.join(map(str, self)).encode('utf8')


class HeadersDict(OrderedDict):
    """Multivalue, case-aware dictionary type used for headers of requests and
    responses.

    """
    def __init__(self, items=()):
        OrderedDict.__init__(self)
        for key, value in items:
            self[key] = value

    def __setitem__(self, key, value):
        """Append``value`` to the list stored at ``key``, case insensitively.

        The case of ``key`` is preserved internally for later use.

        """
        key = self._checktype(key)
        value = self._checktype(value)
        lkey = key.lower()

        if lkey not in self:
            OrderedDict.__setitem__(self, lkey, [(key, value)])
        else:
            OrderedDict.__getitem__(self, lkey).append((key, value))

    def _checktype(self, value):
        if isinstance(value, bytes):
            return value.decode('utf8')
        elif isinstance(value, str):
            return value
        else:
            raise TypeError("Value must be of type 'str' or 'bytes', "
                            "received '%s'" % type(value))

    def __delitem__(self, key):
        OrderedDict.__delitem__(self, key.lower())

    def __getitem__(self, key):
        """Return the first value stored at ``key``."""
        return OrderedDict.__getitem__(self,
                                       self._checktype(key).lower())[0][1]

    def __contains__(self, key):
        """Check if header ``key`` is present. Case insensitive."""
        return OrderedDict.__contains__(self, self._checktype(key).lower())

    def get(self, key, default=None):
        """Return the first value stored at ``key``. Return ``default`` if no
        value is present."""
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def getlist(self, key, default=list):
        """Return all values stored at ``key``."""
        try:
            return [v for k, v in OrderedDict.__getitem__(self, key.lower())]
        except KeyError:
            return default()

    def pop(self, key, *args, **kwargs):
        return OrderedDict.pop(self, key.lower(), *args, **kwargs)

    def replace(self, key, value):
        """Replace all values at `key` with `value`."""
        lkey = key.lower()
        OrderedDict.__setitem__(self, lkey, [(key, value)])

    def __eq__(self, other):
        if list(self.keys()) != list(other.keys()):
            return False

        for key in list(self.keys()):
            value = OrderedDict.__getitem__(self, key)
            ovalue = OrderedDict.__getitem__(other, key)

            if value != ovalue:
                return False

        return True

    def __bytes__(self):
        """Return a string of the headers, suitable for writing to a stream."""
        if not self:
            return b''

        s = b'\r\n'.join(
            ': '.join(v).encode('utf8') for k in self
            for v in OrderedDict.__getitem__(self, k)
        ) + b'\r\n'

        return s


class ICAPMessage(object):
    """Base ICAP class for generalising certain properties of both requests and
    responses.

    Should not be used directly - use `~icap.models.ICAPRequest` or
    `~icap.models.ICAPResponse` instead.

    """
    def __init__(self, headers=None, http=None):
        """If ``headers`` is not given, default to an empty instance of
        `~icap.models.HeadersDict`.

        ``http`` is the encapsulated HTTP message, either an instance of
        `~icap.models.ICAPRequest` or `~icap.models.ICAPResponse`.

        """
        self.headers = headers or HeadersDict()

        # really not comfortable with this default...
        self.http = http

    @cached_property
    def is_request(self):
        """Return True if this object is a request.

        This is just a shortcut for ``isinstance(self, ICAPRequest)``.

        """
        return isinstance(self, ICAPRequest)

    @cached_property
    def is_response(self):
        """Return True if this object is a response.

        This is just a shortcut for ``isinstance(self, ICAPResponse)``.

        """
        return isinstance(self, ICAPResponse)

    @cached_property
    def has_body(self):
        """Return True if this object has a payload."""
        if ((self.is_request and self.is_options and
             'encapsulated' not in self.headers)):
            return False
        return 'null-body' not in self.headers['encapsulated']


class ICAPRequest(ICAPMessage):
    """Representation of an ICAP request."""

    def __init__(self, request_line=None, *args, **kwargs):
        """If no ``request_line`` is given, a default of "UNKNOWN / ICAP/1.0"
        will be used.

        For all other available attributes, see `~icap.models.ICAPMessage`.

        """
        super().__init__(*args, **kwargs)
        self.request_line = request_line or RequestLine("UNKNOWN", "/",
                                                        "ICAP/1.0")

    @classmethod
    def from_parser(cls, parser):
        """Return an instance of `~icap.models.ICAPRequest` from ``parser``.

        ``parser`` MUST be an instance of `~icap.parsing.ICAPRequestParser`.

        """
        assert isinstance(parser, ICAPRequestParser)

        headers = parser.headers

        if parser.is_options:
            self = cls(parser.sline, headers)
        elif parser.is_reqmod:
            self = cls(parser.sline, headers, parser.request_parser.to_http())
        elif parser.is_respmod:
            self = cls(parser.sline, headers, parser.response_parser.to_http())
            if 'req-hdr' in parser.encapsulated_header:
                request = parser.request_parser.to_http()
                self.http.request_line = request.request_line
                self.http.request_headers = request.headers
        return self

    @cached_property
    def allow_204(self):
        """Return True of the client supports a 204 response code."""
        # FIXME: this should parse the list.
        return ('204' in self.headers.get('allow', '') or
                'preview' in self.headers)

    @cached_property
    def is_reqmod(self):
        """Return True if the current request is a REQMOD request."""
        return self.request_line.method == 'REQMOD'

    @cached_property
    def is_respmod(self):
        """Return True if the current request is a RESPMOD request."""
        return self.request_line.method == 'RESPMOD'

    @cached_property
    def is_options(self):
        """Return True if the current request is an OPTIONS request."""
        return self.request_line.method == 'OPTIONS'


class ICAPResponse(ICAPMessage):
    """Representation of an ICAP response."""

    def __init__(self, status_line=None, *args, **kwargs):
        """If no ``status_line`` is given, a default of "ICAP/1.0 200 OK" will
        be used.

        For all other available attributes, see `~icap.models.ICAPMessage`.

        """
        super().__init__(*args, **kwargs)
        self.status_line = status_line or StatusLine('ICAP/1.0', 200, 'OK')

    def __bytes__(self):
        return b'\r\n'.join((
            ' '.join(map(str, self.status_line)).encode('utf8'),
            bytes(self.headers)
        ))

    @classmethod
    def from_error(cls, error):
        if isinstance(error, int):
            status_code = error
        else:
            status_code = error.status_code
        message = icap_response_codes[status_code]
        self = cls(StatusLine('ICAP/1.0', status_code, message))
        return self


class HTTPMessage(object):
    """Base HTTP class for generalising certain properties of both requests and
    responses.

    Should not be used directly - use `~icap.models.HTTPRequest` or
    `~icap.models.HTTPResponse` instead.

    """

    def __init__(self, headers=None, body=b''):
        """If ``headers`` is not given, default to an empty instance of
        `~icap.models.HeadersDict`.

        ``body`` is an iterable of the payload of the HTTP message. It can be a
        stream, list of strings, a generator or a string.
        """
        self.headers = headers or HeadersDict()
        self.body = body
        self.cookies = SimpleCookie(self.headers.get('Cookie', ''))
        self.set_cookies = SimpleCookie()

    def set_cookie(self, name, value, path=None, domain=None):
        self.cookies[name] = value
        self.set_cookies[name] = value
        if path:
            self.set_cookies[name]['path'] = path
        if domain:
            self.set_cookies[name]['domain'] = domain

    def del_cookie(self, name):
        del self.cookies[name]
        self.set_cookies[name] = ''
        self.set_cookies[name]['expires'] = (datetime.now() -
            timedelta(days=1)).strftime('%a, %d %b %Y %I:%m:%S GMT')

    @property
    def body(self):
        """Returns the body of the message.

        If the Content-Type header of the message contains a charset, it
        will return the body decoded using that charset. Otherwise, it will
        return the bytes.

        If the Content-Type header is completely missing, 'text/plain;
        charset=us-ascii' is assumed, as per RFC1341.
        """
        body = self.body_bytes

        # FIXME: caching this in some way would be useful... be it the decoded
        # string or the charset.
        content_type, charset = self.content_type

        if charset:
            body = body.decode(charset)

        return body

    @property
    def body_bytes(self):
        """Returns the body of the message as plain bytes with no decoding."""
        return self._body

    @body.setter
    def body(self, value):
        """Setter for the body attribute.

        If ``value`` is of type `bytes`, then nothing complicated occurs, the
        attribute is merely set.

        If ``value`` is of type `str`, it will store the body encoded using the
        charset in the Content-Type header. If the Content-Type header is
        completely missing, 'text/plain; charset=us-ascii' is assumed, as per
        RFC1341.

        If the Content-Type header is available without a charset, then a
        TypeError will be raised. Given this will only happen in a situation
        you have control of (i.e. modifying the body in a handler), it is your
        responsibility to ensure you handle this situation properly by encoding
        the string before setting it.
        """

        if isinstance(value, str):
            content_type, charset = self.content_type

            # protect people from idiots that set the charset on things they
            # never, ever should. Take, for example, Yammer, who set the
            # charset on images and video.
            if charset and content_type.startswith(('application', 'text',
                                                    'message')):
                value = value.encode(charset)

        if not isinstance(value, bytes):
            raise TypeError('Could not figure out body encoding. Encode '
                            'payload appropriately.')

        self._body = value

    def __bytes__(self):
        if self.is_request:
            field = self.request_line
        else:
            field = self.status_line

        return b'\r\n'.join([bytes(field), bytes(self.headers)])

    @cached_property
    def is_request(self):
        """Return True if this object is a request.

        This is just a shortcut for ``isinstance(self, HTTPRequest)``.

        """
        return isinstance(self, HTTPRequest)

    @cached_property
    def is_response(self):
        """Return True if this object is a response.

        This is just a shortcut for ``isinstance(self, HTTPResponse)``.

        """
        return isinstance(self, HTTPResponse)

    @property
    def content_type(self):
        content_type, options = parse_options_header(
            self.headers.get('content-type', 'text/plain; charset=us-ascii'))
        charset = options.get('charset', '')
        return content_type, charset

    def pre_serialization(self):
        """Method called prior to serialisation. Useful for writing any
        higher-level constructs back to bytes.

        """
        pass


class HTTPRequest(HTTPMessage):
    """Representation of a HTTP request."""

    parsed_post_data = False

    def __init__(self, request_line=None, *args, **kwargs):
        """If no ``request_line`` is given, a default of "GET / HTTP/1.1" will
        be used.

        For all other available attributes, see `~icap.models.HTTPMessage`.

        """
        self.request_line = request_line or RequestLine('GET', '/', 'HTTP/1.1')
        super().__init__(*args, **kwargs)

    @classmethod
    def from_parser(cls, parser):
        """Return an instance of `~icap.models.HTTPRequest` from ``parser``.

        ``parser`` MUST be an instance of `~icap.parsing.HTTPMessageParser`.

        """
        assert not isinstance(parser, ICAPRequestParser)
        assert parser.is_request
        f = cls(parser.sline, parser.headers, parser.payload)

        return f

    def pre_serialization(self):
        """Prior to serialization, write POST data back to bytes if they've
        been parsed out.

        """
        if not self.parsed_post_data:
            return

        content_type, charset = self.content_type
        s = urlencode(self.post, doseq=True, encoding=charset or 'utf-8')
        self._body = s.encode(charset or 'utf-8')

    @cached_property
    def post(self):
        content_type, charset = self.content_type

        if content_type == 'application/x-www-form-urlencoded':
            self.parsed_post_data = True
            return parse_qs(self.body, encoding=charset or 'utf-8')
        else:
            return None


class HTTPResponse(HTTPMessage):
    """Representation of a HTTP response."""

    def __init__(self, status_line=None, *args, **kwargs):
        """Initialise a new `HTTPResponse` instance.

        If no ``status_line`` is given, a default of "HTTP/1.1 200 OK" will be
        used.

        For all other available attributes, see `~icap.models.HTTPMessage`.

        """
        super().__init__(*args, **kwargs)
        self.status_line = status_line or StatusLine('HTTP/1.1', 200, 'OK')

        # if a RESPMOD comes in such that the request headers are available,
        # these will be replaced with those. These are merely provided as
        # defaults to protect against AttributeErrors.
        self.request_line = RequestLine('GET', '/', 'HTTP/1.1')
        self.request_headers = HeadersDict()

    def pre_serialization(self):
        """Handle cookies.

        """
        for morsel in self.set_cookies.values():
            name, _, value = str(morsel).partition(': ')
            self.headers[name] = value

    @classmethod
    def from_parser(cls, parser):
        """Return an instance of `~icap.models.HTTPResponse` from ``parser``.

        ``parser`` MUST be an instance of `~icap.parsing.HTTPMessageParser`.

        """
        assert not isinstance(parser, ICAPRequestParser)
        assert parser.is_response
        return cls(parser.sline, parser.headers, parser.payload)
