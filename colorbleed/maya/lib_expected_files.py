# -*- coding: utf-8 -*-
"""Module handling expected render output from Maya.

This module is used in :mod:`collect_render` and :mod:`collect_vray_scene`.

Note:
    To implement new renderer, just create new class inheriting from
    :class:`AExpectedFiles` and add it to :func:`ExpectedFiles.get()`.

Attributes:
    R_SINGLE_FRAME (:class:`re.Pattern`): Find single frame number.
    R_FRAME_RANGE (:class:`re.Pattern`): Find frame range.
    R_FRAME_NUMBER (:class:`re.Pattern`): Find frame number in string.
    R_LAYER_TOKEN (:class:`re.Pattern`): Find layer token in image prefixes.
    R_AOV_TOKEN (:class:`re.Pattern`): Find AOV token in image prefixes.
    R_SUBSTITUTE_AOV_TOKEN (:class:`re.Pattern`): Find and substitute AOV token
        in image prefixes.
    R_REMOVE_AOV_TOKEN (:class:`re.Pattern`): Find and remove AOV token in
        image prefixes.
    R_CLEAN_FRAME_TOKEN (:class:`re.Pattern`): Find and remove unfilled
        Renderman frame token in image prefix.
    R_CLEAN_EXT_TOKEN (:class:`re.Pattern`): Find and remove unfilled Renderman
        extension token in image prefix.
    R_SUBSTITUTE_LAYER_TOKEN (:class:`re.Pattern`): Find and substitute render
        layer token in image prefixes.
    R_SUBSTITUTE_SCENE_TOKEN (:class:`re.Pattern`): Find and substitute scene
        token in image prefixes.
    R_SUBSTITUTE_CAMERA_TOKEN (:class:`re.Pattern`): Find and substitute camera
        token in image prefixes.
    RENDERER_NAMES (dict): Renderer names mapping between reported name and
        *human readable* name.
    IMAGE_PREFIXES (dict): Mapping between renderers and their respective
        image prefix attribute names.

Todo:
    Determine `multipart` from render instance.

"""
# WIP redo from OpenPype implementation
# Source: https://github.com/pypeclub/OpenPype/blob/aaf8048eb883733d9679915a70049d50440cdb8c/openpype/hosts/maya/api/expected_files.py

import types
import re
import os
from abc import ABCMeta, abstractmethod

import six
import attr

from . import lib

from maya import cmds, mel

R_SINGLE_FRAME = re.compile(r"^(-?)\d+$")
R_FRAME_RANGE = re.compile(r"^(?P<sf>(-?)\d+)-(?P<ef>(-?)\d+)$")
R_FRAME_NUMBER = re.compile(r".+\.(?P<frame>[0-9]+)\..+")
R_LAYER_TOKEN = re.compile(
    r".*((?:%l)|(?:<layer>)|(?:<renderlayer>)).*", re.IGNORECASE
)
R_AOV_TOKEN = re.compile(r".*%a.*|.*<aov>.*|.*<renderpass>.*", re.IGNORECASE)
R_SUBSTITUTE_AOV_TOKEN = re.compile(r"%a|<aov>|<renderpass>", re.IGNORECASE)
R_REMOVE_AOV_TOKEN = re.compile(
    r"_%a|\.%a|_<aov>|\.<aov>|_<renderpass>|\.<renderpass>", re.IGNORECASE)
# to remove unused renderman tokens
R_CLEAN_FRAME_TOKEN = re.compile(r"\.?<f\d>\.?", re.IGNORECASE)
R_CLEAN_EXT_TOKEN = re.compile(r"\.?<ext>\.?", re.IGNORECASE)

R_SUBSTITUTE_LAYER_TOKEN = re.compile(
    r"%l|<layer>|<renderlayer>", re.IGNORECASE
)
R_SUBSTITUTE_CAMERA_TOKEN = re.compile(r"%c|<camera>", re.IGNORECASE)
R_SUBSTITUTE_SCENE_TOKEN = re.compile(r"%s|<scene>", re.IGNORECASE)

