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
  `mox <https://pypi.org/project/mox3/>`__,
  `requests <http://python-requests.org>`__, and
  `urllib <https://docs.python.org/3.9/library/urllib.html>`__
- `util <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.util>`__:
  wide variety of utilities for data structures, web code, etc.
- `webmention <https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.webmention>`__:
  `Webmention <https://webmention.net/>`__ endpoint discovery and
  sending

Changelog
---------

1.1 - unreleased
~~~~~~~~~~~~~~~~

- ``appengine_info``:

  - Add `Cloud Run <https://docs.cloud.google.com/run/docs/>`__ support.

- ``models``:

  - Add new ``WriteOnce``, ``WriteOnceBlobProperty`` ndb property
    classes. (Moved here from
    `arroba <https://github.com/snarfed/arroba/>`__.)
  - Add support for ``$ENCRYPTED_PROPERTY_KEY`` environment variable.

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
    ``sh  source local/bin/activate.csh  gcloud emulators firestore start --host-port=:8089 --database-mode=datastore-mode < /dev/null >& /dev/null &  python -m unittest discover``
3.  Bump the version number in ``setup.py`` and ``docs/conf.py``.
    ``git grep`` the old version number to make sure it only appears in
    the changelog. Change the current changelog entry in ``README.md``
    for this new version from *unreleased* to the current date.
4.  Build the docs. If you added any new modules, add them to the
    appropriate file(s) in ``docs/source/``. Then run
    ``./docs/build.sh``.
5.  ``git commit -am 'release vX.Y'``
6.  Upload to `test.pypi.org <https://test.pypi.org/>`__ for testing.
    ``sh  python setup.py clean build sdist  setenv ver X.Y  twine upload -r pypitest dist/pywebutil-$ver.tar.gz``
7.  Install from test.pypi.org.
    ``sh  cd /tmp  python -m venv local  source local/bin/activate.csh  pip install --upgrade pip  pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple pywebutil``
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
    ``sh  twine upload dist/pywebutil-$ver.tar.gz``
