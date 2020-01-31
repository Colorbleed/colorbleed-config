import os
import contextlib
import hou
import sys
from collections import deque

import pyblish.api
import colorbleed.api

import colorbleed.houdini.usd as usdlib


class ExitStack(object):
    """Context manager for dynamic management of a stack of exit callbacks

    For example:

        with ExitStack() as stack:
            files = [stack.enter_context(open(fname)) for fname in filenames]
            # All opened files will automatically be closed at the end of
            # the with statement, even if attempts to open files later
            # in the list raise an exception

    """
    def __init__(self):
        self._exit_callbacks = deque()

    def pop_all(self):
        """Preserve the context stack by transferring it to a new instance"""
        new_stack = type(self)()
        new_stack._exit_callbacks = self._exit_callbacks
        self._exit_callbacks = deque()
        return new_stack

    def _push_cm_exit(self, cm, cm_exit):
        """Helper to correctly register callbacks to __exit__ methods"""
        def _exit_wrapper(*exc_details):
            return cm_exit(cm, *exc_details)
        _exit_wrapper.__self__ = cm
        self.push(_exit_wrapper)

    def push(self, exit):
        """Registers a callback with the standard __exit__ method signature

        Can suppress exceptions the same way __exit__ methods can.

        Also accepts any object with an __exit__ method (registering a call
        to the method instead of the object itself)
        """
        # We use an unbound method rather than a bound method to follow
        # the standard lookup behaviour for special methods
        _cb_type = type(exit)
        try:
            exit_method = _cb_type.__exit__
        except AttributeError:
            # Not a context manager, so assume its a callable
            self._exit_callbacks.append(exit)
        else:
            self._push_cm_exit(exit, exit_method)
        return exit # Allow use as a decorator

    def callback(self, callback, *args, **kwds):
        """Registers an arbitrary callback and arguments.

        Cannot suppress exceptions.
        """
        def _exit_wrapper(exc_type, exc, tb):
            callback(*args, **kwds)
        # We changed the signature, so using @wraps is not appropriate, but
        # setting __wrapped__ may still help with introspection
        _exit_wrapper.__wrapped__ = callback
        self.push(_exit_wrapper)
        return callback # Allow use as a decorator

    def enter_context(self, cm):
        """Enters the supplied context manager

        If successful, also pushes its __exit__ method as a callback and
        returns the result of the __enter__ method.
        """
        # We look up the special methods on the type to match the with statement
        _cm_type = type(cm)
        _exit = _cm_type.__exit__
        result = _cm_type.__enter__(cm)
        self._push_cm_exit(cm, _exit)
        return result

    def close(self):
        """Immediately unwind the context stack"""
        self.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc_details):
        # We manipulate the exception state so it behaves as though
        # we were actually nesting multiple with statements
        frame_exc = sys.exc_info()[1]
        def _fix_exception_context(new_exc, old_exc):
            while 1:
                exc_context = new_exc.__context__
                if exc_context in (None, frame_exc):
                    break
                new_exc = exc_context
            new_exc.__context__ = old_exc

        # Callbacks are invoked in LIFO order to match the behaviour of
        # nested context managers
        suppressed_exc = False
        while self._exit_callbacks:
            cb = self._exit_callbacks.pop()
            try:
                if cb(*exc_details):
                    suppressed_exc = True
                    exc_details = (None, None, None)
            except:
                new_exc_details = sys.exc_info()
                # simulate the stack of exceptions by setting the context
                _fix_exception_context(new_exc_details[1], exc_details[1])
                if not self._exit_callbacks:
                    raise
                exc_details = new_exc_details
        return suppressed_exc


def render(ropnode):
    # Print verbose when in batch mode without UI
    verbose = not hou.isUIAvailable()

    # Render
    try:
        ropnode.render(verbose=verbose,
                       # Allow Deadline to capture completion percentage
                       output_progress=verbose)
    except hou.Error as exc:
        # The hou.Error is not inherited from a Python Exception class,
        # so we explicitly capture the houdini error, otherwise pyblish
        # will remain hanging.
        import traceback
        traceback.print_exc()
        raise RuntimeError("Render failed: {0}".format(exc))


@contextlib.contextmanager
def parm_values(overrides):
    """Override Parameter values during the context."""

    originals = list()
    try:
        for parm, value in overrides:
            originals.append((parm, parm.rawValue()))
            parm.set(value)
        yield
    finally:
        for parm, value in originals:
            parm.set(value)


class ExtractUSDLayered(colorbleed.api.Extractor):

    order = pyblish.api.ExtractorOrder
    label = "Extract Layered USD"
    hosts = ["houdini"]
    targets = ["local"]
    families = ["colorbleed.usd.layered"]

    def process(self, instance):

        staging_dir = self.staging_dir(instance)

        self.log.info("Extracting: %s" % instance)

        # The individual rop nodes are collected as "publishDependencies"
        dependencies = instance.data["publishDependencies"]
        ropnodes = [dependency[0] for dependency in dependencies]
        assert all(node.type().name() in {"usd", "usd_rop"}
                   for node in ropnodes)

        # The main ROP node, either a USD Rop or ROP network containing
        # multiple USD rops.
        node = instance[0]

        # Write out only this layer using the save pattern parameter
        # Match any filename with folders above it and match the
        # filename itself explicitly. THe match pattern is based on the
        # output path *after* the Output Processor. So we process the save
        # path manually beforehand too.
        fname = instance.data.get("usdFilename")

        # Enable Output Processors so it will always save any file
        # into our unique staging directory with processed Avalon paths
        processors = [
            "avalon_uri_processor",
            "stagingdir_processor"
        ]

        # Collect any output dependencies that have not been processed yet
        # during extraction of other instances
        outputs = [fname]
        for dependency in dependencies:
            if not dependency.data.get("_isExtracted", False):
                dependency_fname = dependency.data["usdFilename"]
                self.log.debug("Extracting dependency: %s" % dependency)

                # Find the file in this instance's staging directory
                dependency.data["files"] = [dependency_fname]
                dependency.data["stagingDir"] = staging_dir

                outputs.append(dependency_fname)
                dependency.data["_isExtracted"] = True

        # Run a stack of context managers before we start the render to
        # temporarily adjust USD ROP settings for our publish output.
        overrides = list()
        with ExitStack() as stack:

            for ropnode in ropnodes:
                manager = usdlib.outputprocessors(
                    ropnode,
                    processors=processors,
                    disable_all_others=True
                )
                stack.enter_context(manager)

                # Only write out specific USD files based on our outputs
                pattern = r"*[/\]{0} {0}"
                value = " ".join(pattern.format(fname) for fname in outputs)
                overrides.append([ropnode.parm("savepattern"),
                                  value])

                # We must add the after we entered the output processor context
                # manager  because this attribute only exists when the Output
                # Processor is added to the ROP node.
                # This sets staging directory on the processor to force our
                # output files to end up in the Staging Directory.
                name = "stagingdiroutputprocessor_stagingDir"
                overrides.append([ropnode.parm(name),
                                  staging_dir])

            stack.enter_context(parm_values(overrides))

            # Render the single ROP node or the full ROP network
            render(node)

        # Detect the output files in the Staging Directory
        path = os.path.join(staging_dir, fname)
        assert os.path.exists(path), "Output file must exist: %s" % path

        # Store the created files on the instance
        if "files" not in instance.data:
            instance.data["files"] = list()
        instance.data["files"].append(fname)

        #raise RuntimeError("Force no integration with a crash")