RENDERER_NAMES = {
    "mentalray": "MentalRay",
    "vray": "V-Ray",
    "arnold": "Arnold",
    "renderman": "Renderman",
    "redshift": "Redshift",
}

# not sure about the renderman image prefix
IMAGE_PREFIXES = {
    "mentalray": "defaultRenderGlobals.imageFilePrefix",
    "vray": "vraySettings.fileNamePrefix",
    "arnold": "defaultRenderGlobals.imageFilePrefix",
    "renderman": "rmanGlobals.imageFileFormat",
    "redshift": "defaultRenderGlobals.imageFilePrefix",
}


@attr.s
class LayerMetadata(object):
    """Data class for Render Layer metadata."""
    frameStart = attr.ib()
    frameEnd = attr.ib()
    cameras = attr.ib()
    sceneName = attr.ib()
    layerName = attr.ib()
    renderer = attr.ib()
    defaultExt = attr.ib()
    filePrefix = attr.ib()
    enabledAOVs = attr.ib()
    frameStep = attr.ib(default=1)
    padding = attr.ib(default=4)


# todo: Simplify the API - this can work fine wiht ExpectedFiles class
#       removed and just a simple `get_renderlayer_info` function exposed
#       which returns a `LayerMetadata` like above INCLUDING the output
#       files.
class ExpectedFiles:
    """Class grouping functionality for all supported renderers.

    Attributes:
        multipart (bool): Flag if multipart exrs are used.

    """
    multipart = False

    def __init__(self, render_instance):
        """Constructor."""
        self._render_instance = render_instance
        self._renderer = None

    def get(self, layer):
        """Get expected files for given renderer and render layer.

        Args:
            renderer (str): Name of renderer
            layer (str): Name of render layer

        Returns:
            dict: Expected rendered files by AOV

        Raises:
            :exc:`UnsupportedRendererException`: If requested renderer
                is not supported. It needs to be implemented by extending
                :class:`AExpectedFiles` and added to this methods ``if``
                statement.

        """
        
        self.layer = layer
        renderer_name = lib.get_attr_in_layer(
            "defaultRenderGlobals.currentRenderer", 
            layer=layer
        )
        
        Renderer = {
            "arnold": ExpectedFilesArnold,
            "vray": ExpectedFilesVray,
            "redshift": ExpectedFilesRedshift,
            "mentalray": ExpectedFilesMentalray,
            "renderman": ExpectedFilesRenderman,

        }.get(renderer_name.lower(), None)
        if Renderer is None:
            raise UnsupportedRendererException(
                "unsupported {}".format(renderer_name)
            )
        
        renderer = Renderer(layer, self._render_instance)
        
        self._renderer = renderer
        return self._get_files(renderer)

    def _get_files(self, renderer):
        # type: (AExpectedFiles) -> list
        files = renderer.get_files()
        self.multipart = renderer.multipart
        return files


