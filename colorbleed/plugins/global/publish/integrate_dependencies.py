import pyblish.api

from colorbleed import lib


class IntegrateAssetDependencies(pyblish.api.InstancePlugin):
    # Get docstring from library Integrator
    __doc__ = lib.Integrator.__doc__

    label = "Integrate Dependencies"
    order = pyblish.api.IntegratorOrder
    families = [
                "colorbleed.usd.bootstrap",
                "colorbleed.usd.layered"
    ]
    targets = ["local"]

    def process(self, instance):

        # Perform initial check
        context = instance.context
        assert all(result["success"] for result in context.data["results"]), (
            "Atomicity not held, aborting.")

        integrator = lib.Integrator()

        # Allow logging into the Plugin's logger.
        integrator.log = self.log

        # Allow hidden sub instances to be published along too.
        dependencies = instance.data.get("publishDependencies", [])
        for dependency in dependencies:

            if not dependency.data.get("publish", True):
                # Skip inactive instances
                continue

            is_integrated = dependency.data.get("_isIntegrated", False)
            if is_integrated:
                # This dependency might have been embedded in another instance
                # too and thus had already run on another instance. We will
                # skip integrating it again.
                continue

            is_extracted = dependency.data.get("_isExtracted", False)
            if not is_extracted:
                continue

            # Consider this Instance integrated prior to processing it.
            # This is so even when it fails it won't retry it again later
            # and just end up failing again.
            dependency.data["_isIntegrated"] = True

            integrator.process(dependency)
