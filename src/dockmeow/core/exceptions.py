"""DockMeow exception hierarchy.

Every user-facing error carries:
- ``technical``:    Full technical description (logged to file, not shown in UI).
- ``user_message``: Short Chinese string shown in QMessageBox.
- ``suggestion``:   Actionable next step shown below the error.
"""


class DockMeowError(Exception):
    """Base class for all DockMeow application errors."""

    def __init__(self, technical: str, user_message: str, suggestion: str = "") -> None:
        super().__init__(technical)
        self.user_message = user_message
        self.suggestion = suggestion


class ReceptorPreparationError(DockMeowError):
    """Raised when receptor PDB preparation fails."""


class LigandPreparationError(DockMeowError):
    """Raised when ligand PDBQT preparation fails."""


class PocketDetectionError(DockMeowError):
    """Raised when pocket detection returns no usable result."""


class DockingExecutionError(DockMeowError):
    """Raised when AutoDock Vina docking fails or is interrupted."""


class LicenseError(DockMeowError):
    """Raised for any licensing validation failure (signature, machine, expiry)."""


class TimeAnomalyError(DockMeowError):
    """Raised when a system clock rollback is detected."""
