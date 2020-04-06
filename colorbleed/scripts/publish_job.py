"""This module is used for command line publishing of image sequences."""

import os
import sys
import logging

handler = logging.basicConfig()
log = logging.getLogger("Publish Image Sequences")
log.setLevel(logging.DEBUG)

error_format = "Failed {plugin.__name__}: {error} -- {error.traceback}"


def publish(path, gui=False):
    """Publish rendered image sequences based on the job data

    Args:
        paths (list): a list of paths where to publish from
        gui (bool, Optional): Choose to show Pyblish GUI, default is False

    Returns:
        None

    """

    assert os.path.exists(path), "File does not exist: %s" % path
    assert os.path.isfile(path), "Path is not a file: %s" % path
    log.info(path)

    # Set this for the PUBLISHJOB collector
    os.environ["STANDALONEPUBLISH"] = path

    # Install Avalon with shell as current host
    from avalon import api, shell
    api.install(shell)

    # Register target and host
    import pyblish.api
    pyblish.api.register_target("standalonepublish")
    pyblish.api.register_host("shell")

    # Publish items
    if gui:
        import pyblish_qml
        pyblish_qml.show(modal=True)
    else:

        import pyblish.util
        context = pyblish.util.publish()

        if not context:
            log.warning("Nothing collected.")
            sys.exit(1)

        # Collect errors, {plugin name: error}
        error_results = [r for r in context.data["results"] if r["error"]]

        if error_results:
            log.error(" Errors occurred ...")
            for result in error_results:
                log.error(error_format.format(**result))
            sys.exit(2)


def __main__():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--path",
                        default=None,
                        help="The publish job `.json` file to parse.")
    parser.add_argument("--gui",
                        default=False,
                        action="store_true",
                        help="Whether to run Pyblish in GUI mode.")

    kwargs, args = parser.parse_known_args()

    print("Running publish imagesequence...")
    print("Paths: {}".format(kwargs.paths or [os.getcwd()]))
    publish(kwargs.path, gui=kwargs.gui)


if __name__ == '__main__':
    __main__()
