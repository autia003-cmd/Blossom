import sys
import os
import json
import re
import ctypes
from ctypes import wintypes
import logging
from pathlib import Path
from datetime import datetime

import pymem
import requests
from PyQt6 import QtWidgets, QtCore, QtGui


# ============================================================
# Paths
# ============================================================

LOCAL_APP_DATA = os.getenv("LOCALAPPDATA")

if not LOCAL_APP_DATA:
    raise RuntimeError("LOCALAPPDATA is not available.")

DATA_PATH = Path(LOCAL_APP_DATA) / "Blossom"
DATA_PATH.mkdir(parents=True, exist_ok=True)

FFS_FILE = DATA_PATH / "ffs.json"
SETTINGS_FILE = DATA_PATH / "settings.json"
LOG_FILE = DATA_PATH / "blossom.log"

OFFSETS_URL = (
    "https://raw.githubusercontent.com/rxyz4/FastFlags/"
    "refs/heads/main/Offsets.h"
)


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("Blossom")


# ============================================================
# Windows memory API
# ============================================================

ntdll = ctypes.WinDLL("ntdll", use_last_error=True)


class IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [
        ("Status", ctypes.c_int),
        ("Information", ctypes.c_void_p),
    ]


NtWriteVirtualMemory = ntdll.NtWriteVirtualMemory
NtWriteVirtualMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(IO_STATUS_BLOCK),
]
NtWriteVirtualMemory.restype = ctypes.c_long


# ============================================================
# Defaults
# ============================================================

DEFAULT_SETTINGS = {
    "auto_apply": False,
    "window_width": 760,
    "window_height": 820,
    "confirm_remove": True,
    "confirm_apply": False,
}


# ============================================================
# Styling
# ============================================================

STYLE = """
* {
    font-family: "Segoe UI", Arial, sans-serif;
}

QWidget#MainContainer {
    background: #fff8fa;
    border: 1px solid #efdfe3;
    border-radius: 16px;
}

QWidget#Card {
    background: #ffffff;
    border: 1px solid #f0e1e5;
    border-radius: 12px;
}

QLabel {
    color: #4b373b;
}

QLabel#Title {
    color: #c86f82;
    font-size: 15px;
    font-weight: 700;
}

QLabel#Subtitle {
    color: #9b7b81;
    font-size: 11px;
}

QLabel#SectionTitle {
    color: #60464c;
    font-size: 13px;
    font-weight: 700;
}

QLineEdit,
QComboBox,
QSpinBox {
    background: #ffffff;
    border: 1px solid #eadce0;
    border-radius: 8px;
    color: #3d2c30;
    padding: 8px 10px;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus {
    border: 1px solid #df9aaa;
}

QPushButton {
    background: #f7eaee;
    border: 1px solid #edd5db;
    border-radius: 8px;
    color: #533d42;
    font-weight: 600;
    padding: 8px 14px;
}

QPushButton:hover {
    background: #f1dce2;
    border-color: #e2b8c2;
}

QPushButton:pressed {
    background: #e8cbd2;
}

QPushButton#PrimaryButton {
    background: #df91a3;
    color: white;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background: #d67d91;
}

QPushButton#DangerButton {
    background: #f8e8e8;
    color: #ae5149;
    border-color: #efcece;
}

QPushButton#DangerButton:hover {
    background: #f3dada;
}

QTableWidget {
    background: white;
    border: 1px solid #eadde1;
    border-radius: 9px;
    color: #3d2c30;
    gridline-color: #f7ecef;
    outline: none;
    selection-background-color: #f5e2e7;
    selection-color: #7f4a55;
}

QTableWidget::item {
    padding: 6px;
}

QHeaderView::section {
    background: #fcf1f3;
    color: #80666c;
    border: none;
    padding: 9px 10px;
    font-size: 11px;
    font-weight: 700;
}

QCheckBox {
    color: #60484e;
}

QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid #dfc4ca;
    background: white;
}

QCheckBox::indicator:checked {
    background: #df91a3;
    border-color: #df91a3;
}

QProgressBar {
    background: #f6e9ed;
    border: none;
    border-radius: 4px;
    height: 7px;
}

QProgressBar::chunk {
    background: #df91a3;
    border-radius: 4px;
}

QPlainTextEdit {
    background: white;
    border: 1px solid #eadde1;
    border-radius: 9px;
    color: #3d2c30;
    font-family: Consolas, monospace;
    font-size: 12px;
    padding: 8px;
}

QStatusBar {
    background: #fcf1f3;
    color: #80666c;
}

QScrollBar:vertical {
    background: #fff8fa;
    width: 8px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #e8c9d1;
    border-radius: 4px;
    min-height: 25px;
}

QScrollBar::handle:vertical:hover {
    background: #dcaeba;
}
"""


# ============================================================
# Helpers
# ============================================================

