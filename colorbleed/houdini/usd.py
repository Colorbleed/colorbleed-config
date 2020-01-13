import os
import logging

from pxr import Usd, UsdGeom, Sdf, Kind

log = logging.getLogger(__name__)

# If you want to print things out, you can do:
# layer = stage.GetRootLayer()
# print layer.ExportToString()

# The predefined steps order used for bootstrapping USD Shots and Assets.
# These are ordered in order from strongest to weakest opinions, like in USD.
SHOT_PIPELINE = ["lighting", "fx", "sim", "anim", "layout"]
ASSET_PIPELINE = ["shade", "model"]
SHOT_PIPELINE_SUBSETS = ["usd" + step.title() for step in SHOT_PIPELINE]
ASSET_PIPELINE_SUBSETS = ["usd" + step.title() for step in ASSET_PIPELINE]


def create_asset(filepath,
                 asset_name,
                 reference_layers,
                 kind=Kind.Tokens.component):
    """
    Creates an asset file that consists of a top level layer and sublayers for
    shading and geometry.

    Args:
        filepath (str): Filepath where the asset.usd file will be saved.
        reference_layers (list): USD Files to reference in the asset.
            Note that the bottom layer (first file, like a model) would
            be last in the list. The strongest layer will be the first
            index.
        asset_name (str): The name for the Asset identifier and default prim.
        kind (pxr.Kind): A USD Kind for the root asset.

    """
    # Also see create_asset.py in PixarAnimationStudios/USD endToEnd example

    log.info("Creating asset at %s", filepath)

    # Make the layer ascii - good for readability, plus the file is small
    root_layer = Sdf.Layer.CreateNew(filepath, args={'format': 'usda'})
    stage = Usd.Stage.Open(root_layer)

    # Define a prim for the asset and make it the default for the stage.
    asset_prim = UsdGeom.Xform.Define(stage, '/%s' % asset_name).GetPrim()
    stage.SetDefaultPrim(asset_prim)

    # Let viewing applications know how to orient a free camera properly
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)

    # Usually we will "loft up" the kind authored into the exported geometry
    # layer rather than re-stamping here; we'll leave that for a later
    # tutorial, and just be explicit here.
    model = Usd.ModelAPI(asset_prim)
    if kind:
        model.SetKind(kind)

    model.SetAssetName(asset_name)
    model.SetAssetIdentifier('%s/%s.usd' % (asset_name, asset_name))

    # Add references to the  asset prim
    references = asset_prim.GetReferences()
    for reference_filepath in reference_layers:
        references.AddReference(reference_filepath)

    stage.GetRootLayer().Save()


def create_shot(filepath, layers, create_layers=False):
    """Create a shot with separate layers for departments.

    Args:
        filepath (str): Filepath where the asset.usd file will be saved.
        layers (str): When provided this will be added verbatim in the
            subLayerPaths layers. When the provided layer paths do not exist
            they are generated using  Sdf.Layer.CreateNew
        create_layers (bool): Whether to create the stub layers on disk if
            they do not exist yet.

    Returns:
        str: The saved shot file path

    """
    # Also see create_shot.py in PixarAnimationStudios/USD endToEnd example

    stage = Usd.Stage.CreateNew(filepath)
    log.info("Creating shot at %s" % filepath)

    for layer_path in layers:
        if create_layers and not os.path.exists(layer_path):
            # We use the Sdf API here to quickly create layers.  Also, we're
            # using it as a way to author the subLayerPaths as there is no
            # way to do that directly in the Usd API.
            layer_folder = os.path.dirname(layer_path)
            if not os.path.exists(layer_folder):
                os.makedirs(layer_folder)

            Sdf.Layer.CreateNew(layer_path)

        stage.GetRootLayer().subLayerPaths.append(layer_path)

    # Lets viewing applications know how to orient a free camera properly
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    stage.GetRootLayer().Save()

    return filepath


def create_stub_usd(filepath, default_prim_path="/root"):
    """Create USD file with empty default prim '/root'"""

    stage = Usd.Stage.CreateNew(filepath)
    prim = stage.DefinePrim(default_prim_path)
    stage.SetDefaultPrim(prim)
    stage.GetRootLayer().Save()

    return stage


def create_stub_usd_sdf_layer(filepath):
    """Create a new Sdf Layer.

    See:
        https://github.com/PixarAnimationStudios/USD/blob/master/extras/usd/
        tutorials/endToEnd/scripts/create_shot.py#L94

    """
    # We use the Sdf API here to quickly create layers.  Also, we're using it
    # as a way to author the subLayerPaths as there is no way to do that
    # directly in the Usd API.
    Sdf.Layer.CreateNew(filepath)


def pick_asset(node):
    """Show a user interface to select an Asset in the project

    When double clicking an asset it will set the Asset value in the
    'asset' parameter.

    """

    from avalon.vendor.Qt import QtCore, QtGui
    from avalon.tools.widgets import AssetWidget
    from avalon import style
    pos = QtGui.QCursor.pos()

    parm = node.parm("asset")
    if not parm:
        log.error("Node has no 'asset' parameter: %s", node)
        return

    # Construct the AssetWidget as a frameless popup so it automatically
    # closes when clicked outside of it.
    global tool
    tool = AssetWidget(silo_creatable=False)
    tool.setContentsMargins(5, 5, 5, 5)
    tool.setWindowTitle("Pick Asset")
    tool.setStyleSheet(style.load_stylesheet())
    tool.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Popup)
    tool.refresh()

    # Select the current asset if there is any
    name = parm.eval()
    if name:
        from avalon import io
        db_asset = io.find_one({"name": name, "type": "asset"})
        if db_asset:
            silo = db_asset.get("silo")
            if silo:
                tool.set_silo(silo)
            tool.select_assets([name], expand=True)

    # Show cursor (top right of window) near cursor
    tool.resize(250, 400)
    tool.move(tool.mapFromGlobal(pos) - QtCore.QPoint(tool.width(), 0))

    def set_parameter_callback(index):
        name = index.data(tool.model.DocumentRole)["name"]
        parm.set(name)
        tool.close()

    tool.view.doubleClicked.connect(set_parameter_callback)
    tool.show()