@six.add_metaclass(ABCMeta)
class AExpectedFiles:
    """Abstract class with common code for all renderers.

    Attributes:
        renderer (str): name of renderer.
        layer (str): name of render layer.
        multipart (bool): flag for multipart exrs.

    """

    renderer = None
    layer = None
    multipart = False

    def __init__(self, layer, render_instance):
        """Constructor."""
        self.layer = layer
        self.render_instance = render_instance

    @abstractmethod
    def get_aovs(self):
        """To be implemented by renderer class.
        
        This should return a list of tuples.
        Each tuple is formatted as: (AOV name, output extension)
        
        Returns:
            list: List of 2-tuples of (AOV name, output extension)
            
        """

    @staticmethod
    def sanitize_camera_name(camera):
        """Sanitize camera name.

        Remove Maya illegal characters from camera name.

        Args:
            camera (str): Maya camera name.

        Returns:
            (str): sanitized camera name

        Example:
            >>> AExpectedFiles.sanizite_camera_name('test:camera_01')
            test_camera_01

        """
        return re.sub('[^0-9a-zA-Z_]+', '_', camera)

    def get_renderer_prefix(self):
        """Return prefix for specific renderer.

        This is for most renderers the same and can be overridden if needed.

        Returns:
            str: String with image prefix containing tokens

        Raises:
            :exc:`UnsupportedRendererException`: If we requested image
                prefix for renderer we know nothing about.
                See :data:`IMAGE_PREFIXES` for mapping of renderers and
                image prefixes.

        """
        try:
            file_prefix_attr = IMAGE_PREFIXES[self.renderer]
        except KeyError:
            raise UnsupportedRendererException(
                "Unsupported renderer {}".format(self.renderer)
            )
        
        return self._get_attr(file_prefix_attr)

    def get_render_attribute(self, attribute):
        """Get attribute from render options.

        Args:
            attribute (str): name of attribute to be looked up.

        Returns:
            Attribute value

        """
        return self._get_attr("defaultRenderGlobals.{}".format(attribute))
        
    def _get_attr(self, attr):
        """Return the value of the attribute in the renderlayer"""
        return lib.get_attr_in_layer(attr, layer=self.layer)

    def _get_layer_data(self):
        # type: () -> LayerMetadata
        #                      ______________________________________________
        # ____________________/ ____________________________________________/
        # 1 -  get scene name  /__________________/
        # ____________________/
        _, scene_basename = os.path.split(cmds.file(q=True, loc=True))
        scene_name, _ = os.path.splitext(scene_basename)

        file_prefix = self.get_renderer_prefix()

        if not file_prefix:
            raise RuntimeError("Image prefix not set")

        layer_name = self.layer
        if self.layer == "defaultRenderLayer":
            # defaultRenderLayer renders as masterLayer
            layer_name = "masterLayer"
        
        elif self.layer.startswith("rs_"):
            layer_name = self.layer[3:]
            
        # todo: Support Custom Frames sequences 0,5-10,100-120
        #       Deadline allows submitting renders with a custom frame list
        #       to support those cases we might want to allow 'custom frames'
        #       to be overridden to `ExpectFiles` class?

        return LayerMetadata(
            frameStart=int(self.get_render_attribute("startFrame")),
            frameEnd=int(self.get_render_attribute("endFrame")),
            frameStep=int(self.get_render_attribute("byFrameStep")),
            padding=int(self.get_render_attribute("extensionPadding")),
            # if we have <camera> token in prefix path we'll expect output for
            # every renderable camera in layer.
            cameras=self.get_renderable_cameras(),
            sceneName=scene_name,
            layerName=layer_name,
            renderer=self.renderer,
            defaultExt=self._get_attr("defaultRenderGlobals.imfPluginKey"),
            filePrefix=file_prefix,
            enabledAOVs=self.get_aovs()
        )

    def _generate_single_file_sequence(
            self, layer_data, 
            force_aov_name=None, 
            force_ext=None,
            force_cameras=None):
        # type: (LayerMetadata, str, str) -> list
        expected_files = []
        cameras = force_cameras if force_cameras else layer_data.cameras
        ext = force_ext or layer_data.defaultExt
        for cam in cameras:
            file_prefix = layer_data.filePrefix
            mappings = (
                (R_SUBSTITUTE_SCENE_TOKEN, layer_data.sceneName),
                (R_SUBSTITUTE_LAYER_TOKEN, layer_data.layerName),
                (R_SUBSTITUTE_CAMERA_TOKEN, self.sanitize_camera_name(cam)),
                # this is required to remove unfilled aov token, for example
                # in Redshift
                (R_REMOVE_AOV_TOKEN, "") if not force_aov_name \
                else (R_SUBSTITUTE_AOV_TOKEN, force_aov_name),

                (R_CLEAN_FRAME_TOKEN, ""),
                (R_CLEAN_EXT_TOKEN, ""),
            )

            for regex, value in mappings:
                file_prefix = re.sub(regex, value, file_prefix)

            for frame in range(
                    int(layer_data.frameStart),
                    int(layer_data.frameEnd) + 1,
                    int(layer_data.frameStep),
            ):
                frame_str = str(frame).rjust(layer_data.padding, "0")
                expected_files.append(
                    "{}.{}.{}".format(file_prefix,frame_str, ext)
                )
        return expected_files

    def _generate_aov_file_sequences(self, layer_data):
        # type: (LayerMetadata) -> dict
        expected_files = {}
        for aov in sorted(layer_data.enabledAOVs):
            for cam in layer_data.cameras:
            
                aov_name = aov[0]
                aov_ext = aov[1]
            
                aov_files = self._generate_single_file_sequence(
                    layer_data, 
                    force_aov_name=aov_name,
                    force_ext=aov_ext,
                    force_cameras=[cam]
                )
            
                # if we have more then one renderable camera, append
                # camera name to AOV to allow per camera AOVs.
                # todo: confirm this actually happens even when <Camera>
                #       render token is in the file path prefix
                aov_name = aov[0]
                if len(layer_data.cameras) > 1:
                    aov_name = "{}_{}".format(aov[0],
                                              self.sanitize_camera_name(cam))

                expected_files[aov_name] = aov_files

        return expected_files

    def get_files(self):
        """Return list of expected files.

        It will translate render token strings  ('<RenderPass>', etc.) to
        their values. This task is tricky as every renderer deals with this
        differently. It depends on `get_aovs()` abstract method implemented
        for every supported renderer.

        """
        layer_data = self._get_layer_data()

        expected_files = []
        if layer_data.enabledAOVs:
            return self._generate_aov_file_sequences(layer_data)
        else:
            return self._generate_single_file_sequence(layer_data)

    def get_renderable_cameras(self):
        # type: () -> list
        """Get all renderable camera transforms.

        Returns:
            list: list of renderable cameras.

        """
        
        renderable_cameras = [
            cam for cam in cmds.ls(cameras=True) 
            if self._get_attr("{}.renderable".format(cam))
        ]
        
        # The output produces a sanitized name for <Camera> using its
        # shortest unique path of the transform so we'll return
        # at least that unique path. This could include a parent
        # name too when two cameras have the same name but are
        # in a different hierarchy, e.g. "group1|cam" and "group2|cam"
        def get_name(camera):
            return cmds.ls(cmds.listRelatives(camera,
                                              parent=True,
                                              fullPath=True))[0]

        return [get_name(cam) for cam in renderable_cameras]


