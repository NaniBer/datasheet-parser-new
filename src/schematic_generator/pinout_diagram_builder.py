"""
Pinout Diagram Builder - Generate schematic symbols for circuit diagrams.

Creates schematic symbols (pinout diagrams) showing component function:
- Rectangle body with pins arranged around it
- Pin names/numbers labeled
- Pin "legs" extending from body
- DesignatorName and PackageValue labels

This is NOT a PCB footprint - it's for circuit schematic diagrams.
For PCB manufacturing layouts, use pcb_footprint_builder.py.
"""

import logging
import os
from typing import List, Dict, Any, Optional

import cadquery as cq

from ..package_types import (
    PackageType,
    SchematicParameters,
    get_schematic_parameters,
)
from ..core import optimize_glb_hierarchy
from .pin_layout import PinPosition, layout_pins

# Setup logging
logger = logging.getLogger(__name__)


def _normalize_schematic_bodyline_name(glb_path: str) -> None:
    """
    Ensure the BodyLine node has exactly one child named "BodyLine".

    The reference schematic.glb hierarchy is:
        BodyLine
        └── BodyLine [mesh]

    CadQuery requires unique names, so the inner shape is built as
    "BodyLine_shape". The optimizer may then collapse the wrapper entirely,
    leaving BodyLine as a leaf with a mesh. This function restores the
    correct two-level structure in both cases:

    Case A — wrapper still present (BodyLine → BodyLine_shape [mesh]):
        Rename the child to "BodyLine".

    Case B — optimizer collapsed to leaf (BodyLine [mesh]):
        Inject a new child "BodyLine" that carries the mesh; clear the
        mesh reference from the BodyLine container node.
    """
    try:
        from pygltflib import GLTF2, Node
    except ImportError:
        return

    gltf = GLTF2().load_binary(str(glb_path))
    if not gltf.scenes or not gltf.scenes[0].nodes:
        return

    package_index = gltf.scenes[0].nodes[0]
    bodyline_index = None
    for child_index in (gltf.nodes[package_index].children or []):
        if gltf.nodes[child_index].name == "BodyLine":
            bodyline_index = child_index
            break
    if bodyline_index is None:
        return

    bodyline_node = gltf.nodes[bodyline_index]

    if bodyline_node.mesh is not None:
        # Case B: optimizer collapsed everything into the BodyLine leaf.
        # Inject a child node that carries the mesh.
        child = Node(name="BodyLine", mesh=bodyline_node.mesh)
        child_index = len(gltf.nodes)
        gltf.nodes.append(child)
        bodyline_node.mesh = None
        bodyline_node.children = [child_index]
    else:
        # Case A: child wrapper is still present; rename it.
        for child_index in (bodyline_node.children or []):
            gltf.nodes[child_index].name = "BodyLine"

    gltf.save(str(glb_path))