def load_json(path: Path, default, expected_type=None):
    """Load JSON safely and return a deep-ish copy of the default on failure."""
    try:
        if not path.exists():
            return default.copy() if isinstance(default, dict) else default

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if expected_type is not None and not isinstance(data, expected_type):
            logger.warning(
                "Ignoring %s because it contains %s instead of %s.",
                path,
                type(data).__name__,
                expected_type.__name__,
            )
            return default.copy() if isinstance(default, dict) else default

        return data

    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.exception("Failed loading %s: %s", path, exc)
        return default.copy() if isinstance(default, dict) else default


def save_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        temporary.replace(path)

    except Exception:
        logger.exception("Failed saving %s", path)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ============================================================
# Flag utilities
# ============================================================

class FlagUtils:
    PREFIXES = (
        "DFFlag",
        "DFInt",
        "DFString",
        "FFlag",
        "FInt",
        "FString",
        "FLog",
    )

    TYPE_BY_PREFIX = {
        "DFFlag": "bool",
        "FFlag": "bool",
        "DFInt": "int",
        "FInt": "int",
        "DFString": "string",
        "FString": "string",
        "FLog": "string",
    }

    @classmethod
    def split_prefix(cls, name: str):
        name = str(name).strip()
        for prefix in cls.PREFIXES:
            if name.startswith(prefix):
                return name[len(prefix):], cls.TYPE_BY_PREFIX[prefix]
        return name, None

    @classmethod
    def clean_prefix(cls, name: str) -> str:
        return cls.split_prefix(name)[0]

    @classmethod
    def flag_type(cls, name: str):
        return cls.split_prefix(name)[1]

    @classmethod
    def parse_value(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value

        text = str(value).strip()
        lower = text.lower()

        if lower == "true":
            return True
        if lower == "false":
            return False

        try:
            return int(text, 10)
        except ValueError:
            return text

    @classmethod
    def validate(cls, name, value):
        raw_name = str(name).strip()
        if not raw_name:
            return False, "Flag name cannot be empty."

        clean_name = cls.clean_prefix(raw_name)
        if not clean_name:
            return False, "Flag name cannot consist only of a prefix."

        parsed = cls.parse_value(value)
        if isinstance(parsed, str) and len(parsed) > 4096:
            return False, "Value is too long (maximum 4096 characters)."

        return True, ""


# ============================================================
# Offset manager
# ============================================================

class OffsetManager(QtCore.QObject):
    loaded = QtCore.pyqtSignal(int)
    failed = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.offsets = {}
        self.types = {}

    @staticmethod
    def clean_name(name):
        return FlagUtils.clean_prefix(name)

    def fetch(self):
        try:
            response = requests.get(
                OFFSETS_URL,
                timeout=10,
                headers={"User-Agent": "Blossom/2.1"},
            )
            response.raise_for_status()

            raw = response.text
            matches = re.findall(
                r"(?:inline\s+constexpr\s+)?(?:uintptr_t|std::uintptr_t|uint64_t|size_t)\s+"
                r"(\w+)\s*=\s*(0x[0-9A-Fa-f]+)\s*;?",
                raw,
            )

            if not matches:
                matches = re.findall(
                    r"(?:inline\s+)?(?:constexpr\s+)?(?:uintptr_t|uint64_t|size_t)\s+"
                    r"(\w+)\s*=\s*(0x[0-9A-Fa-f]+)\s*;",
                    raw,
                )

            offsets = {}
            types = {}
            collisions = []

            for raw_name, value in matches:
                clean_name, flag_type = FlagUtils.split_prefix(raw_name)
                if not clean_name:
                    continue

                if clean_name in offsets and offsets[clean_name] != int(value, 16):
                    collisions.append(clean_name)
                    continue

                offsets[clean_name] = int(value, 16)
                if flag_type:
                    types[clean_name] = flag_type

            if not offsets:
                raise ValueError("No valid offsets were found in Offsets.h.")

            self.offsets = offsets
            self.types = types

            if collisions:
                logger.warning("Ignored %d normalized offset collision(s).", len(collisions))

            logger.info("Loaded %d offsets.", len(self.offsets))
            self.loaded.emit(len(self.offsets))

        except Exception as exc:
            logger.exception("Offset download failed.")
            self.failed.emit(str(exc))


class OffsetWorker(QtCore.QThread):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def run(self):
        self.manager.fetch()


# ============================================================
# Add/Edit flag dialog
# ============================================================

class AddFlagDialog(QtWidgets.QDialog):

    def __init__(
        self,
        parent=None,
        existing_name=None,
        existing_value=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("FFlag Editor")
        self.setModal(True)
        self.resize(500, 340)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QtWidgets.QLabel(
            "🌸 Edit FFlag"
            if existing_name
            else "🌸 Add FFlag"
        )
        title.setObjectName("Title")

        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Enter the flag name and value. Prefixes such as "
            "FFlag and DFInt are normalized automatically."
        )

        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(subtitle)

        layout.addWidget(
            QtWidgets.QLabel("Flag name")
        )

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText(
            "Example: DFIntTaskSchedulerTargetFps"
        )

        if existing_name:
            self.name_edit.setText(
                existing_name
            )

        layout.addWidget(self.name_edit)

        layout.addWidget(
            QtWidgets.QLabel("Value")
        )

        self.value_edit = QtWidgets.QLineEdit()
        self.value_edit.setPlaceholderText(
            "Example: 240"
        )

        if existing_value is not None:
            self.value_edit.setText(
                str(existing_value)
            )

        layout.addWidget(self.value_edit)

        layout.addStretch()

        buttons = QtWidgets.QHBoxLayout()

        cancel = QtWidgets.QPushButton(
            "Cancel"
        )

        save = QtWidgets.QPushButton(
            "Save"
        )

        save.setObjectName(
            "PrimaryButton"
        )

        cancel.clicked.connect(
            self.reject
        )

        save.clicked.connect(
            self._accept
        )

        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout.addLayout(buttons)

    def _accept(self):
        name = self.name_edit.text().strip()
        value = self.value_edit.text().strip()

        valid, error = FlagUtils.validate(
            name,
            value,
        )

        if not valid:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid flag",
                error,
            )
            return

        self.accept()

    def values(self):
        return (
            FlagUtils.clean_prefix(
                self.name_edit.text()
            ),
            self.value_edit.text().strip(),
        )


