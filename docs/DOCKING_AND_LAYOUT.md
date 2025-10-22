# Docking & Layout Guide

The docking system now assigns stable `objectName` values to every dock widget
and exposes a unified context menu so layouts persist reliably across sessions.

## Basics

- Drag any dockable panel by its title bar to reposition it. Drop onto the
  highlight zones (left, right, top, bottom) to anchor the dock in that area.
- Tabs appear automatically when you drop a dock onto an area that already
  contains panels. Use the tab strip to reorder panels within the same area.
- Use the close button in the title bar—or the **Close** entry in the
  context menu—to hide a panel without unregistering it from workspace saves.

## Right-Click Context Menu

Right-click the dock title bar to access:

- **Close** — hides the current dock.
- **Move to Dock Area → Left / Right / Top / Bottom** — relocates the dock and
  raises it immediately. The manager updates its internal registration so the
  move is reflected in subsequent `saveState()` calls.

These options are available on every dock shipped with ComfyVN Studio, including
panels that originate from extensions.

## Saving & Restoring Layouts

`WorkspaceManager` now ensures each `QDockWidget` has an `objectName` before
calling `QMainWindow.saveState()`. This removes the
`'objectName' not set for QDockWidget` warnings and keeps saved layouts stable
even when dock titles change.

- Use the workspace controller to save named layouts under
  `data/workspaces/<name>.json`.
- Layout saves include dock visibility, tab ordering, and floating states. When
  you restore a workspace the manager reapplies geometries after reassigning
  object names.

Tip: persist commonly used layouts per discipline (writing, art, QA) so switch
overs are instant during playtests.