class ExpectedFilesArnold(AExpectedFiles):
    """Expected files for Arnold renderer.

    Attributes:
        aiDriverExtension (dict): Arnold AOV driver extension mapping.
            Is there a better way?
        renderer (str): name of renderer.

    """

    aiDriverExtension = {
        "jpeg": "jpg",
        "exr": "exr",
        "deepexr": "exr",
        "png": "png",
        "tiff": "tif",
        "mtoa_shaders": "ass",  # TODO: research what those last two should be
        "maya": "",
    }

    def __init__(self, layer, render_instance):
        """Constructor."""
        super(ExpectedFilesArnold, self).__init__(layer, render_instance)
        self.renderer = "arnold"

    def get_aovs(self):
        """Get all AOVs.

        See Also:
            :func:`AExpectedFiles.get_aovs()`

        Raises:
            :class:`AOVError`: If AOV cannot be determined.

        """
        
        if not cmds.ls("defaultArnoldRenderOptions", type="aiOptions"):
            # this occurs when Render Setting windows was not opened yet. In
            # such case there are no Arnold options created so query for AOVs
            # will fail. We terminate here as there are no AOVs specified then.
            # This state will most probably fail later on some Validator
            # anyway.
            return []
        
        if not (
            self._get_attr("defaultArnoldRenderOptions.aovMode")
            and not self._get_attr("defaultArnoldDriver.mergeAOVs")  # noqa: W503, E501
        ):
            # AOVs are merged in multi-channel file
            self.multipart = True
            return []

        # AOVs are set to be rendered separately. We should expect
        # <RenderPass> token in path.

        # handle aovs from references
        use_ref_aovs = self.render_instance.data.get(
            "useReferencedAovs", False) or False

        ai_aovs = cmds.ls(type="aiAOV")
        if not use_ref_aovs:
            ref_aovs = cmds.ls(type="aiAOV", referencedNodes=True)
            ai_aovs = list(set(ai_aovs) - set(ref_aovs))

        enabled_aovs = []
        for aov in ai_aovs:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
            
            aov_name = self._get_attr("%s.name" % aov)
            ai_drivers = cmds.listConnections("{}.outputs".format(aov),
                                              source=True, 
                                              destination=False, 
                                              type="aiAOVDriver") or []
                                              
            if len(ai_drivers) > 1:
                # todo: the code below for multiple drivers is functional however
                #       the ExpectedFiles class merges into a dict by AOV key
                #       and thus overwrites it into just one aov output, losing
                #       the multiple drivers.
                raise NotImplementedError("Multiple drivers per AOV not implemented")
                                              
            for ai_driver in ai_drivers:
                # todo: check aiAOVDriver.outputMode as it could have 
                #       disabled an output driver for batch mode
                # todo: check aiAOVDriver.prefix as it could have 
                #       a custom path prefix set for this driver
            
                ai_translator = self._get_attr("{}.aiTranslator".format(ai_driver))
                try:
                    aov_ext = self.aiDriverExtension[ai_translator]
                except KeyError:
                    msg = (
                        "Unrecognized arnold " "driver format for AOV - {}"
                    ).format(aov_name)
                    raise AOVError(msg)
                    
                # If aov RGBA is selected, arnold will translate it to `beauty`
                if aov_name == "RGBA":
                    aov_name = "beauty"
                    
                # Support Arnold light groups for AOVs
                all_light_groups = self._get_attr("{}.lightGroups".format(aov))
                light_groups = []
                if all_light_groups:
                    # All light groups is enabled
                    light_groups = self._get_arnold_light_groups()
                else:
                    value = cmds.getAttr("{}.lightGroupsList".format(aov))
                    selected_light_groups = value.strip().split()
                    light_groups = selected_light_groups

                if light_groups:
                    for light_group in light_groups:
                        aov_light_group_name = "{}_{}".format(aov_name, light_group)
                        enabled_aovs.append((aov_light_group_name, aov_ext))
                else:
                    enabled_aovs.append((aov_name, aov_ext))
                
        # Append 'beauty' as this is arnolds
        # default. If <RenderPass> token is specified and no AOVs are
        # defined, this will be used.
        enabled_aovs.append(
            (u"beauty", self._get_attr("defaultRenderGlobals.imfPluginKey"))
        )
        return enabled_aovs
        
    @staticmethod
    def _get_arnold_light_groups():
        # reference: {arnold}\scripts\mtoa\ui\ae\aiAOVTemplate.py
        # loop over all light groups in the scene
        lights = cmds.ls(exactType=['pointLight',
                                    'directionalLight',
                                    'spotLight',
                                    'areaLight',
                                    'aiAreaLight',
                                    'aiSkyDomeLight',
                                    'aiMeshLight',
                                    'aiPhotometricLight'])

        existing_groups = set()
        for light in lights:
            light_group = cmds.getAttr(light + ".aiAov")
            if light_group:
                existing_groups.add(light_group)

        return sorted(list(existing_groups))