# ============================================================
# Main window
# ============================================================

class BlossomApp(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Blossom — Voidstrap FFlag Manager"
        )

        self.setMinimumSize(
            700,
            700,
        )

        self.added_flags = load_json(
            FFS_FILE,
            {},
            dict,
        )

        self.settings = load_json(
            SETTINGS_FILE,
            DEFAULT_SETTINGS.copy(),
            dict,
        )

        for key, value in DEFAULT_SETTINGS.items():
            self.settings.setdefault(key, value)

        # Sanitize persisted settings so malformed JSON cannot crash startup.
        self.settings["auto_apply"] = bool(self.settings.get("auto_apply", False))
        self.settings["confirm_remove"] = bool(self.settings.get("confirm_remove", True))
        self.settings["confirm_apply"] = bool(self.settings.get("confirm_apply", False))
        for key, fallback in (("window_width", 760), ("window_height", 820)):
            try:
                value = int(self.settings.get(key, fallback))
            except (TypeError, ValueError):
                value = fallback
            self.settings[key] = max(700 if key == "window_width" else 700, value)

        # Normalize persisted flag values to strings for consistent UI behavior.
        self.added_flags = {
            str(k): str(v)
            for k, v in self.added_flags.items()
            if str(k).strip()
        }

        self.offset_manager = OffsetManager()
        self.offset_worker = None

        self.pm = None
        self.is_connected = False
        self.last_apply_time = None

        self._build_ui()
        self._connect_signals()
        self._restore_window()

        self.refresh_table()
        self._start_monitor()

        QtCore.QTimer.singleShot(
            300,
            self.fetch_offsets,
        )

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet(STYLE)

        container = QtWidgets.QWidget()
        container.setObjectName(
            "MainContainer"
        )

        self.setCentralWidget(
            container
        )

        root = QtWidgets.QVBoxLayout(
            container
        )

        root.setContentsMargins(
            1,
            1,
            1,
            1,
        )

        root.setSpacing(0)

        # Header
        header = QtWidgets.QWidget()
        header.setFixedHeight(58)

        header_layout = QtWidgets.QHBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            20,
            0,
            14,
            0,
        )

        title = QtWidgets.QLabel(
            "🌸 Blossom"
        )

        title.setObjectName(
            "Title"
        )

        subtitle = QtWidgets.QLabel(
            "Voidstrap FFlag Manager"
        )

        subtitle.setObjectName(
            "Subtitle"
        )

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(0)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header_layout.addLayout(
            title_box
        )

        header_layout.addStretch()

        self.connection_lbl = QtWidgets.QLabel(
            "● Disconnected"
        )

        self.connection_lbl.setStyleSheet(
            "color: #b97979; "
            "font-weight: 600;"
        )

        header_layout.addWidget(
            self.connection_lbl
        )

        root.addWidget(
            header
        )

        # Main content
        content = QtWidgets.QWidget()

        content_layout = QtWidgets.QVBoxLayout(
            content
        )

        content_layout.setContentsMargins(
            22,
            8,
            22,
            16,
        )

        content_layout.setSpacing(
            10
        )

        root.addWidget(
            content
        )

        # Status card
        status_card = QtWidgets.QWidget()
        status_card.setObjectName(
            "Card"
        )

        status_layout = QtWidgets.QHBoxLayout(
            status_card
        )

        status_layout.setContentsMargins(
            14,
            10,
            14,
            10,
        )

        self.status_lbl = QtWidgets.QLabel(
            "🌙 Waiting for Voidstrap / Roblox..."
        )

        self.status_lbl.setObjectName(
            "SectionTitle"
        )

        self.offset_lbl = QtWidgets.QLabel(
            "Offsets: loading..."
        )

        self.offset_lbl.setObjectName(
            "Subtitle"
        )

        status_layout.addWidget(
            self.status_lbl
        )

        status_layout.addStretch()

        status_layout.addWidget(
            self.offset_lbl
        )

        content_layout.addWidget(
            status_card
        )

        # Search toolbar
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_bar = QtWidgets.QLineEdit()

        self.search_bar.setPlaceholderText(
            "🔍 Search FFlags..."
        )

        self.filter_combo = QtWidgets.QComboBox()

        self.filter_combo.addItems(
            [
                "All flags",
                "Boolean",
                "Integer",
                "String",
            ]
        )

        self.filter_combo.setFixedWidth(
            120
        )

        toolbar.addWidget(
            self.search_bar,
            1,
        )

        toolbar.addWidget(
            self.filter_combo
        )

        content_layout.addLayout(
            toolbar
        )

        # Table
        self.table = QtWidgets.QTableWidget(
            0,
            2,
        )

        self.table.setHorizontalHeaderLabels(
            [
                "Name",
                "Value",
            ]
        )

        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )

        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)

        self.table.verticalHeader().setVisible(
            False
        )

        table_header = (
            self.table.horizontalHeader()
        )

        table_header.setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )

        table_header.setSectionResizeMode(
            1,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )

        content_layout.addWidget(
            self.table,
            1,
        )

        # Statistics
        stats = QtWidgets.QHBoxLayout()

        self.count_lbl = QtWidgets.QLabel()
        self.selected_lbl = QtWidgets.QLabel(
            "0 selected"
        )

        self.count_lbl.setObjectName(
            "Subtitle"
        )

        self.selected_lbl.setObjectName(
            "Subtitle"
        )

        stats.addWidget(
            self.count_lbl
        )

        stats.addStretch()

        stats.addWidget(
            self.selected_lbl
        )

        content_layout.addLayout(
            stats
        )

        # Main action row
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(7)

        self.add_btn = QtWidgets.QPushButton(
            "＋ Add"
        )

        self.edit_btn = QtWidgets.QPushButton(
            "✎ Edit"
        )

        self.remove_btn = QtWidgets.QPushButton(
            "🗑 Remove"
        )

        self.import_btn = QtWidgets.QPushButton(
            "⇩ Import"
        )

        self.export_btn = QtWidgets.QPushButton(
            "⇧ Export"
        )

        self.add_btn.setObjectName(
            "PrimaryButton"
        )

        self.remove_btn.setObjectName(
            "DangerButton"
        )

        buttons.addWidget(
            self.add_btn
        )

        buttons.addWidget(
            self.edit_btn
        )

        buttons.addWidget(
            self.remove_btn
        )

        buttons.addStretch()

        buttons.addWidget(
            self.import_btn
        )

        buttons.addWidget(
            self.export_btn
        )

        content_layout.addLayout(
            buttons
        )

        # Bottom card
        bottom = QtWidgets.QWidget()
        bottom.setObjectName(
            "Card"
        )

        bottom_layout = QtWidgets.QHBoxLayout(
            bottom
        )

        bottom_layout.setContentsMargins(
            14,
            10,
            14,
            10,
        )

        self.auto_apply_cb = QtWidgets.QCheckBox(
            "Auto Apply"
        )

        self.auto_apply_cb.setChecked(
            bool(
                self.settings[
                    "auto_apply"
                ]
            )
        )

        self.refresh_offsets_btn = (
            QtWidgets.QPushButton(
                "↻ Refresh Offsets"
            )
        )

        self.open_data_btn = (
            QtWidgets.QPushButton(
                "📁 Data Folder"
            )
        )

        self.apply_btn = (
            QtWidgets.QPushButton(
                "✨ Apply All"
            )
        )

        self.apply_btn.setObjectName(
            "PrimaryButton"
        )

        self.apply_btn.setMinimumWidth(
            140
        )

        bottom_layout.addWidget(
            self.auto_apply_cb
        )

        bottom_layout.addWidget(
            self.refresh_offsets_btn
        )

        bottom_layout.addWidget(
            self.open_data_btn
        )

        bottom_layout.addStretch()

        bottom_layout.addWidget(
            self.apply_btn
        )

        content_layout.addWidget(
            bottom
        )

        # Menu
        menu = self.menuBar()

        file_menu = menu.addMenu(
            "File"
        )

        import_action = file_menu.addAction(
            "Import JSON"
        )

        export_action = file_menu.addAction(
            "Export JSON"
        )

        file_menu.addSeparator()

        exit_action = file_menu.addAction(
            "Exit"
        )

        tools_menu = menu.addMenu(
            "Tools"
        )

        validate_action = (
            tools_menu.addAction(
                "Validate Flags"
            )
        )

        normalize_action = (
            tools_menu.addAction(
                "Normalize Names"
            )
        )

        clear_action = (
            tools_menu.addAction(
                "Clear All Flags"
            )
        )

        help_menu = menu.addMenu(
            "Help"
        )

        about_action = (
            help_menu.addAction(
                "About"
            )
        )

        import_action.triggered.connect(
            self._import_file
        )

        export_action.triggered.connect(
            self._export_to_file
        )

        exit_action.triggered.connect(
            self.close
        )

        validate_action.triggered.connect(
            self._validate_flags
        )

        normalize_action.triggered.connect(
            self._normalize_flags
        )

        clear_action.triggered.connect(
            self._clear_all
        )

        about_action.triggered.connect(
            self._show_about
        )

        self.statusBar().showMessage(
            "Ready"
        )

    # --------------------------------------------------------
    # Connections
    # --------------------------------------------------------

    def _connect_signals(self):
        self.search_bar.textChanged.connect(
            self.refresh_table
        )

        self.filter_combo.currentIndexChanged.connect(
            self.refresh_table
        )

        self.table.itemSelectionChanged.connect(
            self._update_selection_count
        )

        self.add_btn.clicked.connect(
            self._show_add_dialog
        )

        self.edit_btn.clicked.connect(
            self._edit_selected
        )

        self.remove_btn.clicked.connect(
            self._remove_selected
        )

        self.import_btn.clicked.connect(
            self._import_file
        )

        self.export_btn.clicked.connect(
            self._export_to_file
        )

        self.apply_btn.clicked.connect(
            self._run_apply_all
        )

        self.auto_apply_cb.stateChanged.connect(
            self._toggle_auto_apply
        )

        self.refresh_offsets_btn.clicked.connect(
            self.fetch_offsets
        )

        self.open_data_btn.clicked.connect(
            self._open_data_folder
        )

        self.offset_manager.loaded.connect(
            self._offsets_loaded
        )

        self.offset_manager.failed.connect(
            self._offsets_failed
        )

    # --------------------------------------------------------
    # Process monitoring
    # --------------------------------------------------------

    def _start_monitor(self):
        self.monitor_timer = QtCore.QTimer(
            self
        )

        self.monitor_timer.setInterval(
            1500
        )

        self.monitor_timer.timeout.connect(
            self._check_process
        )

        self.monitor_timer.start()

        self._check_process()

    def _check_process(self):
        try:
            candidate = pymem.Pymem("RobloxPlayerBeta.exe")
            candidate_pid = candidate.process_id

            if self.is_connected and self.pm:
                if self.pm.process_id == candidate_pid:
                    # We already have the correct process handle.
                    try:
                        candidate.close_process()
                    except Exception:
                        pass
                    return

                try:
                    self.pm.close_process()
                except Exception:
                    pass

            self.pm = candidate
            self.is_connected = True
            logger.info("Roblox Player connected: PID %s", candidate_pid)
            self._set_connection(True)

            if self.settings.get("auto_apply", False):
                QtCore.QTimer.singleShot(250, self._run_apply_all)

        except pymem.exception.ProcessNotFound:
            if self.is_connected:
                logger.info("Roblox Player disconnected.")
            self._disconnect_process()

        except Exception as exc:
            logger.exception("Process monitoring error: %s", exc)
            self._disconnect_process()

    def _disconnect_process(self):
        if self.pm:
            try:
                self.pm.close_process()
            except Exception:
                pass
        self.pm = None
        if self.is_connected:
            self.is_connected = False
            self._set_connection(False)

    def _set_connection(
        self,
        connected,
    ):
        if connected:
            self.connection_lbl.setText(
                "● Connected"
            )

            self.connection_lbl.setStyleSheet(
                "color: #65ad86; "
                "font-weight: 600;"
            )

            self.status_lbl.setText(
                "🌸 Voidstrap / Roblox Player connected"
            )

        else:
            self.connection_lbl.setText(
                "● Disconnected"
            )

            self.connection_lbl.setStyleSheet(
                "color: #b97979; "
                "font-weight: 600;"
            )

            self.status_lbl.setText(
                "🌙 Waiting for Voidstrap / Roblox..."
            )

    # --------------------------------------------------------
    # Offsets
    # --------------------------------------------------------

    def fetch_offsets(self):
        if (
            self.offset_worker
            and self.offset_worker.isRunning()
        ):
            return

        self.offset_lbl.setText(
            "Offsets: downloading..."
        )

        self.refresh_offsets_btn.setEnabled(
            False
        )

        self.offset_worker = OffsetWorker(
            self.offset_manager
        )

        self.offset_worker.finished.connect(
            lambda: self.refresh_offsets_btn.setEnabled(
                True
            )
        )

        self.offset_worker.start()

    def _offsets_loaded(
        self,
        count,
    ):
        self.offset_lbl.setText(
            f"Offsets: {count:,} loaded"
        )

        self.refresh_offsets_btn.setEnabled(
            True
        )

        self.statusBar().showMessage(
            f"Loaded {count:,} offsets.",
            4000,
        )

    def _offsets_failed(
        self,
        error,
    ):
        self.offset_lbl.setText(
            "Offsets: failed"
        )

        self.refresh_offsets_btn.setEnabled(
            True
        )

        self.statusBar().showMessage(
            "Unable to download offsets.",
            5000,
        )

        logger.error(
            "Offset download failed: %s",
            error,
        )

    # --------------------------------------------------------
    # Table
    # --------------------------------------------------------

    def refresh_table(self):
        search = (
            self.search_bar.text()
            .casefold()
        )

        filter_type = (
            self.filter_combo.currentText()
        )

        rows = []

        for name, value in self.added_flags.items():
            if (
                search
                and search not in name.casefold()
            ):
                continue

            parsed = FlagUtils.parse_value(
                value
            )

            if filter_type == "Boolean":
                if not isinstance(
                    parsed,
                    bool,
                ):
                    continue

            elif filter_type == "Integer":
                if (
                    isinstance(
                        parsed,
                        bool,
                    )
                    or not isinstance(
                        parsed,
                        int,
                    )
                ):
                    continue

            elif filter_type == "String":
                if not isinstance(
                    parsed,
                    str,
                ):
                    continue

            rows.append(
                (
                    name,
                    str(value),
                )
            )

        self.table.setSortingEnabled(
            False
        )

        self.table.setRowCount(
            len(rows)
        )

        for row, (
            name,
            value,
        ) in enumerate(rows):

            self.table.setItem(
                row,
                0,
                QtWidgets.QTableWidgetItem(
                    name
                ),
            )

            self.table.setItem(
                row,
                1,
                QtWidgets.QTableWidgetItem(
                    value
                ),
            )

        self.table.setSortingEnabled(
            True
        )

        self.count_lbl.setText(
            f"{len(self.added_flags):,} flags"
        )

        self._update_selection_count()

    def _update_selection_count(self):
        rows = {
            item.row()
            for item in self.table.selectedItems()
        }

        self.selected_lbl.setText(
            f"{len(rows):,} selected"
        )

    # --------------------------------------------------------
    # Add / edit
    # --------------------------------------------------------

    def _show_add_dialog(self):
        dialog = AddFlagDialog(
            self
        )

        if (
            dialog.exec()
            != QtWidgets.QDialog.DialogCode.Accepted
        ):
            return

        name, value = (
            dialog.values()
        )

        self.added_flags[name] = value

        self._save()
        self.refresh_table()

        self.statusBar().showMessage(
            f"Added {name}.",
            3000,
        )

    def _edit_selected(self):
        selected = (
            self.table.selectedItems()
        )

        if not selected:
            return

        row = selected[0].row()

        name_item = self.table.item(
            row,
            0,
        )

        value_item = self.table.item(
            row,
            1,
        )

        if not name_item or not value_item:
            return

        name = name_item.text()
        value = value_item.text()

        dialog = AddFlagDialog(
            self,
            name,
            value,
        )

        if (
            dialog.exec()
            != QtWidgets.QDialog.DialogCode.Accepted
        ):
            return

        new_name, new_value = (
            dialog.values()
        )

        if new_name != name:
            self.added_flags.pop(
                name,
                None,
            )

        self.added_flags[
            new_name
        ] = new_value

        self._save()
        self.refresh_table()

        self.statusBar().showMessage(
            f"Updated {new_name}.",
            3000,
        )

    # --------------------------------------------------------
    # Remove
    # --------------------------------------------------------

    def _remove_selected(self):
        selected_rows = sorted(
            {
                item.row()
                for item in self.table.selectedItems()
            },
            reverse=True,
        )

        if not selected_rows:
            return

        names = []

        for row in selected_rows:
            item = self.table.item(
                row,
                0,
            )

            if item:
                names.append(
                    item.text()
                )

        if self.settings.get(
            "confirm_remove",
            True,
        ):
            answer = (
                QtWidgets.QMessageBox.question(
                    self,
                    "Remove flags",
                    f"Remove {len(names)} "
                    "selected flag(s)?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                )
            )

            if (
                answer
                != QtWidgets.QMessageBox.StandardButton.Yes
            ):
                return

        for name in names:
            self.added_flags.pop(
                name,
                None,
            )

        self._save()
        self.refresh_table()

        self.statusBar().showMessage(
            f"Removed {len(names)} flag(s).",
            3000,
        )

    # --------------------------------------------------------
    # Import / export
    # --------------------------------------------------------

    def _import_file(self):
        path, _ = (
            QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Import FFlags",
                "",
                "JSON Files (*.json)",
            )
        )

        if not path:
            return

        try:
            with open(
                path,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            if not isinstance(
                data,
                dict,
            ):
                raise ValueError(
                    "JSON root must be an object."
                )

            imported = 0

            for raw_name, value in data.items():
                name = (
                    FlagUtils.clean_prefix(
                        raw_name
                    )
                )

                valid, _ = (
                    FlagUtils.validate(
                        name,
                        value,
                    )
                )

                if not valid:
                    continue

                if name in self.added_flags and self.added_flags[name] != str(value):
                    logger.warning("Import collision for normalized flag %s; imported value replaces old value.", name)

                self.added_flags[name] = str(value)
                imported += 1

            self._save()
            self.refresh_table()

            self.statusBar().showMessage(
                f"Imported {imported} flag(s).",
                5000,
            )

        except Exception as exc:
            logger.exception(
                "Import failed."
            )

            QtWidgets.QMessageBox.critical(
                self,
                "Import failed",
                str(exc),
            )

    def _export_to_file(self):
        path, _ = (
            QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Export FFlags",
                "fflags.json",
                "JSON Files (*.json)",
            )
        )

        if not path:
            return

        try:
            with open(
                path,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    self.added_flags,
                    f,
                    indent=4,
                )

            self.statusBar().showMessage(
                f"Exported {len(self.added_flags):,} flags.",
                5000,
            )

        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Export failed",
                str(exc),
            )

    # --------------------------------------------------------
    # Utilities
    # --------------------------------------------------------

    def _validate_flags(self):
        invalid = []

        for name, value in (
            self.added_flags.items()
        ):
            valid, error = (
                FlagUtils.validate(
                    name,
                    value,
                )
            )

            if not valid:
                invalid.append(
                    f"{name}: {error}"
                )

        if invalid:
            QtWidgets.QMessageBox.warning(
                self,
                "Validation",
                "\n".join(
                    invalid[:30]
                ),
            )

        else:
            QtWidgets.QMessageBox.information(
                self,
                "Validation",
                f"All {len(self.added_flags):,} "
                "flags are valid.",
            )

    def _normalize_flags(self):
        normalized = {}
        collisions = []

        for name, value in self.added_flags.items():
            clean_name = FlagUtils.clean_prefix(name)
            if clean_name in normalized and normalized[clean_name] != value:
                collisions.append(clean_name)
                continue
            normalized[clean_name] = value

        self.added_flags = normalized
        self._save()
        self.refresh_table()

        if collisions:
            QtWidgets.QMessageBox.warning(
                self,
                "Name collisions",
                "These normalized names occurred more than once:\n\n"
                + "\n".join(collisions[:30]),
            )
        else:
            self.statusBar().showMessage("Flag names normalized.", 4000)

    def _clear_all(self):
        if not self.added_flags:
            return

        answer = (
            QtWidgets.QMessageBox.question(
                self,
                "Clear all",
                "Remove every saved flag?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            )
        )

        if (
            answer
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
            return

        self.added_flags.clear()

        self._save()
        self.refresh_table()

        self.statusBar().showMessage(
            "All flags removed.",
            4000,
        )

    def _open_data_folder(self):
        try:
            os.startfile(
                DATA_PATH
            )

        except Exception as exc:
            logger.exception(
                "Unable to open data directory."
            )

            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                str(exc),
            )

    def _show_about(self):
        QtWidgets.QMessageBox.about(
            self,
            "About Blossom",
            "Blossom\n\n"
            "Voidstrap FFlag Manager\n\n"
            "Data folder:\n"
            f"{DATA_PATH}",
        )

    # --------------------------------------------------------
    # Apply
    # --------------------------------------------------------

    def _run_apply_all(self):
        if not self.is_connected or not self.pm:
            QtWidgets.QMessageBox.warning(
                self,
                "Not connected",
                "Voidstrap / Roblox Player is not currently connected.",
            )
            return

        if not self.offset_manager.offsets:
            QtWidgets.QMessageBox.warning(
                self,
                "Offsets unavailable",
                "Offsets have not been loaded yet.",
            )
            return

        if not self.added_flags:
            return

        if self.settings.get("confirm_apply", False):
            answer = QtWidgets.QMessageBox.question(
                self,
                "Apply flags",
                f"Apply {len(self.added_flags):,} flag(s)?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return

        applied = 0
        failed = []

        for name, value in list(self.added_flags.items()):
            ok, reason = self._inject(name, value)
            if ok:
                applied += 1
            else:
                failed.append(f"{name}: {reason}")

        self.last_apply_time = datetime.now()
        logger.info("Apply completed: %d successful, %d failed.", applied, len(failed))

        if failed:
            logger.warning("Apply failures:\n%s", "\n".join(failed))
            preview = "\n".join(failed[:20])
            if len(failed) > 20:
                preview += f"\n... and {len(failed) - 20} more."
            QtWidgets.QMessageBox.warning(
                self,
                "Apply completed with errors",
                f"Applied: {applied:,}\nFailed: {len(failed):,}\n\n{preview}",
            )
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Apply complete",
                f"Successfully applied all {applied:,} flag(s).",
            )

        self.statusBar().showMessage(
            f"Applied: {applied:,} | Failed: {len(failed):,}",
            6000,
        )

    def _inject(self, name, value):
        if not self.pm:
            return False, "Process handle is unavailable."

        clean_name = FlagUtils.clean_prefix(name)
        if clean_name not in self.offset_manager.offsets:
            return False, "Flag offset was not found."

        try:
            offset = int(self.offset_manager.offsets[clean_name])
            if offset < 0:
                return False, "Offset is negative."

            address = self.pm.base_address + offset
            flag_type = self.offset_manager.types.get(clean_name) or FlagUtils.flag_type(name)
            parsed = FlagUtils.parse_value(value)

            # If the offset source identifies the flag type, enforce it.
            if flag_type == "bool":
                if not isinstance(parsed, bool):
                    return False, "Expected true or false."
                data = ctypes.c_uint32(1 if parsed else 0)

            elif flag_type == "int":
                if isinstance(parsed, bool) or not isinstance(parsed, int):
                    return False, "Expected an integer."
                if not -(2**31) <= parsed <= (2**31 - 1):
                    return False, "Integer is outside the signed 32-bit range."
                data = ctypes.c_int32(parsed)

            elif flag_type == "string":
                # String storage is implementation-specific. A raw byte write is only
                # correct when the supplied offset points at a writable char buffer.
                # Keep it explicit instead of silently converting strings to integers.
                encoded = str(value).encode("utf-8") + b"\x00"
                buffer = ctypes.create_string_buffer(encoded)
                return self._write_memory(address, ctypes.addressof(buffer), len(encoded), clean_name)

            else:
                # Unknown prefixes retain the old convenient behavior, but reject
                # arbitrary non-numeric strings rather than crashing.
                if isinstance(parsed, bool):
                    data = ctypes.c_int32(int(parsed))
                elif isinstance(parsed, int):
                    if not -(2**31) <= parsed <= (2**31 - 1):
                        return False, "Integer is outside the signed 32-bit range."
                    data = ctypes.c_int32(parsed)
                else:
                    return False, "Unsupported value type; expected bool or integer."

            return self._write_memory(
                address,
                ctypes.addressof(data),
                ctypes.sizeof(data),
                clean_name,
            )

        except (ValueError, TypeError, OverflowError, OSError) as exc:
            logger.exception("Failed applying %s", clean_name)
            return False, str(exc) or exc.__class__.__name__

    def _write_memory(self, address, source_address, size, flag_name):
        status_block = IO_STATUS_BLOCK()
        try:
            result = NtWriteVirtualMemory(
                self.pm.process_handle,
                address,
                ctypes.c_void_p(source_address),
                size,
                ctypes.byref(status_block),
            )
        except OSError as exc:
            logger.exception("Memory write failed for %s", flag_name)
            return False, str(exc)

        if result != 0:
            status = ctypes.c_uint32(result & 0xFFFFFFFF).value
            logger.error("NtWriteVirtualMemory failed for %s: NTSTATUS 0x%08X", flag_name, status)
            return False, f"NtWriteVirtualMemory failed (0x{status:08X})."

        return True, ""

    # --------------------------------------------------------
    # Settings
    # --------------------------------------------------------

    def _toggle_auto_apply(
        self,
        state,
    ):
        self.settings[
            "auto_apply"
        ] = (
            state
            == QtCore.Qt.CheckState.Checked.value
        )

        self._save()

    def _save(self):
        try:
            save_json(
                FFS_FILE,
                self.added_flags,
            )

            save_json(
                SETTINGS_FILE,
                self.settings,
            )

        except Exception as exc:
            logger.exception(
                "Failed saving data."
            )

            self.statusBar().showMessage(
                f"Save error: {exc}",
                5000,
            )

    def _restore_window(self):
        try:
            width = int(self.settings.get("window_width", 760))
        except (TypeError, ValueError):
            width = 760
        try:
            height = int(self.settings.get("window_height", 820))
        except (TypeError, ValueError):
            height = 820

        self.resize(max(700, width), max(700, height))

    def closeEvent(self, event):
        self.settings[
            "window_width"
        ] = self.width()

        self.settings[
            "window_height"
        ] = self.height()

        self._save()

        if (
            self.offset_worker
            and self.offset_worker.isRunning()
        ):
            self.offset_worker.quit()
            self.offset_worker.wait(1500)

        self._disconnect_process()
        event.accept()


# ============================================================
# Application entry
# ============================================================

def main():
    app = QtWidgets.QApplication(
        sys.argv
    )

    app.setApplicationName(
        "Blossom"
    )

    app.setApplicationVersion(
        "2.0"
    )

    app.setOrganizationName(
        "Blossom"
    )

    app.setStyle(
        "Fusion"
    )

    window = BlossomApp()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
