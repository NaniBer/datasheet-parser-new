# GLB Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI tool at `src/core/glb_reader.py` that prints a human-readable indented tree of a GLB file's node hierarchy.

**Architecture:** A private `_format_tree(gltf, filename)` function holds all tree-building logic and is tested directly against in-memory `GLTF2` objects. The public `read_glb(path)` function loads the file and delegates to it. A `__main__` block wires up the CLI.

**Tech Stack:** Python 3.9+, pygltflib (already in pyproject.toml `[glb]` extras)

## Global Constraints

- Python 3.9+ (project uses `datasheet/` venv at Python 3.9)
- `pygltflib` is the only dependency — no new packages
- Output goes to stdout; errors/usage to stderr
- Indentation is exactly 2 spaces per depth level
- Node fields printed as: `{name} [children:{n}, mesh:{yes|no}]`
- Unnamed nodes printed as `[unnamed]`

---

### Task 1: Core formatting logic + tests

**Files:**
- Create: `src/core/glb_reader.py`
- Create: `tests/test_glb_reader.py`

**Interfaces:**
- Produces:
  - `_format_tree(gltf: GLTF2, filename: str) -> str` — builds the full output string from an in-memory GLTF2 object
  - `read_glb(path: str) -> str` — loads a GLB file from disk and returns `_format_tree` output

- [ ] **Step 1: Write the failing tests**

Create `tests/test_glb_reader.py`:

```python
"""Tests for GLB file reader."""

import pytest
from pygltflib import GLTF2, Mesh, Node, Scene

from src.core.glb_reader import _format_tree


def test_header_line():
    gltf = GLTF2(
        nodes=[Node(name="Package", children=[1, 2]), Node(name="Legs", children=[]), Node(name="Body", children=[], mesh=0)],
        scenes=[Scene(nodes=[0])],
        meshes=[Mesh()],
    )
    result = _format_tree(gltf, "test.glb")
    first_line = result.splitlines()[0]
    assert first_line == "test.glb  [nodes:3, meshes:1, scenes:1]"


def test_indented_tree_structure():
    gltf = GLTF2(
        nodes=[
            Node(name="Package", children=[1, 2]),
            Node(name="Legs", children=[]),
            Node(name="Body", children=[], mesh=0),
        ],
        scenes=[Scene(nodes=[0])],
        meshes=[Mesh()],
    )
    result = _format_tree(gltf, "test.glb")
    lines = result.splitlines()
    assert "Package [children:2, mesh:no]" in lines
    assert "  Legs [children:0, mesh:no]" in lines
    assert "  Body [children:0, mesh:yes]" in lines


def test_unnamed_node_shown_as_unnamed():
    gltf = GLTF2(
        nodes=[Node(name=None, children=[])],
        scenes=[Scene(nodes=[0])],
        meshes=[],
    )
    result = _format_tree(gltf, "test.glb")
    assert "[unnamed] [children:0, mesh:no]" in result


def test_orphaned_nodes_section():
    gltf = GLTF2(
        nodes=[
            Node(name="Root", children=[]),
            Node(name="Orphan", children=[]),
        ],
        scenes=[Scene(nodes=[0])],  # node 1 not reachable
        meshes=[],
    )
    result = _format_tree(gltf, "test.glb")
    assert "[orphaned nodes]" in result
    assert "Orphan" in result


def test_multiple_scenes_labelled():
    gltf = GLTF2(
        nodes=[
            Node(name="SceneARoot", children=[]),
            Node(name="SceneBRoot", children=[]),
        ],
        scenes=[Scene(nodes=[0]), Scene(nodes=[1])],
        meshes=[],
    )
    result = _format_tree(gltf, "test.glb")
    assert "[scene 1]" in result
    assert "SceneARoot" in result
    assert "SceneBRoot" in result


def test_no_scenes_prints_warning_and_all_nodes():
    gltf = GLTF2(
        nodes=[Node(name="Floating", children=[])],
        scenes=[],
        meshes=[],
    )
    result = _format_tree(gltf, "test.glb")
    assert "[warning: no scenes found]" in result
    assert "Floating" in result
```

- [ ] **Step 2: Run tests — verify they all fail**

```bash
cd /Users/mac/Documents/Projects/datasheet-parser-new && source datasheet/bin/activate && pytest tests/test_glb_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.core.glb_reader'`