class ExpectedFilesVray(AExpectedFiles):
    """Expected files for V-Ray renderer."""

    def __init__(self, layer, render_instance):
        """Constructor."""
        super(ExpectedFilesVray, self).__init__(layer, render_instance)
        self.renderer = "vray"

    def get_renderer_prefix(self):
        """Get image prefix for V-Ray.

        This overrides :func:`AExpectedFiles.get_renderer_prefix()` as
        we must add `<aov>` token manually.

        See also:
            :func:`AExpectedFiles.get_renderer_prefix()`

        """
        prefix = super(ExpectedFilesVray, self).get_renderer_prefix()
        prefix = "{}_<aov>".format(prefix)
        return prefix

    def _get_layer_data(self):
        # type: () -> LayerMetadata
        """Override to get vray specific extension."""
        layer_data = super(ExpectedFilesVray, self)._get_layer_data()
        default_ext = self._get_attr("vraySettings.imageFormatStr")
        if default_ext in ["exr (multichannel)", "exr (deep)"]:
            default_ext = "exr"
        layer_data.defaultExt = default_ext
        layer_data.padding = self._get_attr("vraySettings.fileNamePadding")
        return layer_data

    def get_files(self):
        """Get expected files.

        This overrides :func:`AExpectedFiles.get_files()` as we
        we need to add one sequence for plain beauty if AOVs are enabled
        as vray output beauty without 'beauty' in filename.

        """
        expected_files = super(ExpectedFilesVray, self).get_files()

        layer_data = self._get_layer_data()
        
        # remove 'beauty' from filenames as vray doesn't output it
        update = {}
        if layer_data.enabledAOVs:
            for aov, seqs in expected_files.items():
                if aov == "beauty":
                    new_list = []
                    for seq in seqs:
                        new_list.append(seq.replace("_beauty", ""))
                    update[aov] = new_list
            expected_files.update(update)
            
        return expected_files

    def get_aovs(self):
        """Get all AOVs.

        See Also:
            :func:`AExpectedFiles.get_aovs()`

        """
        if not cmds.ls("vraySettings", type="VRaySettingsNode"):
            # this occurs when Render Setting windows was not opened yet. In
            # such case there are no VRay options created so query for AOVs
            # will fail. We terminate here as there are no AOVs specified then.
            # This state will most probably fail later on some Validator
            # anyway.
            return []

        image_format_str = self._get_attr("vraySettings.imageFormatStr")
        if image_format_str == "exr (multichannel)":
            # AOVs are merged in m-channel file
            self.multipart = True
            return []
            
        default_ext = image_format_str
        if default_ext in ["exr (multichannel)", "exr (deep)"]:
            default_ext = "exr"

        # add beauty as default
        enabled_aovs = []
        enabled_aovs.append(
            (u"beauty", default_ext)
        )

        # handle aovs from references
        use_ref_aovs = self.render_instance.data.get(
            "useReferencedAovs", False) or False

        # this will have list of all aovs no matter if they are coming from
        # reference or not.
        vr_aovs = cmds.ls(
            type=["VRayRenderElement", "VRayRenderElementSet"]) or []
        if not use_ref_aovs:
            ref_aovs = cmds.ls(
                type=["VRayRenderElement", "VRayRenderElementSet"],
                referencedNodes=True) or []
            # get difference
            vr_aovs = list(set(vr_aovs) - set(ref_aovs))

        for aov in vr_aovs:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
                
            aov_name = self._get_vray_aov_name(aov)
            enabled_aovs.append((aov_name, default_ext))

        return enabled_aovs

    @staticmethod
    def _get_vray_aov_name(node):
        """Get AOVs name from Vray.

        Args:
            node (str): aov node name.

        Returns:
            str: aov name.

        """
        vray_name = None
        vray_explicit_name = None
        vray_file_name = None
        for node_attr in cmds.listAttr(node):
            if node_attr.startswith("vray_filename"):
                vray_file_name = cmds.getAttr("{}.{}".format(node, node_attr))
            elif node_attr.startswith("vray_name"):
                vray_name = cmds.getAttr("{}.{}".format(node, node_attr))
            elif node_attr.startswith("vray_explicit_name"):
                vray_explicit_name = cmds.getAttr(
                    "{}.{}".format(node, node_attr))

            if vray_file_name is not None and vray_file_name != "":
                final_name = vray_file_name
            elif vray_explicit_name is not None and vray_explicit_name != "":
                final_name = vray_explicit_name
            elif vray_name is not None and vray_name != "":
                final_name = vray_name
            else:
                continue
            # special case for Material Select elements - these are named
            # based on the material they are connected to.
            if "vray_mtl_mtlselect" in cmds.listAttr(node):
                connections = cmds.listConnections(
                    "{}.vray_mtl_mtlselect".format(node))
                if connections:
                    final_name += '_{}'.format(str(connections[0]))
                    
            # todo: implement special case for VRayExtraTex and
            #       for velocity channels
            #       reference: https://github.com/Colorbleed/colorbleed-config/blob/153f1cfa7e46dec32dc65a4b7e7fa6c0d40f6adf/colorbleed/plugins/maya/publish/collect_render_layer_aovs.py#L115-L146

            return final_name


