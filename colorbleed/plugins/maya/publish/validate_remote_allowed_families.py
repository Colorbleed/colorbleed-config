import pyblish.api


class ValidateRemoteAllowedFamilies(pyblish.api.InstancePlugin):
    """This invalidates instances for publishing on the farm.

    This means the publishing of the family cannot be done in a standalone
    application. As such to publish these instances you'll have to run
    a regular local publish.

    Please use `Avalon > Publish...` instead.

    """

    label = "Remote Disallowed Families"
    families = ["colorbleed.review"]
    targets = ["deadline"]
    order = pyblish.api.ValidatorOrder - 0.4  # Show error as early as possible

    def process(self, instance):

        # Get the families of the instance
        families = instance.data.get("families", [])
        family = instance.data.get("family", None)  # backwards compatibility
        if family:
            families.append(family)
        families = set(families)

        invalid_families = families.intersection(self.families)

        raise RuntimeError("Family is not supported for publishing on "
                           "farm: %s" % list(invalid_families))
