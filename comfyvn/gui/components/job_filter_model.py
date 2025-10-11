# comfyvn/gui/components/job_filter_model.py
# 🔍 Job Filter Model — v1.0 (Phase 3.4-E)
# Provides dynamic filtering & sorting for TaskManagerDock job table
# [🎨 GUI Code Production Chat]

from PySide6.QtCore import QSortFilterProxyModel, Qt, QModelIndex


class JobFilterModel(QSortFilterProxyModel):
    """
    Acts as a smart filter layer for job tables.
    Supports CPU/GPU/Active/Failed filters from TaskManagerControls.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filters = {
            "cpu_only": False,
            "gpu_only": False,
            "active": False,
            "failed": False,
        }

    # ------------------------------------------------------------------
    def set_filters(self, filters: dict):
        """Update filters and refresh display."""
        changed = False
        for k, v in filters.items():
            if self.filters.get(k) != v:
                self.filters[k] = v
                changed = True
        if changed:
            self.invalidateFilter()

    # ------------------------------------------------------------------
    def filterAcceptsRow(self, source_row, source_parent: QModelIndex) -> bool:
        """Core filtering logic for jobs table."""
        model = self.sourceModel()
        if not model:
            return True

        idx_type = model.index(source_row, 1, source_parent)   # Type column
        idx_status = model.index(source_row, 2, source_parent) # Status column

        job_type = model.data(idx_type, Qt.DisplayRole) or ""
        job_status = (model.data(idx_status, Qt.DisplayRole) or "").lower()

        # --- Device filters ---
        if self.filters["cpu_only"] and "cpu" not in job_type.lower():
            return False
        if self.filters["gpu_only"] and "gpu" not in job_type.lower():
            return False

        # --- Status filters ---
        if self.filters["active"] and job_status not in ("running", "processing", "active"):
            return False
        if self.filters["failed"] and job_status not in ("failed", "error"):
            return False

        return True

    # ------------------------------------------------------------------
    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """Custom sorting rule — numeric if possible."""
        ldata = self.sourceModel().data(left, Qt.DisplayRole)
        rdata = self.sourceModel().data(right, Qt.DisplayRole)
        try:
            return float(ldata) < float(rdata)
        except Exception:
            return str(ldata) < str(rdata)
