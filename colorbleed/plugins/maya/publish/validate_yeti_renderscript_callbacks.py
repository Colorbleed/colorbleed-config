import re
from maya import cmds

import pyblish.api
import colorbleed.api


class ValidateYetiRenderScriptCallbacks(pyblish.api.InstancePlugin):
    """Check if the render script callbacks will be used during the rendering

    In order to ensure the render tasks are executed properly we need to check
    if the pre and post render callbacks are actually used.

    For example:
        Yeti is not loaded but its callback scripts are still set in the
        render settings. This will cause an error because Maya tries to find
        and execute the callbacks.

    Developer note:
         The pre and post render callbacks cannot be overridden

    """

    order = colorbleed.api.ValidateContentsOrder
    label = "Yeti Render Script Callbacks"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer"]
    actions = [colorbleed.api.RepairAction]

    # Settings per renderer
    callbacks = {
        "vray": {
            "pre": "catch(`pgYetiVRayPreRender`)",
            "post": "catch(`pgYetiVRayPostRender`)"
        },
        "arnold": {
            "pre": "pgYetiPreRender"
        }
    }

    @classmethod
    def is_yeti_callbacks_needed(cls, instance):
        """Return whether current scene requires Yeti callbacks for render"""

        renderer = instance.data["renderer"]
        if renderer == "redshift":
            cls.log.info("Redshift ignores any pre and post render callbacks")
            return False

        yeti_loaded = cmds.pluginInfo("pgYetiMaya", query=True, loaded=True)
        if yeti_loaded:
            # The pre and post render MEL scripts are only needed whenever
            # there is a pgYetiMaya node present in the scene
            if cmds.ls(type="pgYetiMaya"):
                return True

        return False

    @classmethod
    def compute_required_callbacks(cls, instance):
        """Compute pre and post callbacks that should be included/excluded.

        What callback needs to be included or excluded depends on the usage of
        Yeti and the renderer. By default we consider all callbacks must be
        excluded, unless Yeti is being used. Then we force the callback for
        the active renderer to have the correct callback included.

        """

        includes = {"pre": [], "post": []}
        excludes = {"pre": [], "post": []}

        # Collect all callbacks
        exclude_pres = set()
        exclude_posts = set()
        for callbacks in cls.callbacks.values():
            pre = callbacks.get("pre", None)
            if pre:
                exclude_pres.add(pre)

            post = callbacks.get("post", None)
            if post:
                exclude_posts.add(post)

        # Figure out which Yeti callbacks are needed
        if cls.is_yeti_callbacks_needed(instance):
            renderer = instance.data["renderer"]
            renderer_callbacks = cls.callbacks.get(renderer, {})
            if not renderer_callbacks:
                raise RuntimeError("Renderer '%s' is not supported for Yeti "
                                   "with this validator." % renderer)

            # Add required pre callback to includes and remove from excludes
            pre = renderer_callbacks.get("pre", None)
            if pre:
                exclude_pres.discard(pre)
                includes["pre"].append(pre)

            post = renderer_callbacks.get("post", None)
            if post:
                exclude_posts.discard(post)
                includes["post"].append(post)

        # Any remaining Yeti callbacks not for this render should be removed
        # as such we just conider that the exclude list.
        excludes["pre"] = list(exclude_pres)
        excludes["post"] = list(exclude_posts)

        return includes, excludes

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Invalid render callbacks found for '%s'!"
                             % instance.name)

    @classmethod
    def get_invalid(cls, instance):

        pre_mel = cmds.getAttr("defaultRenderGlobals.preMel") or ""
        post_mel = cmds.getAttr("defaultRenderGlobals.postMel") or ""
        if pre_mel.strip():
            cls.log.debug("Found pre mel: `%s`" % pre_mel)

        if post_mel.strip():
            cls.log.debug("Found post mel: `%s`" % post_mel)

        invalid = False
        includes, excludes = cls.compute_required_callbacks(instance)

        # Includes should be included in pre/post mel script for render.
        for cmd in includes["pre"]:
            pattern = re.escape(cmd)
            if not re.search(pattern, pre_mel):
                cls.log.error("Missing pre render callback: %s" % cmd)
                invalid = True

        for cmd in includes["post"]:
            pattern = re.escape(cmd)
            if not re.search(pattern, post_mel):
                cls.log.error("Missing post render callback: %s" % cmd)
                invalid = True

        # Excludes should be removed from callbacks
        for cmd in excludes["pre"]:
            pattern = re.escape(cmd)
            if re.search(pattern, pre_mel):
                cls.log.error("Found invalid pre render callback: %s" % cmd)
                invalid = True

        for cmd in excludes["post"]:
            pattern = re.escape(cmd)
            if re.search(pattern, post_mel):
                cls.log.error("Found invalid post render callback: %s" % cmd)
                invalid = True

        return invalid

    @classmethod
    def repair(cls, instance):

        pre_mel = cmds.getAttr("defaultRenderGlobals.preMel") or ""
        post_mel = cmds.getAttr("defaultRenderGlobals.postMel") or ""
        includes, excludes = cls.compute_required_callbacks(instance)

        # A potential suffix for the callback that we also want to remove
        # when present to produce a clean result
        space_semicolon_space = r"[ ]*;?[ ]*"

        # Fix excludes
        for cmd in excludes["pre"]:
            pattern = re.escape(cmd) + space_semicolon_space
            pre_mel = re.sub(pattern, "", pre_mel)

        for cmd in excludes["post"]:
            pattern = re.escape(cmd) + space_semicolon_space
            post_mel = re.sub(pattern, "", post_mel)

        # Fix includes
        for cmd in includes["pre"]:
            pattern = re.escape(cmd)
            if not re.search(pattern, pre_mel):
                pre_mel = "{0}; {1}".format(cmd, pre_mel)

        for cmd in includes["post"]:
            pattern = re.escape(cmd)
            if not re.search(pattern, post_mel):
                post_mel = "{0}; {1}".format(cmd, post_mel)

        cls.log.info("Setting pre-mel: %s" % pre_mel)
        cls.log.info("Setting post-mel: %s" % post_mel)

        # Apply the new pre and post mel
        cmds.setAttr("defaultRenderGlobals.preMel", pre_mel, type="string")
        cmds.setAttr("defaultRenderGlobals.postMel", post_mel, type="string")