class PinoutDiagramBuilder:
    """
    Build pinout diagram symbols using cadquery.

    Creates assembly hierarchy:
    Package (main)
    ├── BodyLine (wireframe border)
    │   ├── BodyLine_Top
    │   ├── BodyLine_Bottom
    │   ├── BodyLine_Left
    │   └── BodyLine_Right
    ├── Legs (all pins)
    │   ├── pin1 (leg, text, num)
    │   ├── pin2 (leg, text, num)
    │   └── ...
    ├── DesignatorName ("U")
    └── PackageValue (component name)
    """

    # Colors matching sample.gltf
    BLACK_COLOR = cq.Color(0, 0, 0, 1.0)
    PIN_COLOR = cq.Color(
        0.33725490196078434,
        0.12941176470588237,
        0.44313725490196076,
        1.0
    )

    def __init__(self, package_type: str, pin_count: int, component_name: str = "IC", custom_layout: Optional[Dict[str, List[int]]] = None, pin_data: Optional[List[Dict[str, Any]]] = None):
        """
        Initialize pinout diagram builder.

        Args:
            package_type: Package type (e.g., "DIP-8", "LQFP64")
            pin_count: Number of pins
            component_name: Component name for PackageValue label
            custom_layout: Optional dict mapping side names to pin numbers
                         (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})
            pin_data: Optional enriched pin dicts (carry role/nc). When present
                      and no explicit custom_layout is given, pins that clear the
                      SYM-04 gate are laid out by function (Slice C.4b); otherwise
                      the physical layout is used unchanged.
        """
        self.package_type = package_type
        self.pin_count = pin_count
        self.component_name = component_name
        self.custom_layout = custom_layout

        # Get schematic parameters
        self.params = get_schematic_parameters(package_type, pin_count)

        # SYM-04: functional grouping. An explicit Vision custom_layout is
        # authoritative and always wins; otherwise, when the pins clear the gate
        # (concrete power+ground, >=50% concrete roles), lay them out by function
        # and resize the body to fit. Below the gate, layout_arg stays the
        # original custom_layout (usually None) => byte-identical physical layout.
        layout_arg: Optional[Dict[str, List]] = custom_layout
        if custom_layout is None and pin_data:
            from ..models import functional_layout_applicable
            if functional_layout_applicable([p.get("role") for p in pin_data]):
                from .functional_layout import apply_functional_layout
                layout_arg = apply_functional_layout(pin_data, self.params)
                logger.info(
                    "SYM-04 functional layout: %s",
                    {k: [n for n in v if n] for k, v in layout_arg.items() if any(v)},
                )

        # Calculate pin positions
        self.pin_positions = layout_pins(self.params, layout_arg)

        logger.info(
            "Initialized schematic builder for %s (%d pins)" % (package_type, pin_count)
        )
        logger.info(
            "Body: %.1f x %.1f mm" % (self.params.body_width, self.params.body_height)
        )

    def build_pin_markers(self) -> cq.Assembly:
        """
        Build pin 1 marker (dot) and orientation notch.

        Returns:
            Assembly with Pin1Dot and Notch components
        """
        markers_assy = cq.Assembly(name="PinMarkers")

        # Pin 1 dot marker - at top-left corner of body
        dot_radius = 0.6  # Size of dot marker (mm)
        dot_height = 0.3  # Thickness of dot (mm)
        dot_offset = 1.5  # Offset from body corner (mm)

        # Dot position: top-left corner of body (inside the body)
        dot_x = -self.params.body_width / 2 + dot_offset
        dot_y = self.params.body_height / 2 - dot_offset

        pin1_dot = cq.Workplane("XY").center(dot_x, dot_y).circle(dot_radius).extrude(dot_height)
        markers_assy.add(pin1_dot, name="Pin1Dot", color=self.BLACK_COLOR)

        # Notch indicator - semicircle on top edge (centered)
        notch_radius = 2.0  # Size of notch (mm)
        notch_height = 0.3  # Thickness of notch (mm)

        # Create a semicircle notch centered on top edge
        # Start from left point, arc to right point, then close
        notch = (cq.Workplane("XY")
                 .center(0, self.params.body_height / 2)
                 .moveTo(-notch_radius, 0)
                 .threePointArc((0, notch_radius), (notch_radius, 0))
                 .close()
                 .extrude(notch_height))
        markers_assy.add(notch, name="Notch", color=self.BLACK_COLOR)

        return markers_assy

    def build_body_border(self) -> cq.Assembly:
        """
        Build wireframe border for IC body.

        Creates a single fused border shape (4 sides united) to match the
        reference schematic.glb which has one BodyLine [mesh] child.

        Hierarchy:
        BodyLine
        └── BodyLine [mesh]
        """
        bw = self.params.body_width
        bh = self.params.body_height
        thick = self.params.body_geometry.border_thickness
        height = self.params.body_geometry.border_height

        # Build 4 sides and fuse into a single mesh
        top    = cq.Workplane("XY").center(0,        bh / 2).rect(bw, thick).extrude(height)
        bottom = cq.Workplane("XY").center(0,       -bh / 2).rect(bw, thick).extrude(height)
        left   = cq.Workplane("XY").center(-bw / 2,       0).rect(thick, bh).extrude(height)
        right  = cq.Workplane("XY").center( bw / 2,       0).rect(thick, bh).extrude(height)
        border = top.union(bottom).union(left).union(right)

        body_line = cq.Assembly(name="BodyLine")
        # CadQuery requires globally unique names; use a temp name here.
        # save_glb() renames this to "BodyLine" after export so the final
        # hierarchy matches the reference: BodyLine > BodyLine [mesh].
        body_line.add(border, name="BodyLine_shape", color=self.BLACK_COLOR)
        return body_line

    def build_pin(
        self, pin_pos: PinPosition, pin_name: str = "", pin_number: str = ""
    ) -> cq.Assembly:
        """
        Build pin assembly.

        Hierarchy matches reference schematic.glb:
        <pin_number>
        ├── leg [mesh]
        ├── pinPoint [mesh]
        ├── text [mesh]
        ├── boundingBox [mesh]
        └── pinName [mesh]

        Args:
            pin_pos: Pin position from layout algorithm
            pin_name: Pin function name (e.g., "GND", "VCC")
            pin_number: Pin number (e.g., "1", "A1")

        Returns:
            Single assembly containing all pin components as children
        """
        pin_assy = cq.Assembly(name=pin_number)

        leg_length = self.params.pin_geometry.leg_length
        leg_width = self.params.pin_geometry.leg_width
        leg_thickness = self.params.pin_geometry.leg_thickness

        # 1. leg — thin rectangle extending from body edge outward
        if pin_pos.side in ["left", "right"]:
            offset = leg_length / 2 if pin_pos.side == "right" else -leg_length / 2
            pin_leg = (cq.Workplane("XY").center(pin_pos.x + offset, pin_pos.y)
                       .rect(leg_length, leg_width).extrude(leg_thickness))
        else:  # top or bottom
            offset = -leg_length / 2 if pin_pos.side == "bottom" else leg_length / 2
            pin_leg = (cq.Workplane("XY").center(pin_pos.x, pin_pos.y + offset)
                       .rect(leg_width, leg_length).extrude(leg_thickness))
        pin_assy.add(pin_leg, name="leg", color=self.PIN_COLOR)

        # 2. pinPoint — small dot at the outer tip of the leg (wire connection point)
        dot_r = leg_width * 1.5
        if pin_pos.side == "left":
            pt_x, pt_y = pin_pos.x - leg_length, pin_pos.y
        elif pin_pos.side == "right":
            pt_x, pt_y = pin_pos.x + leg_length, pin_pos.y
        elif pin_pos.side == "top":
            pt_x, pt_y = pin_pos.x, pin_pos.y + leg_length
        else:  # bottom
            pt_x, pt_y = pin_pos.x, pin_pos.y - leg_length
        pin_point = cq.Workplane("XY").center(pt_x, pt_y).circle(dot_r).extrude(leg_thickness)
        pin_assy.add(pin_point, name="pinPoint", color=self.PIN_COLOR)

        # 3. text — pin number label
        num_size = self.params.pin_geometry.pin_num_size
        num_height = self.params.pin_geometry.pin_num_height
        num_assy = cq.Assembly(name="text")
        if pin_pos.side in ["top", "bottom"]:
            direction = -1 if pin_pos.side == "top" else 1
            char_spacing = num_size * 1.2
            for i, char in enumerate(pin_number):
                if not char.strip():
                    continue
                char_y = pin_pos.num_y + (i * char_spacing * direction)
                try:
                    char_wp = cq.Workplane("XY").center(
                        pin_pos.num_x, char_y
                    ).text(char, num_size, num_height, halign="center")
                    num_assy.add(char_wp, color=self.BLACK_COLOR)
                except (IndexError, Exception):
                    pass
        else:
            num_text = cq.Workplane("XY").center(
                pin_pos.num_x, pin_pos.num_y
            ).text(pin_number, num_size, num_height, halign=pin_pos.num_halign)
            num_assy.add(num_text, color=self.BLACK_COLOR)
        pin_assy.add(num_assy, name="text")

        # 4. boundingBox — invisible selection area covering the leg region
        #    Matches reference schematic.glb: spans the full leg length × 1.24 mm,
        #    centered at the midpoint of the leg (same X/Y as leg center).
        bbox_fixed_h = 1.24  # fixed height matching reference (mm)
        if pin_pos.side == "left":
            bbox_cx = pin_pos.x - leg_length / 2
            bbox_cy = pin_pos.y
            bbox_w, bbox_h = leg_length, bbox_fixed_h
        elif pin_pos.side == "right":
            bbox_cx = pin_pos.x + leg_length / 2
            bbox_cy = pin_pos.y
            bbox_w, bbox_h = leg_length, bbox_fixed_h
        elif pin_pos.side == "top":
            bbox_cx = pin_pos.x
            bbox_cy = pin_pos.y + leg_length / 2
            bbox_w, bbox_h = bbox_fixed_h, leg_length
        else:  # bottom
            bbox_cx = pin_pos.x
            bbox_cy = pin_pos.y - leg_length / 2
            bbox_w, bbox_h = bbox_fixed_h, leg_length
        bbox = cq.Workplane("XY").center(bbox_cx, bbox_cy).rect(bbox_w, bbox_h).extrude(0.01)
        bbox_assy = cq.Assembly(name="boundingBox")
        bbox_assy.add(bbox, color=cq.Color(1, 1, 1, 0))
        pin_assy.add(bbox_assy, name="boundingBox")

        # 5. pinName — pin function name label
        if pin_name:
            txt_size = self.params.pin_geometry.pin_name_size
            txt_height = self.params.pin_geometry.pin_name_height
            name_assy = cq.Assembly(name="pinName")
            if pin_pos.side in ["top", "bottom"]:
                direction = -1 if pin_pos.side == "top" else 1
                char_spacing = txt_size * 1.2
                for i, char in enumerate(pin_name[:30]):
                    if not char.strip():  # skip whitespace — CadQuery crashes on spaces
                        continue
                    char_y = pin_pos.text_y + (i * char_spacing * direction)
                    try:
                        char_wp = cq.Workplane("XY").center(
                            pin_pos.text_x, char_y
                        ).text(char, txt_size, txt_height, halign="center")
                        name_assy.add(char_wp, color=self.BLACK_COLOR)
                    except (IndexError, Exception):
                        pass  # skip characters that CadQuery can't render
            else:
                pin_name_text = cq.Workplane("XY").center(
                    pin_pos.text_x, pin_pos.text_y
                ).text(pin_name[:30], txt_size, txt_height, halign=pin_pos.text_halign)
                name_assy.add(pin_name_text, color=self.BLACK_COLOR)
            pin_assy.add(name_assy, name="pinName")

        return pin_assy

    def build_all_pins(
        self, pin_data: List[Dict[str, Any]]
    ) -> cq.Assembly:
        """
        Build all pins and organize into Legs assembly.

        Args:
            pin_data: List of pin dictionaries with 'pin_num', 'pin_name'

        Returns:
            Legs assembly containing all pins
        """
        legs_assy = cq.Assembly(name="Legs")

        # Create a mapping from pin number to position
        pin_number_to_position = {
            pos.pin_number: pos for pos in self.pin_positions
        }

        logger.info("Building %d pins" % len(pin_data))

        # Debug: print pin positions
        logger.debug("Pin positions:")
        for pin_num, pos in pin_number_to_position.items():
            logger.debug("  Pin %s: (%.1f, %.1f) %s" % (pin_num, pos.x, pos.y, pos.side))

        # Debug: print input pin data
        logger.debug("Input pin data:")
        for pin in pin_data:
            pin_num = str(pin.get("number", pin.get("pin_num", "")))
            pin_name = pin.get("name", pin.get("pin_name", ""))
            logger.debug("  Pin %s: %s" % (pin_num, pin_name))

        # Build each pin
        for pin in pin_data:
            pin_num = str(pin.get("number", pin.get("pin_num", "")))
            pin_name = pin.get("name", pin.get("pin_name", ""))

            # Get position from layout algorithm by pin number
            pin_pos = pin_number_to_position.get(pin_num)
            if pin_pos is None:
                logger.warning("No layout position for pin %s" % pin_num)
                continue

            logger.info("Building pin %s (%s) at (%.1f, %.1f) side=%s" % (pin_num, pin_name, pin_pos.x, pin_pos.y, pin_pos.side))

            # Build pin assembly (returns single assembly with nested children)
            pin_assy = self.build_pin(pin_pos, pin_name, pin_num)

            # Add pin assembly to Legs assembly
            legs_assy.add(pin_assy)

        return legs_assy

    def build_designator(self) -> cq.Assembly:
        """
        Build designator label ("U").

        Hierarchy:
        DesignatorName
        ├── Body [mesh]
        └── BoundingBox [mesh]

        Returns:
            Assembly with "U" text above body
        """
        size = self.params.body_geometry.designator_size
        height = self.params.body_geometry.designator_height
        offset = self.params.body_geometry.designator_offset
        text_y = self.params.body_height / 2 + offset

        designator_assy = cq.Assembly(name="DesignatorName")

        text_shape = cq.Workplane("XY").center(0, text_y).text(
            self.params.body_geometry.designator_name, size, height,
        )
        body_assy = cq.Assembly(name="Body")
        body_assy.add(text_shape, color=self.BLACK_COLOR)
        designator_assy.add(body_assy, name="Body")

        bbox = cq.Workplane("XY").center(0, text_y).rect(
            size * 2.0, size * 1.5
        ).extrude(0.001)
        bbox_assy = cq.Assembly(name="BoundingBox")
        bbox_assy.add(bbox, color=cq.Color(1, 1, 1, 0))
        designator_assy.add(bbox_assy, name="BoundingBox")

        return designator_assy

    def build_package_value(self) -> cq.Assembly:
        """
        Build package value label (component name).

        Hierarchy:
        PackageValue
        ├── Body [mesh]
        └── BoundingBox [mesh]

        Returns:
            Assembly with component name text above body
        """
        size = self.params.body_geometry.value_size
        height = self.params.body_geometry.value_height
        offset = self.params.body_geometry.value_offset
        name = self.component_name[:30]
        text_y = self.params.body_height / 2 + offset

        value_assy = cq.Assembly(name="PackageValue")

        text_shape = cq.Workplane("XY").center(0, text_y).text(name, size, height)
        body_assy = cq.Assembly(name="Body")
        body_assy.add(text_shape, color=self.BLACK_COLOR)
        value_assy.add(body_assy, name="Body")

        bbox_w = max(len(name) * size * 0.6, size * 2)
        bbox = cq.Workplane("XY").center(0, text_y).rect(bbox_w, size * 1.5).extrude(0.001)
        bbox_assy = cq.Assembly(name="BoundingBox")
        bbox_assy.add(bbox, color=cq.Color(1, 1, 1, 0))
        value_assy.add(bbox_assy, name="BoundingBox")

        return value_assy

    def build_schematic(self, pin_data: List[Dict[str, Any]]) -> cq.Assembly:
        """
        Build complete schematic symbol assembly.

        Args:
            pin_data: List of pin dictionaries with 'number', 'name'

        Returns:
            Complete Package assembly with all components
        """
        # Main package assembly
        package_assy = cq.Assembly(name="Package")

        # Order matches reference schematic.glb:
        # DesignatorName → PackageValue → BodyLine → Legs

        # 1. DesignatorName
        logger.info("Adding designator label...")
        designator = self.build_designator()
        package_assy.add(designator, name="DesignatorName")

        # 2. PackageValue
        logger.info("Adding package value label...")
        value = self.build_package_value()
        package_assy.add(value, name="PackageValue")

        # 3. BodyLine (single fused border mesh)
        logger.info("Building body border...")
        body_line = self.build_body_border()
        package_assy.add(body_line, name="BodyLine")

        # 4. Legs
        logger.info("Building pins...")
        legs = self.build_all_pins(pin_data)
        package_assy.add(legs, name="Legs")

        logger.info(
            "Schematic assembly built: %d top-level components" % len(package_assy.children)
        )

        return package_assy

    def save_glb(self, output_path: str, pin_data: List[Dict[str, Any]]) -> bool:
        """
        Build and export schematic to GLB file.

        Args:
            output_path: Path to save GLB file
            pin_data: List of pin dictionaries

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Building schematic for %s..." % output_path)

            # Build schematic assembly
            assembly = self.build_schematic(pin_data)

            # Save to GLB
            logger.info("Saving to %s..." % output_path)
            assembly.save(output_path)
            try:
                original_nodes, simplified_nodes = optimize_glb_hierarchy(output_path)
                logger.info(
                    "Optimized GLB hierarchy: %d -> %d nodes"
                    % (original_nodes, simplified_nodes)
                )
                _normalize_schematic_bodyline_name(output_path)
            except Exception as exc:
                logger.warning("Skipping GLB hierarchy optimization: %s" % exc)

            try:
                from src.core.schematic_extras import inject_schematic_extras

                pin_name_map = {
                    str(pin.get("number")): str(pin.get("name") or "")
                    for pin in pin_data
                }
                # Slice C: per-pin contract semantics for GLB extras (carried on
                # the pin dicts by the adapter's record enrichment).
                pin_semantics = {
                    str(pin.get("number")): {
                        "electrical_type": pin.get("electrical_type"),
                        "role": pin.get("role"),
                        "active_low": bool(pin.get("active_low")),
                        "nc": bool(pin.get("nc")),
                        "nc_instruction": pin.get("nc_instruction"),
                    }
                    for pin in pin_data
                }
                if not inject_schematic_extras(
                    output_path, pin_name_map, self.component_name,
                    pin_semantics=pin_semantics,
                ):
                    logger.warning("Schematic extras injection found no Package root")
            except Exception as exc:
                logger.warning("Skipping schematic extras injection: %s" % exc)

            logger.info("Successfully saved schematic to %s" % output_path)

            # Verify file exists
            if os.path.exists(output_path):
                size = os.path.getsize(output_path)
                logger.info("GLB file size: %d bytes" % size)
                return True
            else:
                logger.error("GLB file not created: %s" % output_path)
                return False

        except Exception as e:
            logger.error("Error saving GLB: %s" % e)
            import traceback
            traceback.print_exc()
            return False


def build_pinout_diagram(
    package_type: str,
    pin_count: int,
    component_name: str,
    pin_data: List[Dict[str, Any]],
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
) -> bool:
    """
    Build and export pinout diagram from pin data.

    Args:
        package_type: Package type (e.g., "DIP-8", "LQFP64")
        pin_count: Number of pins
        component_name: Component name
        pin_data: List of pin dictionaries with 'number', 'name'
        output_path: Path to save GLB file
        custom_layout: Optional dict mapping side names to pin numbers
                     (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})

    Returns:
        True if successful, False otherwise
    """
    builder = PinoutDiagramBuilder(package_type, pin_count, component_name, custom_layout, pin_data=pin_data)
    return builder.save_glb(output_path, pin_data)