class ExpectedFilesRedshift(AExpectedFiles):
    """Expected files for Redshift renderer.

    Attributes:

        unmerged_aovs (list): Name of aovs that are not merged into resulting
            exr and we need them specified in expectedFiles output.

    """

    unmerged_aovs = {"Cryptomatte"}

    def __init__(self, layer, render_instance):
        """Construtor."""
        super(ExpectedFilesRedshift, self).__init__(layer, render_instance)
        self.renderer = "redshift"

    def get_renderer_prefix(self):
        """Get image prefix for Redshift.

        This overrides :func:`AExpectedFiles.get_renderer_prefix()` as
        we must add `<aov>` token manually.

        See also:
            :func:`AExpectedFiles.get_renderer_prefix()`

        """
        prefix = super(ExpectedFilesRedshift, self).get_renderer_prefix()
        prefix = "{}.<aov>".format(prefix)
        return prefix

    def get_files(self):
        """Get expected files.

        This overrides :func:`AExpectedFiles.get_files()` as we
        we need to add one sequence for plain beauty if AOVs are enabled
        as vray output beauty without 'beauty' in filename.

        """
        expected_files = super(ExpectedFilesRedshift, self).get_files()
        layer_data = self._get_layer_data()

        # Redshift doesn't merge Cryptomatte AOV to final exr. We need to check
        # for such condition and add it to list of expected files.
        # Always include cryptomatte as separate output files
        for aov in layer_data.enabledAOVs:
            if aov[0].lower() == "cryptomatte":
                aov_name = aov[0]
                sequence = self._generate_single_file_sequence(
                    layer_data,
                    force_aov_name=aov_name
                )
                expected_files[aov_name] = sequence

        if layer_data.enabledAOVs:
            # When a Beauty AOV is added manually, it will be rendered as
            # 'Beauty_other' in file name and "standard" beauty will have
            # 'Beauty' in its name. When disabled, standard output will be
            # without `Beauty`.
            if expected_files.get(u"Beauty"):
                # Rename Beauty to Beauty_Other
                sequence = expected_files.pop(u"Beauty")
                sequence = [
                    item.replace(".Beauty", ".Beauty_other")
                    for item in sequence
                ]
                expected_files[u"Beauty_other"] = sequence
                
                # Add the new Beauty AOV
                expected_files[u"Beauty"] = self._generate_single_file_sequence(  # noqa: E501
                    layer_data, force_aov_name="Beauty"
                )
            else:
                expected_files[u"Beauty"] = self._generate_single_file_sequence(  # noqa: E501
                    layer_data
                )

        return expected_files

    def get_aovs(self):
        """Get all AOVs.

        See Also:
            :func:`AExpectedFiles.get_aovs()`

        """
        
        if not cmds.ls("redshiftOptions", type="RedshiftOptions"):
            # this occurs when Render Setting windows was not opened yet. In
            # such case there are no Redshift options created so query for AOVs
            # will fail. We terminate here as there are no AOVs specified then.
            # This state will most probably fail later on some Validator
            # anyway.
            return []

        # For Redshift we don't directly return upon forcing multilayer
        # due to some AOVs still being written into separate files, 
        # like Cryptomatte.
        # AOVs are merged in multi-channel file
        self.multipart = bool(self._get_attr("redshiftOptions.exrForceMultilayer"))

        # Get Redshift Extension from image format
        image_format = self._get_attr("redshiftOptions.imageFormat")  # integer
        aov_ext = mel.eval("redshiftGetImageExtension(%i)" % image_format)
        
        use_ref_aovs = self.render_instance.data.get(
            "useReferencedAovs", False) or False

        rs_aovs = cmds.ls(type="RedshiftAOV")
        if not use_ref_aovs:
            ref_aovs = cmds.ls(type="RedshiftAOV", referencedNodes=True)
            rs_aovs = list(set(ai_aovs) - set(ref_aovs))

        enabled_aovs = []
        for aov in rs_aovs:
            enabled = self._get_attr("{}.enabled".format(aov))
            print(aov)
            if not enabled:
                continue
                
            # If AOVs are merged into multipart exr, append AOV only if it
            # is in the list of AOVs that renderer cannot (or will not)
            # merge into final exr.
            aov_name = self._get_attr("%s.name" % aov)
            if self.multipart and aov_name not in self.unmerged_aovs:
                continue
            
            # todo: Redshift skips rendering of masterlayer without AOV suffix
            #       when a Beauty AOV is rendered. It overrides the main layer.
            #       >>> cmds.getAttr(aov + ".aovType") == "Beauty"
            #       Reference: https://github.com/Colorbleed/colorbleed-config/blob/153f1cfa7e46dec32dc65a4b7e7fa6c0d40f6adf/colorbleed/plugins/maya/publish/collect_render_layer_aovs.py#L178-L182
                
            # Support light Groups
            light_groups = []
            if self._get_attr("{}.supportsLightGroups".format(aov)):
                all_light_groups = self._get_attr("{}.allLightGroups".format(aov))
                if all_light_groups:
                    # All light groups is enabled
                    light_groups = self._get_redshift_light_groups()
                else:
                    value = self._get_attr("{}.lightGroupList".format(aov))
                    # note: string value can return None when never set
                    if value:
                        selected_light_groups = value.strip().split()
                        light_groups = selected_light_groups

                if light_groups:
                    for light_group in light_groups:
                        aov_light_group_name = "{}_{}".format(aov_name, light_group)
                        enabled_aovs.append((aov_light_group_name, aov_ext))

            # Redshift AOV Light Select always renders the global AOV
            # even when light groups are present so we don't need to
            # exclude it when light groups are active
            enabled_aovs.append((aov_name, aov_ext))

        return enabled_aovs

    @staticmethod
    def _get_redshift_light_groups():
        return sorted(mel.eval("redshiftAllAovLightGroups"))


