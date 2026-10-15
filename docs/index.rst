webutil
-------

Common utilities and handler code for Python web apps.

- Install with ``pip install webutil``
- Supports Python 3.9+
- `Documentation <https://oauth-dropins.readthedocs.io/>`__

webutil is dedicated to the public domain. You may also use it under the
`CC0 public domain
dedication <https://creativecommons.org/share-your-work/public-domain/cc0/>`__.

Contents
--------

- `flask_util <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.flask_util>`__:
  `Flask <https://flask.palletsprojects.com/>`__ decorators and handlers
  for caching, exception handling, regular expression URL routing,
  domain-wide redirects, rate limiting, headers, and serving XRD and JRD
  templates.
- `logs <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.logs>`__:
  Flask request handler that collects full trace logs from `Google Cloud
  Logging <https://cloud.google.com/logging/docs>`__, formats them
  nicely, and serves them
- `models <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.models>`__:
  minor utility `Model
  classes <https://googleapis.dev/python/python-ndb/latest/model.html>`__
  for the `Google Cloud
  Datastore <https://console.cloud.google.com/datastore/>`__ `ndb
  library <https://github.com/googleapis/python-ndb>`__
- `testutil <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.testutil>`__:
  misc utilities and helpers for
  `unittest <https://docs.python.org/3.9/library/unittest.html>`__,
  `requests <http://python-requests.org>`__, and
  `urllib <https://docs.python.org/3.9/library/urllib.html>`__
- `util <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.util>`__:
  wide variety of utilities for data structures, web code, etc.
- `webmention <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.webmention>`__:
  `Webmention <https://webmention.net/>`__ endpoint discovery and
  sending

Changelog
---------

3.0 - 2026-10-14
~~~~~~~~~~~~~~~~

*Breaking changes:*

- ``util``:

  - Remove ``if_changed``.
  - ``pretty_link``: only link ``http`` and ``https`` URLs. For other
    URLs, return just the link text.

*Non-breaking changes:*

- ``flask_util``:

  - Add ``bool_param`` for getting boolean query params/form arguments.
  - Add ``csp_report`` handler for logging ``Content-Security-Policy``
    violation reports.
  - ``MODERN_HEADERS``: tighten ``Content-Security-Policy``
    significantly.

- ``models``:

  - Fix missing import in ``Cache.get``/``Cache.put``.

- ``testutil``:

  - Add ``assert_html_equals``, which compares HTML strings and ignores
    insignificant whitespace and attribute order.
  - ``requests_response``: back the returned response with a
    ``urllib3.HTTPResponse`` instead of a bare ``BytesIO``, so that
    ``resp.raw.stream()`` works for code that streams responses.

- ``util``:

  - ``requests_*``: add ``cache`` kwarg, an opt-in Flask-request-local
    cache of GET/HEAD responses and exceptions, keyed on method, URL,
    and ``Accept`` header.
  - ``encode``: fix ``encoding`` kwarg, it was ignored for nested values
    and always used UTF-8.
  - ``is_connection_failure``: make ``prawcore`` import optional.
  - ``linkify``, ``tokenize_links``: fix duplicated trailing punctuation
    after a link, eg ``http://foo.com/a)..`` became
    ``http://foo.com/a).....``.
  - ``clean_url``: fix query params with escaped delimiters, eg
    ``?a=b%26c`` lost the ``%26c``. The query string was unescaped
    before it was parsed.
  - ``maybe_iso8601_to_rfc3339``: return non-string inputs unchanged
    instead of raising ``AttributeError``.
  - ``pretty_link``: HTML-escape the URL in ``href`` and the ``attrs``
    values.
  - ``to_utc_timestamp``: fix timezone aware datetimes, they were read
    as wall clock time and their UTC offset was ignored.
  - ``trim_nulls``: add ``keep_empty_values_in`` kwarg.

.. _section-1:

2.0 - 2026-06-29
~~~~~~~~~~~~~~~~

- ``appengine_info``:

  - Add `Cloud Run <https://docs.cloud.google.com/run/docs/>`__ support.

- ``flask_util``:

  - Add ``block``, a ``before_request`` handler that blocks requests by
    client IP CIDR and/or ``User-Agent``.

- ``models``:

  - Add new ``WriteOnce``, ``WriteOnceBlobProperty`` ndb property
    classes. (Moved here from
    `arroba <https://github.com/snarfed/arroba/>`__.)
  - Add support for ``$ENCRYPTED_PROPERTY_KEY`` environment variable.

- ``testutil``:

  - Add new ``@head_returns_200`` decorator.
  - Drop ``mox`` from ``TestCase``.
  - Add new ``unittest.mock`` and ``requests`` helpers to ``TestCase``.

- ``util``:

  - ``requests_*``: add new ``log_data`` boolean kwarg.

.. _section-2:

1.0 - 2026-05-27
~~~~~~~~~~~~~~~~

Initial PyPI release. Moved out of oauth-dropins, where it’s been
maintained for the last 10+ years, into its own dedicated package,
``pywebutil``.

Release instructions
--------------------

Here’s how to package, test, and ship a new release.

1.  Pull from remote to make sure we’re at head.
    ``sh  git checkout main  git pull``

2.  Run the unit tests.
    ``sh  source .venv/bin/activate.csh  gcloud emulators firestore start --host-port=:8089 --database-mode=datastore-mode < /dev/null >& /dev/null &  python -m unittest discover  python -m unittest webutil/tests/hypothesis/*.py``

3.  Bump the version number in ``pyproject.toml`` and ``docs/conf.py``.
    ``git grep`` the old version number to make sure it only appears in
    the changelog. Change the current changelog entry in ``README.md``
    for this new version from *unreleased* to the current date.

4.  Build the docs. If you added any new modules, add them to the
    appropriate file(s) in ``docs/source/``. Then run
    ``./docs/build.sh``.

5.  

    .. code:: sh

       setenv ver X.Y
       git commit -am "release v$ver"

6.  Upload to `test.pypi.org <https://test.pypi.org/>`__ for testing.
    ``sh  uv build  twine upload -r pypitest dist/pywebutil-$ver.tar.gz dist/pywebutil-$ver-py3-none-any.whl``

7.  Install from test.pypi.org.
    ``sh  cd /tmp  python3 -m venv .venv  source .venv/bin/activate.csh  pip3 install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple pywebutil``

8.  Smoke test that the code trivially loads and runs.
    ``sh  python  # run test code below`` Test code to paste into the
    interpreter:
    ``py  from webutil import util  util.__file__  util.UrlCanonicalizer()('http://asdf.com')  # should print 'https://asdf.com/'  exit()``

9.  Tag the release in git. In the tag message editor, delete the
    generated comments at bottom, leave the first line blank (to omit
    the release “title” in github), put ``### Notable changes`` on the
    second line, then copy and paste this version’s changelog contents
    below it.
    ``sh  git tag -a v$ver --cleanup=verbatim  git push  git push --tags``

10. `Click here to draft a new release on
    GitHub. <https://github.com/snarfed/webutil/releases/new>`__ Enter
    ``vX.Y`` in the *Tag version* box. Leave *Release title* empty. Copy
    ``### Notable changes`` and the changelog contents into the
    description text box.

11. Upload to `pypi.org <https://pypi.org/>`__!
    ``sh  twine upload dist/pywebutil-$ver-* dist/pywebutil-$ver.*``
