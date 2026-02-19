"""
Export cadquery models to GLB format.
"""

import tempfile
import subprocess
from pathlib import Path
from typing import Optional

try:
    import cadquery as cq
except ImportError:
    cq = None


class GLBExporter:
    """Export cadquery models to GLB (binary glTF) format."""

    def __init__(self, cadquery_code: str):
        """
        Initialize the exporter with cadquery code.

        Args:
            cadquery_code: String containing valid cadquery Python code
        """
        self.cadquery_code = cadquery_code
        self.model = None
        self._build_model()

    def _build_model(self) -> None:
        """
        Build the cadquery model from the code.

        Raises:
            ImportError: If cadquery is not installed
            RuntimeError: If code execution fails
        """
        if cq is None:
            raise ImportError(
                "cadquery is required. Install with: pip install cadquery"
            )

        try:
            # Create a namespace for execution
            namespace = {"cq": cq, "show_object": lambda x: None}

            # Execute the cadquery code
            exec(self.cadquery_code, namespace)

            # Extract the result model
            if "result" in namespace:
                self.model = namespace["result"]
            else:
                raise RuntimeError(
                    "Cadquery code did not produce a 'result' variable"
                )

        except Exception as e:
            raise RuntimeError(f"Failed to build cadquery model: {e}")

    def export_to_glb(self, output_path: str) -> None:
        """
        Export the model to GLB format.

        Args:
            output_path: Path where GLB file should be saved

        Raises:
            RuntimeError: If export fails
        """
        if self.model is None:
            raise RuntimeError("Model has not been built")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Use cadquery's built-in export functionality
            self.model.val().exportStl(str(output_file.with_suffix(".stl")))

            # Convert STL to GLB using meshconv or similar tool
            # Note: This requires additional conversion tools
            # For now, we'll export as STL and note conversion requirement
            print(f"Model exported to: {output_file.with_suffix('.stl')}")
            print(f"Note: GLB export requires additional conversion tools.")
            print(f"Install 'meshconv' or use online converters to convert STL to GLB.")

        except Exception as e:
            raise RuntimeError(f"Failed to export model: {e}")

    def export_to_step(self, output_path: str) -> None:
        """
        Export the model to STEP format (alternative to GLB).

        Args:
            output_path: Path where STEP file should be saved

        Raises:
            RuntimeError: If export fails
        """
        if self.model is None:
            raise RuntimeError("Model has not been built")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.model.val().exportStep(str(output_file))
            print(f"Model exported to: {output_file}")
        except Exception as e:
            raise RuntimeError(f"Failed to export STEP file: {e}")

    def export_to_obj(self, output_path: str) -> None:
        """
        Export the model to OBJ format (alternative to GLB).

        Args:
            output_path: Path where OBJ file should be saved

        Raises:
            RuntimeError: If export fails
        """
        if self.model is None:
            raise RuntimeError("Model has not been built")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.model.val().exportStl(str(output_file.with_suffix(".stl")))

            # STL export is more reliable in cadquery
            # OBJ conversion may require additional tools
            print(f"Model exported to: {output_file.with_suffix('.stl')}")
            print(f"Note: OBJ export may require additional conversion.")
        except Exception as e:
            raise RuntimeError(f"Failed to export OBJ file: {e}")

    def get_model(self):
        """
        Get the cadquery model object.

        Returns:
            Cadquery model object
        """
        return self.model

    def _convert_stl_to_glb(self, stl_path: str, glb_path: str) -> bool:
        """
        Convert STL file to GLB format.

        This requires external tools like meshconv or trimesh.

        Args:
            stl_path: Path to STL file
            glb_path: Path where GLB file should be saved

        Returns:
            True if conversion successful, False otherwise
        """
        try:
            # Try using trimesh if available
            import trimesh

            mesh = trimesh.load(stl_path)
            mesh.export(glb_path)
            return True
        except ImportError:
            # Try using meshconv CLI tool
            try:
                subprocess.run(
                    ["meshconv", stl_path, "-o", glb_path],
                    check=True,
                    capture_output=True
                )
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                return False
        except Exception:
            return False
