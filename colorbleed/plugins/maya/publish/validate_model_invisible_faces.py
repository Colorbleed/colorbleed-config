from maya import cmds
import maya.api.OpenMaya as om

import pyblish.api
import colorbleed.api
import colorbleed.maya.action


def get_default_hide_face_data_members():
    """Returns members of the defaultHideFaceDataSet.

    Note that the face components are returned using the
    transform name as opposed to shape name, like:
        pCube1.f[0]
    As opposed to:
        pCubeShape1.f[0]

    """

    if not cmds.objExists("defaultHideFaceDataSet"):
        return []

    sel = om.MSelectionList()
    sel.add("defaultHideFaceDataSet")
    node = sel.getDependNode(0)
    members = om.MFnSet(node).getMembers(flatten=True)
    return list(members.getSelectionStrings())


class ValidateModelInvisibleFaces(pyblish.api.InstancePlugin):
    """Check whether meshes have invisible or hidden faces.

    This differentiates two different types of 'hidden' faces.

    1. *Invisible* faces are faces made invisible with:
        Edit Mesh > Assign Invisible Faces
        This is stored as `polyHole` data on the mesh.

    2. *Hidden* faces:
        Selected components -> Hide (CTRL+H)
        The faces are added into a `defaultHideFaceDataSet` set.

    """

    order = colorbleed.api.ValidateContentsOrder
    hosts = ["maya"]
    families = ["colorbleed.model"]
    label = "Mesh Hidden Face"
    actions = [colorbleed.maya.action.SelectInvalidAction]
    optional = True

    @classmethod
    def get_invalid(cls, instance):

        hidden_faces = get_default_hide_face_data_members()
        mesh_lookup = set(cmds.ls(hidden_faces, objectsOnly=True, long=True))

        invalid = []
        for mesh in cmds.ls(instance, type="mesh", long=True):

            # Invisible faces assigned with Edit Mesh > Assign Invisible Faces
            components = cmds.polyHole(mesh, query=True) or []
            if components:
                cls.log.warning("Mesh has invisible faces: %s" % mesh)
                invalid.append(mesh)
                continue

            # Check for hidden faces on this mesh
            if mesh in mesh_lookup:
                cls.log.warning("Mesh has hidden faces: %s" % mesh)
                invalid.append(mesh)
                continue

        return invalid

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Meshes have invisible faces: %s" % invalid)