- [ ] **Step 3: Implement `src/core/glb_reader.py`**

Create `src/core/glb_reader.py`:

```python
"""GLB file reader — prints a human-readable node hierarchy tree."""

import os
import sys

from pygltflib import GLTF2


def read_glb(path: str) -> str:
    gltf = GLTF2().load(path)
    return _format_tree(gltf, os.path.basename(path))


def _format_tree(gltf: GLTF2, filename: str) -> str:
    total_nodes = len(gltf.nodes) if gltf.nodes else 0
    total_meshes = len(gltf.meshes) if gltf.meshes else 0
    total_scenes = len(gltf.scenes) if gltf.scenes else 0

    lines = [
        f"{filename}  [nodes:{total_nodes}, meshes:{total_meshes}, scenes:{total_scenes}]",
        "",
    ]

    visited: set = set()

    if not gltf.scenes:
        lines.append("[warning: no scenes found]")
        for i in range(total_nodes):
            lines.append(_fmt(gltf.nodes[i], depth=0))
            visited.add(i)
    else:
        for scene_idx, scene in enumerate(gltf.scenes):
            if scene_idx > 0:
                lines.append("")
                lines.append(f"[scene {scene_idx}]")
            for root_idx in (scene.nodes or []):
                _walk(gltf, root_idx, 0, lines, visited)

    orphans = set(range(total_nodes)) - visited
    if orphans:
        lines.append("")
        lines.append("[orphaned nodes]")
        for i in sorted(orphans):
            lines.append(_fmt(gltf.nodes[i], depth=1))

    return "\n".join(lines)


def _walk(gltf: GLTF2, node_idx: int, depth: int, lines: list, visited: set) -> None:
    visited.add(node_idx)
    node = gltf.nodes[node_idx]
    lines.append(_fmt(node, depth))
    for child_idx in (node.children or []):
        _walk(gltf, child_idx, depth + 1, lines, visited)


def _fmt(node, depth: int) -> str:
    name = node.name if node.name else "[unnamed]"
    children = len(node.children or [])
    has_mesh = "yes" if node.mesh is not None else "no"
    return f"{'  ' * depth}{name} [children:{children}, mesh:{has_mesh}]"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/core/glb_reader.py <file.glb>", file=sys.stderr)
        sys.exit(1)
    print(read_glb(sys.argv[1]))
```

- [ ] **Step 4: Run tests — verify they all pass**

```bash
cd /Users/mac/Documents/Projects/datasheet-parser-new && source datasheet/bin/activate && pytest tests/test_glb_reader.py -v
```

Expected: 6 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/core/glb_reader.py tests/test_glb_reader.py
git commit -m "feat: add GLB reader CLI tool"
```

---

### Task 2: Smoke test against real GLB files

**Files:**
- No new files — manual verification only

**Interfaces:**
- Consumes: `read_glb(path: str) -> str` from Task 1

- [ ] **Step 1: Run against schematic.glb**

```bash
cd /Users/mac/Documents/Projects/datasheet-parser-new && source datasheet/bin/activate && python src/core/glb_reader.py schematic.glb
```

Expected: header line followed by indented node tree. Verify:
- First line matches `schematic.glb  [nodes:N, meshes:M, scenes:1]`
- `Package` appears as a root node
- Child nodes like `DesignatorName`, `Legs`, `Body` appear indented under it
- No Python tracebacks

- [ ] **Step 2: Run against 2d.glb**

```bash
cd /Users/mac/Documents/Projects/datasheet-parser-new && source datasheet/bin/activate && python src/core/glb_reader.py 2d.glb
```

Expected: similar tree output for the PCB footprint structure. Verify:
- Header shows a different node/mesh count from schematic.glb
- No Python tracebacks

- [ ] **Step 3: Verify bad path exits with usage message**

```bash
cd /Users/mac/Documents/Projects/datasheet-parser-new && source datasheet/bin/activate && python src/core/glb_reader.py 2>&1
```

Expected: `Usage: python src/core/glb_reader.py <file.glb>` printed to stderr, exit code 1

- [ ] **Step 4: Commit smoke test confirmation**

```bash
git commit --allow-empty -m "chore: confirm glb_reader smoke tests pass against schematic.glb and 2d.glb"
```
