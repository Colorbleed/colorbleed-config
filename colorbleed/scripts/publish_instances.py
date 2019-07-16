try:
    import logging
    import pyblish.api
    import pyblish.util
except ImportError as exc:
    # Ensure Deadline fails by output an error that contains "Fatal Error:"
    raise ImportError("Fatal Error: %s" % exc)


handler = logging.basicConfig()
log = logging.getLogger("Publish active instances")
log.setLevel(logging.DEBUG)


class CollectInstancesActiveState(pyblish.api.ContextPlugin):
    """Collect instance active state from PYBLISH_ACTIVE_INSTANCES.

    This will read the PYBLISH_ACTIVE_INSTANCES environment variable and split
    the string by comma. Only those instances that match by name with the
    entries in that list will remain active for publishing, the rest will
    be deactivated.

    """
    order = pyblish.api.CollectorOrder + 0.499

    def process(self, context):

        active = os.environ.get("PYBLISH_ACTIVE_INSTANCES")
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


def publish():
    # Note: This function assumes Avalon has been installed prior to this.
    #       As such it does *not* trigger avalon.api.install().

    # First register the plug-in that ensures only the instances defined in
    # PYBLISH_ACTIVE_INSTANCES remain enabled directly after collection.
    pyblish.api.register_plugin(CollectInstancesActiveState)

    context = pyblish.util.publish()

    # Cleanup afterwards, just to be sure. This is not so important if this
    # runs in a standalone process that dies after publishing anyway.
    pyblish.api.deregister_plugin(CollectInstancesActiveState)

    print("Finished pyblish.util.publish(), checking for errors..")

    if not context:
        log.warning("Fatal Error: Nothing collected.")
        sys.exit(1)

    # Collect errors, {plugin name: error}
    error_results = [r for r in context.data["results"] if r["error"]]

    if error_results:
        error_format = "Failed {plugin.__name__}: {error} -- {error.traceback}"
        for result in error_results:
            log.error(error_format.format(**result))

        log.error("Fatal Error: Errors occurred, see log..")
        sys.exit(2)

    print("All good. Success!")


if __name__ == "__main__":
    publish()
