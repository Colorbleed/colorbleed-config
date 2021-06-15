# -*- coding: utf-8 -*-
"""Module handling expected render output from Maya.

This module is used in :mod:`collect_render` and :mod:`collect_vray_scene`.

Note:
    To implement new renderer, just create new class inheriting from
    :class:`ARenderProducts` and add it to :func:`RenderProducts.get()`.

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

import logging
import types
import re
import os
from abc import ABCMeta, abstractmethod

import six
import attr

from . import lib
from . import lib_rendersetup

from maya import cmds, mel

log = logging.getLogger(__name__)

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
    "vray": "V-Ray",
    "arnold": "Arnold",
    "renderman": "Renderman",
    "redshift": "Redshift",
}

# not sure about the renderman image prefix
IMAGE_PREFIXES = {
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
    frameStep = attr.ib(default=1)
    padding = attr.ib(default=4)
    renderProducts = attr.ib(init=False, default=attr.Factory(list))
   

@attr.s    
class RenderProduct(object):
    """Describes an image or other file-like artifact produced by a render.
    
    Warning:
        This currently does NOT return as a product PER render camera.
        A single Render Product will generate files per camera. E.g. with two
        cameras each render product generates two sequences on disk assuming
        the file path prefix correctly uses the <Camera> tokens.
    
    """
    productName = attr.ib()
    ext = attr.ib()                             # extension
    aov = attr.ib(default=None)                 # source aov
    driver = attr.ib(default=None)              # source driver
    multipart = attr.ib(default=False)          # multichannel file
    
    
def get(layer, render_instance=None):
    """Get render details and products for given renderer and render layer.

    Args:
        layer (str): Name of render layer
        render_instance (pyblish.api.Instance): Publish instance.
            If not provided an empty mock instance is used.

    Returns:
        ARenderProducts: The correct RenderProducts instance for that
            renderlayer.

    Raises:
        :exc:`UnsupportedRendererException`: If requested renderer
            is not supported. It needs to be implemented by extending
            :class:`ARenderProducts` and added to this methods ``if``
            statement.

    """

    if render_instance is None:
        # For now produce a mock instance
        class Instance(object):
            data = {}
        render_instance = Instance()
        
    renderer_name = lib.get_attr_in_layer(
        "defaultRenderGlobals.currentRenderer", 
        layer=layer
    )
    
    Renderer = {
        "arnold": RenderProductsArnold,
        "vray": RenderProductsVray,
        "redshift": RenderProductsRedshift,
        "renderman": RenderProductsRenderman
    }.get(renderer_name.lower(), None)
    if Renderer is None:
        raise UnsupportedRendererException(
            "unsupported {}".format(renderer_name)
        )
        
    return Renderer(layer, render_instance)


@six.add_metaclass(ABCMeta)
class ARenderProducts:
    """Abstract class with common code for all renderers.

    Attributes:
        renderer (str): name of renderer.

    """

    renderer = None
        
    def __init__(self, layer, render_instance):
        """Constructor."""
        self.layer = layer
        self.render_instance = render_instance
        self.multipart = False
        
        # Initialize
        self.layer_data = self._get_layer_data()
        self.layer_data.renderProducts = self.get_render_products()

    @abstractmethod
    def get_render_products(self):
        """To be implemented by renderer class.
        
        This should return a list of RenderProducts.
        
        Returns:
            list: List of RenderProduct
            
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
            >>> ARenderProducts.sanizite_camera_name('test:camera_01')
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
            # Fall back to scene name by default
            log.debug("Image prefix not set, using <Scene>")
            file_prefix = "<Scene>"
        
        layer_name = self.layer
        
        # If the Render Layer belongs to a Render Setup layer then the
        # output name is based on the Render Setup Layer name without
        # the `rs_` prefix.
        rs_layer = lib_rendersetup.get_rendersetup_layer(layer_name)
        if rs_layer:
            layer_name = rs_layer

        if self.layer == "defaultRenderLayer":
            # defaultRenderLayer renders as masterLayer
            layer_name = "masterLayer"
            
        # todo: Support Custom Frames sequences 0,5-10,100-120
        #       Deadline allows submitting renders with a custom frame list
        #       to support those cases we might want to allow 'custom frames'
        #       to be overridden to `ExpectFiles` class?
        layer_data = LayerMetadata(
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
            filePrefix=file_prefix
        )
        return layer_data

    def _generate_file_sequence(
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

    def get_files(self, product, camera):
        """Return list of expected files.

        It will translate render token strings  ('<RenderPass>', etc.) to
        their values. This task is tricky as every renderer deals with this
        differently. That's why we expose `get_files` as a method on the
        Renderer class so it can be overridden for complex cases.
        
        """
        return self._generate_file_sequence(
            self.layer_data, 
            force_aov_name=product.productName,
            force_ext=product.ext,
            force_cameras=[camera]
        )

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


class RenderProductsArnold(ARenderProducts):
    """Expected files for Arnold renderer.
    
    References:
        mtoa.utils.getFileName()
        mtoa.utils.ui.common.updateArnoldTargetFilePreview()

    Attributes:
        aiDriverExtension (dict): Arnold AOV driver extension mapping.
            Is there a better way?
        renderer (str): name of renderer.

    """
    
    renderer = "arnold"
    aiDriverExtension = {
        "jpeg": "jpg",
        "exr": "exr",
        "deepexr": "exr",
        "png": "png",
        "tiff": "tif",
        "mtoa_shaders": "ass",  # TODO: research what those last two should be
        "maya": "",
    }
        
    def _get_aov_render_products(self, aov):
        """Return all render products for the AOV"""
        
        products = list()
        aov_name = self._get_attr("%s.name" % aov)
        ai_drivers = cmds.listConnections("{}.outputs".format(aov),
                                          source=True, 
                                          destination=False, 
                                          type="aiAOVDriver") or []
                                          
        for ai_driver in ai_drivers:
            # todo: check aiAOVDriver.prefix as it could have 
            #       a custom path prefix set for this driver
            
            # Skip Drivers set only for GUI
            # 0: GUI, 1: Batch, 2: GUI and Batch
            output_mode = self._get_attr("{}.outputMode".format(ai_driver))
            if output_mode == 0: # GUI only
                log.warning("%s has Output Mode set to GUI, skipping...", ai_driver)
                continue
        
            ai_translator = self._get_attr("{}.aiTranslator".format(ai_driver))
            try:
                ext = self.aiDriverExtension[ai_translator]
            except KeyError:
                raise AOVError(
                    "Unrecognized arnold driver format for AOV - {}".format(aov_name)
                )
                
            # If aov RGBA is selected, arnold will translate it to `beauty`
            name = aov_name
            if name == "RGBA":
                name = "beauty"
                
            # Support Arnold light groups for AOVs
            # Global AOV: When disabled the main layer is not written: `{pass}`
            # All Light Groups: When enabled, a `{pass}_lgroups` file is written
            #                   this output is always merged into a single product.
            # - Light Groups List: When set, a product per light group is written.
            #                      e.g. {pass}_front, {pass}_rim
            global_aov = self._get_attr("{}.globalAov".format(aov))
            if global_aov:
                product = RenderProduct(productName=name, 
                                        ext=ext, 
                                        aov=aov_name,
                                        driver=ai_driver)
                products.append(product)
                
            all_light_groups = self._get_attr("{}.lightGroups".format(aov))
            if all_light_groups:
                # All light groups is enabled. A single multipart Render Product
                product = RenderProduct(productName=name + "_lgroups",
                                        ext=ext,
                                        aov=aov_name,
                                        driver=ai_driver,
                                        # Always multichannel output
                                        multipart=True)
                products.append(product)
            else:
                value = self._get_attr("{}.lightGroupsList".format(aov))
                if not value:
                    continue
                selected_light_groups = value.strip().split()
                for light_group in selected_light_groups:
                    # Render Product per selected light group
                    aov_light_group_name = "{}_{}".format(name, light_group)
                    product = RenderProduct(productName=aov_light_group_name,
                                            aov=aov_name,
                                            driver=ai_driver,
                                            ext=ext)
                    products.append(product)
                    
        return products

    def get_render_products(self):
        """Get all AOVs.

        See Also:
            :func:`ARenderProducts.get_render_products()`

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

        aovs = cmds.ls(type="aiAOV")
        if not use_ref_aovs:
            ref_aovs = cmds.ls(type="aiAOV", referencedNodes=True)
            aovs = list(set(aovs) - set(ref_aovs))
                    
        products = []
        
        # Append the AOV products
        for aov in aovs:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
                
            # For now stick to the legacy output format.
            aov_products = self._get_aov_render_products(aov)
            products.extend(aov_products)
            
        if not any(product.aov == "RGBA" for product in products):
            # Append default 'beauty' as this is arnolds default. 
            # If <RenderPass> token is specified and no AOVs are defined, this will be used.
            default_ext = self._get_attr("defaultRenderGlobals.imfPluginKey")
            
            # For legibility add the beauty layer as first entry
            products.insert(0, RenderProduct(productName="beauty",
                                             ext=default_ext,
                                             driver="defaultArnoldDriver"))
            
        # TODO: Output Denoising AOVs?
                
        return products


class RenderProductsVray(ARenderProducts):
    """Expected files for V-Ray renderer."""
    
    renderer = "vray"

    def get_renderer_prefix(self):
        """Get image prefix for V-Ray.

        This overrides :func:`ARenderProducts.get_renderer_prefix()` as
        we must add `<aov>` token manually.

        See also:
            :func:`ARenderProducts.get_renderer_prefix()`

        """
        prefix = super(RenderProductsVray, self).get_renderer_prefix()
        prefix = "{}_<aov>".format(prefix)
        return prefix

    def _get_layer_data(self):
        # type: () -> LayerMetadata
        """Override to get vray specific extension."""
        layer_data = super(RenderProductsVray, self)._get_layer_data()
        
        default_ext = self._get_attr("vraySettings.imageFormatStr")
        if default_ext in ["exr (multichannel)", "exr (deep)"]:
            default_ext = "exr"
        layer_data.defaultExt = default_ext
        layer_data.padding = self._get_attr("vraySettings.fileNamePadding")
        
        return layer_data

    def get_render_products(self):
        """Get all AOVs.

        See Also:
            :func:`ARenderProducts.get_render_products()`

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
        products = []
        products.append(RenderProduct(productName="", ext=default_ext))

        # handle aovs from references
        use_ref_aovs = self.render_instance.data.get(
            "useReferencedAovs", False) or False

        # this will have list of all aovs no matter if they are coming from
        # reference or not.
        aov_types = ["VRayRenderElement", "VRayRenderElementSet"]
        aovs = cmds.ls(type=aov_types)
        if not use_ref_aovs:
            ref_aovs = cmds.ls(type=aov_types, referencedNodes=True) or []
            aovs = list(set(aovs) - set(ref_aovs))

        for aov in aovs:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
                
            aov_name = self._get_vray_aov_name(aov)
            product = RenderProduct(productName=aov_name,
                                    ext=default_ext,
                                    aov=aov)
            products.append(product)

        return products

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


class RenderProductsRedshift(ARenderProducts):
    """Expected files for Redshift renderer.

    Attributes:

        unmerged_aovs (list): Name of aovs that are not merged into resulting
            exr and we need them specified in Render Products output.

    """

    renderer = "redshift"
    unmerged_aovs = {"Cryptomatte"}

    def get_renderer_prefix(self):
        """Get image prefix for Redshift.

        This overrides :func:`ARenderProducts.get_renderer_prefix()` as
        we must add `<aov>` token manually.

        See also:
            :func:`ARenderProducts.get_renderer_prefix()`

        """
        prefix = super(RenderProductsRedshift, self).get_renderer_prefix()
        prefix = "{}.<aov>".format(prefix)
        return prefix

    def get_render_products(self):
        """Get all AOVs.

        See Also:
            :func:`ARenderProducts.get_render_products()`

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
        multipart = bool(self._get_attr("redshiftOptions.exrForceMultilayer"))

        # Get Redshift Extension from image format
        image_format = self._get_attr("redshiftOptions.imageFormat")  # integer
        ext = mel.eval("redshiftGetImageExtension(%i)" % image_format)
        
        use_ref_aovs = self.render_instance.data.get(
            "useReferencedAovs", False) or False
    
        aovs = cmds.ls(type="RedshiftAOV")
        if not use_ref_aovs:
            ref_aovs = cmds.ls(type="RedshiftAOV", referencedNodes=True)
            aovs = list(set(aovs) - set(ref_aovs))

        products = []
        has_beauty_aov = False
        for aov in aovs:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
                
            aov_type = self._get_attr("%s.aovType" % aov)
            if multipart and aov_type not in self.unmerged_aovs:
                continue
                
            # Any AOVs that still get processed, like Cryptomatte
            # by themselves are not multipart files.
            aov_multipart = not multipart
                
            if aov_type == "Beauty":
                has_beauty_aov = True
                
            aov_name = self._get_attr("%s.name" % aov)
            
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

                for light_group in light_groups:
                    aov_light_group_name = "{}_{}".format(aov_name, light_group)
                    product = RenderProduct(productName=aov_light_group_name,
                                            aov=aov_name,
                                            ext=ext,
                                            multipart=aov_multipart)
                    products.append(product)

            # Redshift AOV Light Select always renders the global AOV
            # even when light groups are present so we don't need to
            # exclude it when light groups are active
            product = RenderProduct(productName=aov_name,
                                    aov=aov_name,
                                    ext=ext,
                                    multipart=aov_multipart)
            products.append(product)   
        
        # When a Beauty AOV is added manually, it will be rendered as
        # 'Beauty_other' in file name and "standard" beauty will have
        # 'Beauty' in its name. When disabled, standard output will be
        # without `Beauty`.
        beauty_name = "Beauty_other" if has_beauty_aov else ""
        products.insert(0,
                        RenderProduct(productName=beauty_name,
                                      ext=ext,
                                      multipart=multipart))

        return products

    @staticmethod
    def _get_redshift_light_groups():
        return sorted(mel.eval("redshiftAllAovLightGroups"))


class RenderProductsRenderman(ARenderProducts):
    """Expected files for Renderman renderer.

    Warning:
        This is very rudimentary and needs more love and testing.
    """
    
    renderer = "renderman"

    def get_render_products(self):
        """Get all AOVs.

        See Also:
            :func:`ARenderProducts.get_render_products()`

        """
        products = []

        default_ext = "exr"
        displays = cmds.listConnections("rmanGlobals.displays")
        for aov in displays:
            enabled = self._get_attr("{}.enabled".format(aov))
            if not enabled:
                continue
        
            aov_name = str(aov)
            if aov_name == "rmanDefaultDisplay":
                aov_name = "beauty"
                
            product = RenderProduct(productName=aov_name,
                                    ext=default_ext)
            products.append(product)

        return products

    def get_files(self, product, camera):
        """Get expected files.

        In renderman we hack it with prepending path. This path would
        normally be translated from `rmanGlobals.imageOutputDir`. We skip
        this and hardcode prepend path we expect. There is no place for user
        to mess around with this settings anyway and it is enforced in
        render settings validator.
        """
        files = super(RenderProductsRenderman, self).get_files(product, camera)

        layer_data = self.layer_data
        new_files = []
        for file in files:
            new_file = "{}/{}/{}".format(
                layer_data["sceneName"], layer_data["layerName"], file
            )
        new_files.append(new_file)

        return new_files


class AOVError(Exception):
    """Custom exception for determining AOVs."""


class UnsupportedRendererException(Exception):
    """Custom exception.

    Raised when requesting data from unsupported renderer.
    """
