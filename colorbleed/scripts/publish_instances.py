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


def publish():
    # Note: This function assumes Avalon has been installed prior to this.
    #       As such it does *not* trigger avalon.api.install().
    print("Starting pyblish.util.pyblish()..")
    context = pyblish.util.publish()
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
