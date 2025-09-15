#
# Python script for Blender (Version 1.2 - Blender 3.x/4.x API Fix)
#
# Author: Victor Do
#
# This script creates a black and white image mask from the currently selected faces
# of a mesh object. The selected faces will be rendered as white, and all unselected
# faces and the background will be black. The script is packaged as an add-on with a UI panel.
#

import bpy

# bl_info defines the add-on's properties for Blender
bl_info = {
    "name": "Create Image Mask from Selection",
    "author": "Victor Do",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N key) > Edit Tab",
    "description": "Creates a black and white image mask from selected faces.",
    "warning": "Object must have a UV map.",
    "doc_url": "",
    "category": "Object",
}


class MaskCreatorProperties(bpy.types.PropertyGroup):
    image_name: bpy.props.StringProperty(
        name="Image Name",
        description="Name for the newly created mask image",
        default="FaceMask",
    )
    
    image_size: bpy.props.IntProperty(
        name="Resolution",
        description="The width and height of the output mask image",
        default=4096,
        min=256,
        max=8192,
        step=1024,
    )

    margin: bpy.props.IntProperty(
        name="Margin",
        description="Pixel margin for the bake to prevent seams at UV edges",
        default=2,
        min=0,
        max=64,
    )


class MASK_OT_create_image_mask(bpy.types.Operator):
    """Creates a black and white image mask from the selected faces"""
    bl_idname = "object.create_image_mask"
    bl_label = "Create Face Mask"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and
                obj.type == 'MESH' and
                context.mode == 'EDIT_MESH')

    def execute(self, context):
        props = context.scene.mask_creator_props
        obj = context.active_object
        mesh = obj.data

        if not mesh.uv_layers:
            self.report({'ERROR'}, "Object has no UV map. Please unwrap the mesh first.")
            return {'CANCELLED'}

        if not any(p.select for p in mesh.polygons):
            self.report({'ERROR'}, "No faces are selected.")
            return {'CANCELLED'}
        
        selected_face_indices = {p.index for p in mesh.polygons if p.select}
        original_mode = context.mode
        original_engine = context.scene.render.engine
        original_material = obj.active_material
        bpy.ops.object.mode_set(mode='OBJECT')

        VCOL_LAYER_NAME = "temp_mask_vcol"
        if VCOL_LAYER_NAME in mesh.vertex_colors:
            mesh.vertex_colors.remove(mesh.vertex_colors[VCOL_LAYER_NAME])
        vc_layer = mesh.vertex_colors.new(name=VCOL_LAYER_NAME)
        
        # --- FIX ---
        # The line below was changed from 'mesh.vertex_colors.active_render = vc_layer'
        # to use the modern generic attribute system for Blender 3.0+
        mesh.attributes.active_color = mesh.attributes[VCOL_LAYER_NAME]
        # --- END FIX ---
        
        white = (1.0, 1.0, 1.0, 1.0)
        black = (0.0, 0.0, 0.0, 1.0)
        for poly in mesh.polygons:
            for loop_index in poly.loop_indices:
                vc_layer.data[loop_index].color = white if poly.index in selected_face_indices else black

        BAKE_MATERIAL_NAME = "temp_mask_bake_material"
        if BAKE_MATERIAL_NAME in bpy.data.materials:
            bpy.data.materials.remove(bpy.data.materials[BAKE_MATERIAL_NAME])
        bake_material = bpy.data.materials.new(name=BAKE_MATERIAL_NAME)
        bake_material.use_nodes = True
        nodes = bake_material.node_tree.nodes
        nodes.clear()
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        emission_node = nodes.new(type='ShaderNodeEmission')
        vcol_node = nodes.new(type='ShaderNodeVertexColor')
        vcol_node.layer_name = VCOL_LAYER_NAME
        bake_material.node_tree.links.new(vcol_node.outputs['Color'], emission_node.inputs['Color'])
        bake_material.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
        obj.data.materials.append(bake_material)
        obj.active_material_index = len(obj.data.materials) - 1

        image = bpy.data.images.new(
            name=props.image_name,
            width=props.image_size,
            height=props.image_size,
            alpha=False
        )
        image.colorspace_settings.name = 'Non-Color'
        image_node = nodes.new(type='ShaderNodeTexImage')
        image_node.image = image
        nodes.active = image_node

        self.report({'INFO'}, f"Baking mask to '{props.image_name}'...")
        context.scene.render.engine = 'CYCLES'
        bpy.ops.object.bake(
            type='EMIT',
            margin=props.margin,
            use_clear=True
        )

        mesh.vertex_colors.remove(vc_layer)
        obj.active_material = original_material
        bpy.data.materials.remove(bake_material)
        context.scene.render.engine = original_engine
        bpy.ops.object.mode_set(mode=original_mode)
        if original_mode == 'EDIT_MESH':
            bpy.ops.mesh.select_mode(type="FACE")
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            for i in selected_face_indices:
                mesh.polygons[i].select = True
            bpy.ops.object.mode_set(mode='EDIT')

        self.report({'INFO'}, f"Successfully created mask image '{props.image_name}'.")
        return {'FINISHED'}


class MASK_PT_panel(bpy.types.Panel):
    """Creates a UI Panel in the 3D view's sidebar"""
    bl_label = "Image Mask Creator"
    bl_idname = "MASK_PT_image_mask_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Edit'

    def draw(self, context):
        layout = self.layout
        if MASK_OT_create_image_mask.poll(context):
            props = context.scene.mask_creator_props
            col = layout.column(align=True)
            col.label(text="Mask Settings:")
            col.prop(props, "image_name")
            col.prop(props, "image_size")
            col.prop(props, "margin")
            col.separator()
            col.operator("object.create_image_mask", text="Create Mask from Selection", icon='MOD_MASK')
        else:
            layout.label(text="Select a Mesh object.")
            layout.label(text="Enter Edit Mode & select faces.")


classes = (
    MaskCreatorProperties,
    MASK_OT_create_image_mask,
    MASK_PT_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mask_creator_props = bpy.props.PointerProperty(type=MaskCreatorProperties)

def unregister():
    del bpy.types.Scene.mask_creator_props
    for cls in reversed(classes):
        bpy.utils