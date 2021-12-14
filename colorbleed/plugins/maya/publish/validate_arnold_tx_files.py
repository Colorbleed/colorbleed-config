import re
import os
import glob

import maya.cmds as cmds

import pyblish.api
import colorbleed.maya.action
import colorbleed.maya.lib as lib


def get_file_node_attrs():

    cmds.filePathEditor(refresh=True)
    node_attrs = {}
    for registered in cmds.filePathEditor(query=True,
                                          listRegisteredTypes=True):

        if registered == "reference":
            # Ignore references
            continue

        if registered == "file":
            # Somehow the registered type just lists "file"
            # without the attribute (similar to references)
            node = "file"
            attr = "fileTextureName"

        elif "." in registered:
            node, attr = registered.split(".", 1)

        else:
            # No attribute specified in the registered type
            # and thus it's non trivial to get the path?
            # todo: log this more from a debug - however using
            #       "logging" separate from Plug-in doesn't work with Pyblish?
            print("Unsupported file dependency type: %s" % registered)
            continue

        node_attrs[node] = attr

    return node_attrs

# Cache once on plug-in load
FILE_ATTR = get_file_node_attrs()


def get_file_node_attr(node):
    node_type = cmds.nodeType(node)
    attribute_name = FILE_ATTR[node_type]
    return "{}.{}".format(node, attribute_name)


def has_sequence_pattern(filepath):
    """Return whether file node uses an image sequence or single image.

    Determine if a node uses an image sequence or just a single image,
    not always obvious from its file path alone.

    Args:
        node (str): Name of the Maya node

    Returns:
        bool: True if node uses an image sequence

    """
    filepath_lower = filepath.lower()
    # The following tokens imply a sequence
    patterns = ["<udim>", "<tile>", "<uvtile>", "u<u>_v<v>", "<frame0"]
    return any(pattern in filepath_lower for pattern in patterns)


def seq_to_glob(path, force_use_file_sequence=False):
    """Takes an image sequence path and returns it in glob format,
    with the frame number replaced by a '*'.

    Image sequences may be numerical sequences, e.g. /path/to/file.1001.exr
    will return as /path/to/file.*.exr.

    Image sequences may also use tokens to denote sequences, e.g.
    /path/to/texture.<UDIM>.tif will return as /path/to/texture.*.tif.

    Args:
        path (str): the image sequence path
        force_use_file_sequence (bool): When enabled parse the file
            name as a file sequence even when no pattern is present.
            As such a filename like hello.0123.exr is changed to
            hello.*.exr.

    Returns:
        str: Return glob string that matches the filename pattern.

    """

    if path is None:
        return path

    # If any of the patterns, convert the pattern
    patterns = {
        "<udim>": "<udim>",
        "<tile>": "<tile>",
        "<uvtile>": "<uvtile>",
        "#": "#",
        "u<u>_v<v>": "<u>|<v>",
        "<frame0": "<frame0\d+>",
        "<f>": "<f>"
    }

    lower = path.lower()
    has_pattern = False
    for pattern, regex_pattern in patterns.items():
        if pattern in lower:
            path = re.sub(regex_pattern, "*", path, flags=re.IGNORECASE)
            has_pattern = True

    if has_pattern:
        return path

    if force_use_file_sequence:
        base = os.path.basename(path)
        matches = list(re.finditer(r'\d+', base))
        if matches:
            match = matches[-1]
            new_base = '{0}*{1}'.format(base[:match.start()],
                                        base[match.end():])
            head = os.path.dirname(path)
            return os.path.join(head, new_base)

    return path


def get_file_node_path(node):
    """Get the file path used by a Maya file node.

    Args:
        node (str): Name of the Maya file node

    Returns:
        str: the file path in use

    """

    if cmds.nodeType(node) == "file":
        # Special case for file nodes. If the path appears to be sequence, use
        # 'computedFileTextureNamePattern' this preserves the <> tag
        if cmds.attributeQuery('computedFileTextureNamePattern',
                               node=node,
                               exists=True):
            plug = '{0}.computedFileTextureNamePattern'.format(node)
            texture_pattern = cmds.getAttr(plug)

            patterns = ["<udim>",
                        "<tile>",
                        "u<u>_v<v>",
                        "<f>",
                        "<frame0",
                        "<uvtile>"]
            lower = texture_pattern.lower()
            if any(pattern in lower for pattern in patterns):
                return texture_pattern

        # otherwise use fileTextureName
        return cmds.getAttr('{0}.fileTextureName'.format(node))

    else:
        attribute = get_file_node_attr(node)
        return cmds.getAttr(attribute)


def get_file_node_files(node, replace_extension=None):
    """Return the file paths related to the file node

    Note:
        Will only return existing files. Returns an empty list
        if not valid existing files are linked.

    Returns:
        list: List of full file paths.

    """

    # Node has .useFrameExtension and it is enabled, then it's a sequence
    # This is supported by for example 'file' and 'aiImage' nodes.
    uses_frame_extension = False
    if cmds.attributeQuery("useFrameExtension", exists=True, node=node):
        frame_extension_attr = "{0}.useFrameExtension".format(node)
        uses_frame_extension = cmds.getAttr(frame_extension_attr)

    path = get_file_node_path(node)

    if replace_extension:
        base, _ = os.path.splitext(path)
        path = base + replace_extension

    path = cmds.workspace(expandName=path)
    if uses_frame_extension or has_sequence_pattern(path):
        glob_pattern = seq_to_glob(path)
        return glob.glob(glob_pattern)
    elif os.path.exists(path):
        return [path]
    else:
        return []


class ValidateArnoldTxFiles(pyblish.api.InstancePlugin):
    """Warn user when no .tx files on disk for used file nodes.

    When any file nodes detected that do not have matching .tx files on their
    location raise a warning. It is allowed to render without .tx files but
    it is likely slower than you'd like.

    """

    order = colorbleed.api.ValidateContentsOrder - 0.05
    label = "Arnold resources have .tx files"
    hosts = ["maya"]
    families = ["colorbleed.renderlayer.arnold"]
    actions = [colorbleed.maya.action.SelectInvalidAction]

    def process(self, instance):

        if instance.data.get("renderer", None) != "arnold":
            # If not rendering with Arnold, ignore..
            return

        invalid = self.get_invalid(instance)
        if invalid:
            self.log.warning("Found file nodes that don't have .tx "
                             "files: {}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):

        invalid = []
        file_nodes = cmds.ls(type="file")
        for node in file_nodes:
            files = get_file_node_files(node, replace_extension=".tx")
            if not files:
                path = get_file_node_path(node)
                cls.log.debug("No .tx files for: {}".format(path))
                invalid.append(node)

        return invalid