class ExpectedFilesRenderman(AExpectedFiles):
    """Expected files for Renderman renderer.

    Warning:
        This is very rudimentary and needs more love and testing.
    """

    def __init__(self, layer, render_instance):
        """Constructor."""
        super(ExpectedFilesRenderman, self).__init__(layer, render_instance)
        self.renderer = "renderman"

    def get_aovs(self):
        """Get all AOVs.

        See Also:
            :func:`AExpectedFiles.get_aovs()`

        """
        enabled_aovs = []

        default_ext = "exr"
        displays = cmds.listConnections("rmanGlobals.displays")
        for aov in displays:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
        
            aov_name = str(aov)
            if aov_name == "rmanDefaultDisplay":
                aov_name = "beauty"
                
            enabled_aovs.append((aov_name, default_ext))

        return enabled_aovs

    def get_files(self):
        """Get expected files.

        This overrides :func:`AExpectedFiles.get_files()` as we
        we need to add one sequence for plain beauty if AOVs are enabled
        as vray output beauty without 'beauty' in filename.

        In renderman we hack it with prepending path. This path would
        normally be translated from `rmanGlobals.imageOutputDir`. We skip
        this and hardcode prepend path we expect. There is no place for user
        to mess around with this settings anyway and it is enforced in
        render settings validator.
        """
        layer_data = self._get_layer_data()
        new_expected_files = {}

        expected_files = super(ExpectedFilesRenderman, self).get_files()
        # we always get beauty
        for aov, files in expected_files.items():
            new_files = []
            for file in files:
                new_file = "{}/{}/{}".format(
                    layer_data["sceneName"], layer_data["layerName"], file
                )
                new_files.append(new_file)
            new_expected_files[aov] = new_files

        return new_expected_files


class ExpectedFilesMentalray(AExpectedFiles):
    """Skeleton unimplemented class for Mentalray renderer."""

    def __init__(self, layer, render_instance):
        """Constructor.

        Raises:
            :exc:`UnimplementedRendererException`: as it is not implemented.

        """
        super(ExpectedFilesMentalray, self).__init__(layer, render_instance)
        raise UnimplementedRendererException("Mentalray not implemented")

    def get_aovs(self):
        """Get all AOVs.

        See Also:
            :func:`AExpectedFiles.get_aovs()`

        """
        return []


class AOVError(Exception):
    """Custom exception for determining AOVs."""


class UnsupportedRendererException(Exception):
    """Custom exception.

    Raised when requesting data from unsupported renderer.
    """


class UnimplementedRendererException(Exception):
    """Custom exception.

    Raised when requesting data from renderer that is not implemented yet.
    """
