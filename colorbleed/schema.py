"""Wrapper around :mod:`jsonschema`

Schemas are implicitly loaded from the /schema directory of this project.

Attributes:
    _cache: Cache of previously loaded schemas

Resources:
    http://json-schema.org/
    http://json-schema.org/latest/json-schema-core.html
    http://spacetelescope.github.io/understanding-json-schema/index.html

"""

import os
import sys
import json
import logging

from avalon.vendor import jsonschema

if sys.version_info[0] == 3:
    basestring = str

log_ = logging.getLogger(__name__)

ValidationError = jsonschema.ValidationError
SchemaError = jsonschema.SchemaError


def validate(data):
    """Validate `data` using `data['schema']`

    Arguments:
        data (dict): JSON-compatible data

    Raises:
        ValidationError on invalid schema

    """

    schema = data["schema"]

    if isinstance(schema, basestring):
        schema = _cache[schema + ".json"]

    resolver = jsonschema.RefResolver(
        "",
        None,
        store=_cache,
        cache_remote=True
    )

    jsonschema.validate(data,
                        schema,
                        types={"array": (list, tuple)},
                        resolver=resolver)


_MODULE_DIR = os.path.dirname(__file__)
_SCHEMA_DIR = os.path.join(_MODULE_DIR, "schema")

_cache = {}


def _precache():
    """Store available schemas in-memory for reduced disk access"""
    for schema in os.listdir(_SCHEMA_DIR):
        if schema.startswith(("_", ".")):
            continue
        if not schema.endswith(".json"):
            continue
        if not os.path.isfile(os.path.join(_SCHEMA_DIR, schema)):
            continue
        with open(os.path.join(_SCHEMA_DIR, schema)) as f:
            log_.debug("Installing schema '%s'.." % schema)
            _cache[schema] = json.load(f)


_precache()
