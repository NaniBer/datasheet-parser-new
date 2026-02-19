"""
Generate cadquery code from PinData for 3D component modeling.
"""

from typing import Optional, Tuple, List

from ..models.pin_data import PinData, PackageInfo


class CadqueryBuilder:
    """Build cadquery models from pin data."""

    def __init__(self, pin_data: PinData):
        """
        Initialize the builder with pin data.

        Args:
            pin_data: PinData object containing component information
        """
        self.pin_data = pin_data
        self.package = pin_data.package

    def generate_model_code(self) -> str:
        """
        Generate cadquery Python code for the component.

        Returns:
            String containing valid cadquery code
        """
        package_type = self.package.type.upper()

        # Dispatch to appropriate package type handler
        if package_type in ("DIP", "DIL"):
            return self._generate_dip_code()
        elif package_type in ("QFN", "VQFN", "UQFN"):
            return self._generate_qfn_code()
        elif package_type in ("SOIC", "SOP", "SSOP"):
            return self._generate_soic_code()
        elif package_type in ("TSSOP", "TQSOP"):
            return self._generate_tssop_code()
        else:
            # Default to generic rectangular package
            return self._generate_generic_code()

    def _generate_dip_code(self) -> str:
        """Generate cadquery code for DIP (Dual Inline Package)."""
        p = self.package
        pins = self.pin_data.pins

        # Calculate parameters
        pins_per_side = p.pin_count // 2
        if p.pitch:
            pin_pitch = p.pitch
        else:
            pin_pitch = 0.1 * (p.pin_count ** 0.5)  # Estimate: 0.1mm * sqrt(pin_count)

        # Body dimensions
        body_width = p.width * 0.8  # Body is slightly smaller than total width
        body_height = p.height * 0.9
        body_thickness = p.thickness if p.thickness else 2.0

        # Pin dimensions
        pin_length = 3.0
        pin_width = 0.5
        pin_thickness = 0.2

        code = f'''import cadquery as cq

# DIP Package: {p.pin_count}-pin {p.type}
# Component: {self.pin_data.component_name}

# Parameters
pin_count = {p.pin_count}
pins_per_side = {pins_per_side}
pin_pitch = {pin_pitch:.4f}
body_width = {body_width:.4f}
body_height = {body_height:.4f}
body_thickness = {body_thickness:.4f}
pin_length = {pin_length:.4f}
pin_width = {pin_width:.4f}
pin_thickness = {pin_thickness:.4f}

# Create component body
body = (cq.Workplane("XY")
       .box(body_width, body_height, body_thickness))

# Create pins
pins = []

# Left side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_length, pin_width, pin_thickness)
           .translate((-body_width/2 - pin_length/2, y_pos, -pin_thickness/2)))
    pins.append(pin)

# Right side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_length, pin_width, pin_thickness)
           .translate((body_width/2 + pin_length/2, y_pos, -pin_thickness/2)))
    pins.append(pin)

# Combine all parts
result = body
for pin in pins:
    result = result.union(pin)

# Add pin labels as metadata
pin_metadata = {{}}
'''

        # Add pin metadata
        for pin in pins:
            code += f'pin_metadata[{pin.number}] = "{pin.name}"\n'

        code += '''
# Export the model
show_object(result)
'''
        return code

    def _generate_qfn_code(self) -> str:
        """Generate cadquery code for QFN (Quad Flat No-leads) package."""
        p = self.package

        # Calculate parameters
        pins_per_side = p.pin_count // 4
        if p.pitch:
            pin_pitch = p.pitch
        else:
            pin_pitch = 0.05 * (p.pin_count ** 0.5)

        # Body dimensions
        body_thickness = p.thickness if p.thickness else 1.0

        code = f'''import cadquery as cq

# QFN Package: {p.pin_count}-pin {p.type}
# Component: {self.pin_data.component_name}

# Parameters
pin_count = {p.pin_count}
pins_per_side = {pins_per_side}
pin_pitch = {pin_pitch:.4f}
body_width = {p.width:.4f}
body_height = {p.height:.4f}
body_thickness = {body_thickness:.4f}
pin_width = {pin_pitch * 0.6:.4f}
pin_length = {pin_pitch * 0.6:.4f}

# Create component body
body = (cq.Workplane("XY")
       .box(body_width, body_height, body_thickness))

# Create bottom pins
pins = []

# Bottom side pins
for i in range(pins_per_side):
    x_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_width, pin_length, 0.3)
           .translate((x_pos, -body_height/2 - pin_length/2, -body_thickness/2 - 0.15)))
    pins.append(pin)

# Top side pins
for i in range(pins_per_side):
    x_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_width, pin_length, 0.3)
           .translate((x_pos, body_height/2 + pin_length/2, -body_thickness/2 - 0.15)))
    pins.append(pin)

# Left side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_length, pin_width, 0.3)
           .translate((-body_width/2 - pin_length/2, y_pos, -body_thickness/2 - 0.15)))
    pins.append(pin)

# Right side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_length, pin_width, 0.3)
           .translate((body_width/2 + pin_length/2, y_pos, -body_thickness/2 - 0.15)))
    pins.append(pin)

# Combine all parts
result = body
for pin in pins:
    result = result.union(pin)

# Add center thermal pad
if pin_count > 16:
    thermal_pad = (cq.Workplane("XY")
                   .box(body_width * 0.6, body_height * 0.6, 0.3)
                   .translate((0, 0, -body_thickness/2 - 0.15)))
    result = result.union(thermal_pad)

# Add pin labels as metadata
pin_metadata = {{}}
'''

        # Add pin metadata
        for pin in self.pin_data.pins:
            code += f'pin_metadata[{pin.number}] = "{pin.name}"\n'

        code += '''
# Export the model
show_object(result)
'''
        return code

    def _generate_soic_code(self) -> str:
        """Generate cadquery code for SOIC (Small Outline IC) package."""
        p = self.package
        pins = self.pin_data.pins

        # Calculate parameters
        pins_per_side = p.pin_count // 2
        if p.pitch:
            pin_pitch = p.pitch
        else:
            pin_pitch = 0.05  # Standard SOIC pitch is 1.27mm

        # Body dimensions
        body_width = p.width * 0.7
        body_height = p.height * 0.9
        body_thickness = p.thickness if p.thickness else 1.5

        code = f'''import cadquery as cq

# SOIC Package: {p.pin_count}-pin {p.type}
# Component: {self.pin_data.component_name}

# Parameters
pin_count = {p.pin_count}
pins_per_side = {pins_per_side}
pin_pitch = {pin_pitch:.4f}
body_width = {body_width:.4f}
body_height = {body_height:.4f}
body_thickness = {body_thickness:.4f}
pin_length = {pin_pitch * 3:.4f}
pin_width = {pin_pitch * 0.6:.4f}
pin_thickness = 0.2

# Create component body
body = (cq.Workplane("XY")
       .box(body_width, body_height, body_thickness))

# Create gull-wing pins
pins = []

# Left side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    # Gull-wing shape: vertical down, bend out, horizontal
    pin = (cq.Workplane("XY")
           .box(pin_thickness, pin_width, pin_length)
           .translate((-body_width/2 - pin_thickness/2, y_pos, -pin_length/2 + pin_thickness/2)))
    pins.append(pin)

# Right side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_thickness, pin_width, pin_length)
           .translate((body_width/2 + pin_thickness/2, y_pos, -pin_length/2 + pin_thickness/2)))
    pins.append(pin)

# Combine all parts
result = body
for pin in pins:
    result = result.union(pin)

# Add pin labels as metadata
pin_metadata = {{}}
'''

        # Add pin metadata
        for pin in pins:
            code += f'pin_metadata[{pin.number}] = "{pin.name}"\n'

        code += '''
# Export the model
show_object(result)
'''
        return code

    def _generate_tssop_code(self) -> str:
        """Generate cadquery code for TSSOP (Thin Shrink Small Outline Package)."""
        p = self.package
        pins = self.pin_data.pins

        # Calculate parameters
        pins_per_side = p.pin_count // 2
        if p.pitch:
            pin_pitch = p.pitch
        else:
            pin_pitch = 0.03  # Standard TSSOP pitch is 0.65mm

        # Body dimensions
        body_width = p.width * 0.6
        body_height = p.height * 0.9
        body_thickness = p.thickness if p.thickness else 1.0

        code = f'''import cadquery as cq

# TSSOP Package: {p.pin_count}-pin {p.type}
# Component: {self.pin_data.component_name}

# Parameters
pin_count = {p.pin_count}
pins_per_side = {pins_per_side}
pin_pitch = {pin_pitch:.4f}
body_width = {body_width:.4f}
body_height = {body_height:.4f}
body_thickness = {body_thickness:.4f}
pin_length = {pin_pitch * 4:.4f}
pin_width = {pin_pitch * 0.5:.4f}
pin_thickness = 0.15

# Create component body
body = (cq.Workplane("XY")
       .box(body_width, body_height, body_thickness))

# Create gull-wing pins
pins = []

# Left side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_thickness, pin_width, pin_length)
           .translate((-body_width/2 - pin_thickness/2, y_pos, -pin_length/2 + pin_thickness/2)))
    pins.append(pin)

# Right side pins
for i in range(pins_per_side):
    y_pos = -(pins_per_side - 1) * pin_pitch / 2 + i * pin_pitch
    pin = (cq.Workplane("XY")
           .box(pin_thickness, pin_width, pin_length)
           .translate((body_width/2 + pin_thickness/2, y_pos, -pin_length/2 + pin_thickness/2)))
    pins.append(pin)

# Combine all parts
result = body
for pin in pins:
    result = result.union(pin)

# Add pin labels as metadata
pin_metadata = {{}}
'''

        # Add pin metadata
        for pin in pins:
            code += f'pin_metadata[{pin.number}] = "{pin.name}"\n'

        code += '''
# Export the model
show_object(result)
'''
        return code

    def _generate_generic_code(self) -> str:
        """Generate generic cadquery code for unknown package types."""
        p = self.package
        pins = self.pin_data.pins

        # Calculate parameters
        body_thickness = p.thickness if p.thickness else 2.0

        code = f'''import cadquery as cq

# Generic Package: {p.pin_count}-pin {p.type}
# Component: {self.pin_data.component_name}

# Parameters
pin_count = {p.pin_count}
body_width = {p.width:.4f}
body_height = {p.height:.4f}
body_thickness = {body_thickness:.4f}

# Create component body
body = (cq.Workplane("XY")
       .box(body_width, body_height, body_thickness))

# Create pins (simplified rectangular pins)
pins = []
pins_per_side = max(2, pin_count // 4)  # Distribute around edges

# Bottom edge pins
for i in range(pins_per_side):
    x_pos = -body_width/2 + (i + 0.5) * (body_width / (pins_per_side + 1))
    pin = (cq.Workplane("XY")
           .box(0.5, 0.5, 2.0)
           .translate((x_pos, -body_height/2 - 1.0, -1.0)))
    pins.append(pin)

# Combine all parts
result = body
for pin in pins:
    result = result.union(pin)

# Add pin labels as metadata
pin_metadata = {{}}
'''

        # Add pin metadata
        for pin in pins:
            code += f'pin_metadata[{pin.number}] = "{pin.name}"\n'

        code += '''
# Export the model
show_object(result)
'''
        return code

    def get_pin_positions(self) -> List[Tuple[float, float, float]]:
        """
        Calculate 3D positions for all pins.

        Returns:
            List of (x, y, z) tuples for each pin
        """
        # This would be expanded to return actual positions based on package type
        # For now, return placeholder positions
        positions = []
        for i, pin in enumerate(self.pin_data.pins):
            x = (i % 4) * 1.0 - 1.5
            y = (i // 4) * 1.0 - 1.5
            z = -1.0
            positions.append((x, y, z))
        return positions
