import os
import json
import pprint

import pyblish.api
from colorbleed import schema


class CollectStandalonePublish(pyblish.api.ContextPlugin):
    """Gather publish context and instances based on .json file.

    This is based on the publishstandalone-1.0 json schema found in:
        <config>/schema/publishstandalone-1.0.json

    It reads the file from the STANDALONEPUBLISH environment variable which
    will need to be set to a .json filepath.

    Requires:
        os.environ  -> STANDALONEPUBLISH

    Provides:
        instance    -> renderSubsets

    """

    order = pyblish.api.CollectorOrder
    targets = ["standalonepublish"]
    label = "Collect Standalone Publish Job"

    def process(self, context):

        if not os.environ.get("STANDALONEPUBLISH"):
            raise RuntimeError("Skipping collect publish instances, missing "
                               "'STANDALONEPUBLISH' environment variable..")

        path = os.environ["STANDALONEPUBLISH"]
        assert os.path.isfile(path), "Path is not a file: %s" % path
        assert path.endswith(".json"), "Path is not .json file: %s" % path

        payload = self._load_json(path)
        assert "schema" in payload, "Must have schema data"

        # Validate schema
        try:
            schema.validate(payload)
        except schema.ValidationError as exc:
            self.log.debug(pprint.pformat(payload))
            self.log.error("Failed to validate schema: %s" % exc)
            raise exc

        # Set up publish context and instances
        context.data.update(payload["context"])

        for instance_data in payload["instances"]:

            # Define a nice name based on "subset (asset)"
            name = "{asset} ({subset})".format(**instance_data)
            instance = context.create_instance(name=name)
            instance.data.update(instance_data)

            # Force the primary family from the families data
            # todo: remove this when pyblish GUI doesn't require it.
            instance.data["family"] = instance_data["families"][0]

    def _load_json(self, path):
        self.log.info("Loading: {}".format(path))

        with open(path, "r") as f:
            try:
                data = json.load(f)
            except Exception as exc:
                self.log.error("Error loading json: "
                               "{} - Exception: {}".format(path, exc))
                raise

            return data
