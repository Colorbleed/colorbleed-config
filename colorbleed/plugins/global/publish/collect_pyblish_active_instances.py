import os
import pyblish.api


class CollectInstancesActiveState(pyblish.api.ContextPlugin):
    """Collect instance active state from PYBLISH_ACTIVE_INSTANCES.

    This will read the PYBLISH_ACTIVE_INSTANCES environment variable and split
    the string by comma. Only those instances that match by name with the
    entries in that list will remain active for publishing, the rest will
    be deactivated.

    This is used for activating solely those instances that are set in the
    environment variable, which is used for Deadline farm jobs that trigger
    Pyblish publishes on the farm and we want to ensure only specific
    instances are processed.

    """
    targets = ["local"]
    order = pyblish.api.CollectorOrder + 0.499
    label = "Force Instances Active State"

    def process(self, context):

        active = os.environ.get("PYBLISH_ACTIVE_INSTANCES")
        if active is None:
            # The value is not set in the environment so we ignore this
            # collector completely
            self.log.debug("PYBLISH_ACTIVE_INSTANCES not set. "
                           "Ignoring collector..")
            return

        if not active:
            raise RuntimeError("No registered active instances to process"
                               " in PYBLISH_ACTIVE_INSTANCES.")

        # Make set of valid entries, split by comma
        active = set(name.strip() for name in active.split(",") if
                     name.strip())

        found = set()
        for instance in context:

            # Set the state per instance
            state = instance.name in active
            self.log.info("Setting %s publish state to %s" % (instance.name,
                                                              state))
            instance.data["active"] = state
            instance.data["publish"] = state

            if state:
                found.add(instance.name)

        # Ensure all PYBLISH_ACTIVE_INSTANCES are found so that we can
        # expect the publish to be consistent with what the user requested
        missing = active - found
        if missing:
            raise RuntimeError("Missing subsets: %s" % list(missing))


# Avoid this plug-in all together when PYBLISH_ACTIVE_INSTANCES is not set so
# we only ever load this whenever that environment variable is set at the time
# of discovering Pyblish plug-ins.
if "PYBLISH_ACTIVE_INSTANCES" not in os.environ:
    del CollectInstancesActiveState
