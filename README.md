webutil [![Circle CI](https://circleci.com/gh/snarfed/oauth-dropins.svg?style=svg)](https://circleci.com/gh/snarfed/oauth-dropins) [![Coverage Status](https://coveralls.io/repos/github/snarfed/oauth-dropins/badge.svg?branch=master)](https://coveralls.io/github/snarfed/oauth-dropins?branch=master)
===

Common utilities and handler code for Python web apps:
* [`flask_util`](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.flask_util): [Flask](https://flask.palletsprojects.com/) decorators and handlers for caching, exception handling, regular expression URL routing, domain-wide redirects, rate limiting, headers, and serving XRD and JRD templates.
* [`logs`](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.logs): Flask request handler that collects full trace logs from [Google Cloud Logging](https://cloud.google.com/logging/docs), formats them nicely, and serves them
* [`models`](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.models): minor utility [Model classes](https://googleapis.dev/python/python-ndb/latest/model.html) for the [Google Cloud Datastore](https://console.cloud.google.com/datastore/) [ndb library](https://github.com/googleapis/python-ndb)
* [`testutil`](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.testutil): misc utilities and helpers for [unittest](https://docs.python.org/3.9/library/unittest.html), [mox](https://pypi.org/project/mox3/), [requests](http://python-requests.org), and [urllib](https://docs.python.org/3.9/library/urllib.html)
* [`util`](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.util): wide variety of utilities for data structures, web code, etc.
* [`webmention`](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html#module-oauth_dropins.webutil.webmention): [Webmention](https://webmention.net/) endpoint discovery and sending

webutil is not developed, maintained, or distributed as a standalone package. Instead, it's distributed as part of the [oauth-dropins](https://oauth-dropins.readthedocs.io/) library.

* Install with `pip install oauth-dropins`.
* Supports Python 3.7+.
* [Reference documentation.](https://oauth-dropins.readthedocs.io/en/stable/source/oauth_dropins.webutil.html)

webutil is public domain. You may also use it under the [CC0 public domain dedication](https://creativecommons.org/share-your-work/public-domain/cc0/).
