import os

import pyblish.api


class CollectAlembicAttributes(pyblish.api.InstancePlugin):
    """Collect attributes and attribute prefixes to include on Alembic export.

    This reformats the ";" separated string attributes from the instance to
    a list of values, for example: a;b;c -> ["a", "b", "c"]

    Note:
        This also appends the default "cbId" and "cb_*" attributes for Alembic
        export unless CB_MAYA_ABC_WRITE_CBID environment variable is set to
        "False" or "0"

    Provides:
        instance ->     attr (list)
        instance ->     attrPrefix (list)

    """

    order = pyblish.api.CollectorOrder + 0.499
    label = 'Define Alembic Export Attributes'
    families = ["colorbleed.pointcache",
                "colorbleed.animation",
                "colorbleed.model"]

    def process(self, instance):

        # Parse string attributes collected from the instance to lists
        def parse_attrs(instance, key):
            """Parse string data values to list, a;b;c -> ['a','b', 'c']"""
            value = instance.data.get(key)
            if not value:
                return []

            return [x for x in value.split(";") if x.strip()]

        attr = parse_attrs(instance, "attr")
        attr_prefix = parse_attrs(instance, "attrPrefix")

        # By default include cbId attributes with the Alembic unless the
        # project is explicitly set to disregard writing of 'cbId'
        state = os.environ.get("CB_MAYA_ABC_WRITE_CBID")
        if state in {"0", "False"}:
            self.log.debug("Skipping default attrs because environment "
                           "variable 'CB_MAYA_ABC_WRITE_CBID' is set "
                           "to %s." % state)
        else:
            attr.append("cbId")
            attr_prefix.append("cb_")

        # Set the new data as lists
        instance.data["attr"] = attr
        instance.data["attrPrefix"] = attr_prefix
