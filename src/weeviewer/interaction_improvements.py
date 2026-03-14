"""
Interaction Improvements Module
Contains path validation, drag-and-drop support, and layout management
"""
import wx
import wx.adv
import json
import re
import logging
from typing import Tuple, List, Optional, Any, Dict, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Path Validation System
# ============================================================================

class ValidationErrorType(Enum):
    """Validation error types"""
    SYNTAX_ERROR = "syntax_error"
    INVALID_NODE = "invalid_node"
    OUT_OF_RANGE = "out_of_range"
    INVALID_INDEX = "invalid_index"
    EMPTY_PATH = "empty_path"
    INVALID_TYPE = "invalid_type"


@dataclass
class ValidationError:
    """Validation error"""
    error_type: ValidationErrorType
    message: str
    position: int
    suggestion: Optional[str] = None


class PathValidator:
    """Path validator"""

    def __init__(self, file_type: str, data: Any):
        """Initialize path validator

        Args:
            file_type: File type (json/xml)
            data: Data object
        """
        self.file_type = file_type
        self.data = data
        logger.debug(f"PathValidator initialized: file_type={file_type}")

    def validate(self, path: str) -> Tuple[bool, List[ValidationError]]:
        """Validate path

        Args:
            path: Path string

        Returns:
            (is_valid, error_list)
        """
        if not path or not path.strip():
            return False, [ValidationError(
                ValidationErrorType.EMPTY_PATH,
                "Path cannot be empty",
                0,
                "Please enter a valid path"
            )]

        if self.file_type == 'json':
            return self._validate_json_path(path)
        elif self.file_type == 'xml':
            return self._validate_xml_path(path)
        else:
            return False, [ValidationError(
                ValidationErrorType.SYNTAX_ERROR,
                f"Unknown file type: {self.file_type}",
                0
            )]

    def _validate_json_path(self, path: str) -> Tuple[bool, List[ValidationError]]:
        """Validate JSON path

        Args:
            path: JSON path

        Returns:
            (is_valid, error_list)
        """
        errors = []

        # Remove leading $
        if path.startswith('

    def _validate_xml_path(self, path: str) -> Tuple[bool, List[ValidationError]]:
        """Validate XML path

        Args:
            path: XML path

        Returns:
            (is_valid, error_list)
        """
        errors = []

        # Split path segments
        parts = [p.strip() for p in path.split('/') if p.strip()]

        if not parts:
            errors.append(ValidationError(
                ValidationErrorType.EMPTY_PATH,
                "Path cannot be empty",
                0,
                "Please enter a valid XML path"
            ))
            return False, errors

        # Validate each path segment
        try:
            current_element = self.data

            for i, part in enumerate(parts):
                # Parse tag name and index
                match = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if not match:
                    errors.append(ValidationError(
                        ValidationErrorType.SYNTAX_ERROR,
                        f"Invalid path segment: '{part}'",
                        sum(len(p) for p in parts[:i]) + i,
                        "Correct format: tag or tag[index]"
                    ))
                    return False, errors

                tag = match.group(1)
                index_str = match.group(2)

                # Find element
                children = list(current_element.findall(tag))
                if not children:
                    available_tags = list(set(child.tag for child in current_element))
                    errors.append(ValidationError(
                        ValidationErrorType.INVALID_NODE,
                        f"Tag '{tag}' not found",
                        sum(len(p) for p in parts[:i]) + i,
                        f"Available tags: {', '.join(available_tags[:5])}..."
                    ))
                    return False, errors

                # Handle index
                if index_str:
                    try:
                        index = int(index_str)
                        if index < 1:
                            errors.append(ValidationError(
                                ValidationErrorType.INVALID_INDEX,
                                f"XML index must be >= 1 (XPath standard)",
                                match.start(),
                                "Please use index >= 1"
                            ))
                            return False, errors

                        if index > len(children):
                            errors.append(ValidationError(
                                ValidationErrorType.OUT_OF_RANGE,
                                f"Index {index} is out of range (1-{len(children)})",
                                match.start(),
                                f"Valid range: 1-{len(children)}"
                            ))
                            return False, errors

                        current_element = children[index - 1]

                    except ValueError:
                        errors.append(ValidationError(
                            ValidationErrorType.INVALID_INDEX,
                            f"Invalid index: {index_str}",
                            match.start(),
                            "Index must be an integer"
                        ))
                        return False, errors
                else:
                    current_element = children[0]

            return True, []

        except Exception as e:
            errors.append(ValidationError(
                ValidationErrorType.SYNTAX_ERROR,
                f"Error during validation: {str(e)}",
                0
            ))
            return False, errors


class PathValidationPanel(wx.Panel):
    """Path validation panel"""

    def __init__(self, parent, on_path_change_callback=None):
        """Initialize path validation panel

        Args:
            parent: Parent window
            on_path_change_callback: Path change callback
        """
        super().__init__(parent)
        self.on_path_change_callback = on_path_change_callback
        self.validator: Optional[PathValidator] = None
        self.validation_timer = wx.Timer(self)

        self._create_ui()
        self._bind_events()

    def _create_ui(self):
        """Create UI"""
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Path input field
        self.path_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.path_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)

        # Validation status icon
        self.status_icon = wx.StaticBitmap(self, bitmap=wx.Bitmap(16, 16))
        sizer.Add(self.status_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        # Error hint
        self.error_label = wx.StaticText(self, label="")
        self.error_label.SetForegroundColour(wx.Colour(255, 0, 0))
        sizer.Add(self.error_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.SetSizer(sizer)

    def _bind_events(self):
        """Bind events"""
        self.path_ctrl.Bind(wx.EVT_TEXT, self._on_path_changed)
        self.Bind(wx.EVT_TIMER, self._on_validation_timer, self.validation_timer)

    def set_validator(self, validator: PathValidator):
        """Set validator

        Args:
            validator: Path validator
        """
        self.validator = validator

    def _on_path_changed(self, event):
        """Path change event"""
        # Delayed validation (debounce)
        self.validation_timer.Start(300, oneShot=True)
        event.Skip()

    def _on_validation_timer(self, event):
        """Validation timer event"""
        if not self.validator:
            return

        path = self.path_ctrl.GetValue()
        is_valid, errors = self.validator.validate(path)

        # Update status icon
        if not path:
            # Empty path
            self._draw_empty_icon()
            self.error_label.SetLabel("")
        elif is_valid:
            # Valid path
            self._draw_check_icon()
            self.error_label.SetLabel("Path is valid")
            self.error_label.SetForegroundColour(wx.Colour(0, 128, 0))
        else:
            # Invalid path
            self._draw_error_icon()
            if errors:
                error = errors[0]
                self.error_label.SetLabel(error.message)
                self.error_label.SetForegroundColour(wx.Colour(255, 0, 0))

        # Notify callback
        if self.on_path_change_callback:
            self.on_path_change_callback(path, is_valid, errors)

    def _draw_check_icon(self):
        """Draw check icon"""
        bitmap = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.TRANSPARENT))
        dc.Clear()

        # Green checkmark
        dc.SetPen(wx.Pen(wx.Colour(0, 128, 0), 2))
        dc.SetBrush(wx.Brush(wx.TRANSPARENT))

        # Draw circle
        dc.DrawCircle(8, 8, 7)

        # Draw checkmark
        dc.DrawLines([(5, 8), (7, 10), (11, 6)])

        dc.SelectObject(wx.NullBitmap)
        self.status_icon.SetBitmap(bitmap)

    def _draw_error_icon(self):
        """Draw error icon"""
        bitmap = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.TRANSPARENT))
        dc.Clear()

        # Red cross
        dc.SetPen(wx.Pen(wx.Colour(255, 0, 0), 2))
        dc.SetBrush(wx.Brush(wx.TRANSPARENT))

        # Draw circle
        dc.DrawCircle(8, 8, 7)

        # Draw cross
        dc.DrawLine(5, 5, 11, 11)
        dc.DrawLine(11, 5, 5, 11)

        dc.SelectObject(wx.NullBitmap)
        self.status_icon.SetBitmap(bitmap)

    def _draw_empty_icon(self):
        """Draw empty icon"""
        bitmap = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.TRANSPARENT))
        dc.Clear()
        dc.SelectObject(wx.NullBitmap)
        self.status_icon.SetBitmap(bitmap)

    def get_path(self) -> str:
        """Get path

        Returns:
            Path string
        """
        return self.path_ctrl.GetValue()

    def set_path(self, path: str):
        """Set path

        Args:
            path: Path string
        """
        self.path_ctrl.SetValue(path)


# ============================================================================
# Drag and Drop Support
# ============================================================================

class PathDropSource(wx.DropSource):
    """Path drag source"""

    def __init__(self, path: str, format_type: str = "text"):
        """Initialize drag source

        Args:
            path: Path string
            format_type: Format type (text/jsonpath/xpath)
        """
        super().__init__()
        self.path = path
        self.format_type = format_type

        # Create data object
        data = wx.DataObjectComposite()

        # Text format
        text_data = wx.TextDataObject(path)
        data.Add(text_data)

        # Custom format
        custom_data = wx.CustomDataObject("path")
        custom_data.SetData(path.encode('utf-8'))
        data.Add(custom_data)

        self.SetData(data)

    def DoDragDrop(self, flags: int = wx.Drag_AllowMove) -> int:
        """Execute drag and drop

        Args:
            flags: Drag and drop flags

        Returns:
            Drag and drop result
        """
        return super().DoDragDrop(flags)


class FileDropTarget(wx.FileDropTarget):
    """File drop target"""

    def __init__(self, frame):
        """Initialize file drop target

        Args:
            frame: Main window
        """
        super().__init__()
        self.frame = frame

    def OnDropFiles(self, x: int, y: int, filenames: List[str]) -> bool:
        """Handle file drop

        Args:
            x: X coordinate
            y: Y coordinate
            filenames: File name list

        Returns:
            Success status
        """
        for filename in filenames:
            if filename.endswith('.xml') or filename.endswith('.json'):
                # Call main window's file loading method
                if hasattr(self.frame, '_load_file_in_background'):
                    self.frame._load_file_in_background(
                        filename,
                        'json' if filename.endswith('.json') else 'xml'
                    )
                elif hasattr(self.frame, 'on_load_file'):
                    # Fallback method
                    self.frame.file_path = filename
                    self.frame.current_file_type = 'json' if filename.endswith('.json') else 'xml'
                    self.frame.on_load_file(None)
                break
        return True


class BookmarkDropTarget(wx.TextDropTarget):
    """Bookmark drop target"""

    def __init__(self, bookmark_manager):
        """Initialize bookmark drop target

        Args:
            bookmark_manager: Bookmark manager
        """
        super().__init__()
        self.bookmark_manager = bookmark_manager

    def OnDropText(self, x: int, y: int, text: str) -> bool:
        """Handle text drop

        Args:
            x: X coordinate
            y: Y coordinate
            text: Dropped text

        Returns:
            Success status
        """
        # Parse dropped bookmark data
        try:
            data = json.loads(text)
            if 'id' in data and 'name' in data:
                # Add bookmark
                if hasattr(self.bookmark_manager, 'add_bookmark'):
                    from allnew import Bookmark
                    bookmark = Bookmark(
                        id=data['id'],
                        name=data['name'],
                        path=data['path'],
                        file_path=data.get('file_path', ''),
                        file_type=data.get('file_type', 'json'),
                        description=data.get('description', ''),
                        created_time=data.get('created_time', ''),
                        group=data.get('group', 'Default Group')
                    )
                    self.bookmark_manager.add_bookmark(bookmark)
                return True
        except Exception as e:
            logger.error(f"Failed to parse bookmark data: {e}")

        return False


# ============================================================================
# Layout Management
# ============================================================================

@dataclass
class PanelLayout:
    """Panel layout configuration"""
    name: str
    width: int
    height: int
    position_x: int
    position_y: int
    is_visible: bool
    is_docked: bool
    dock_area: Optional[str] = None  # left, right, top, bottom
    splitter_pos: int = 500  # Splitter position


class LayoutManager:
    """Layout manager"""

    def __init__(self, window, config_manager):
        """Initialize layout manager

        Args:
            window: Main window
            config_manager: Configuration manager
        """
        self.window = window
        self.config = config_manager
        self.panels: Dict[str, wx.Window] = {}
        self.layouts: Dict[str, PanelLayout] = {}
        self.current_layout: Optional[str] = None

        # Define default layouts
        self._define_default_layouts()

        logger.info("LayoutManager initialized")

    def _define_default_layouts(self):
        """Define default layouts"""
        # Default layout
        self.layouts['default'] = PanelLayout(
            name='default',
            width=1000,
            height=700,
            position_x=100,
            position_y=100,
            is_visible=True,
            is_docked=True,
            splitter_pos=500
        )

        # Wide screen layout
        self.layouts['wide'] = PanelLayout(
            name='wide',
            width=1400,
            height=800,
            position_x=50,
            position_y=50,
            is_visible=True,
            is_docked=True,
            splitter_pos=700
        )

        # Compact layout
        self.layouts['compact'] = PanelLayout(
            name='compact',
            width=800,
            height=900,
            position_x=200,
            position_y=50,
            is_visible=True,
            is_docked=True,
            splitter_pos=400
        )

        # Large screen layout
        self.layouts['large'] = PanelLayout(
            name='large',
            width=1600,
            height=900,
            position_x=20,
            position_y=20,
            is_visible=True,
            is_docked=True,
            splitter_pos=800
        )

    def register_panel(self, panel_id: str, panel: wx.Window):
        """Register panel

        Args:
            panel_id: Panel ID
            panel: Panel window
        """
        self.panels[panel_id] = panel

    def apply_layout(self, layout_name: str):
        """Apply layout

        Args:
            layout_name: Layout name
        """
        if layout_name not in self.layouts:
            logger.warning(f"Layout does not exist: {layout_name}")
            return False

        layout = self.layouts[layout_name]
        self.current_layout = layout_name

        # Apply window size and position
        self.window.SetSize(layout.width, layout.height)
        self.window.SetPosition((layout.position_x, layout.position_y))

        # Update splitter position
        if hasattr(self.window, 'splitter'):
            self.window.splitter.SetSashPosition(layout.splitter_pos)

        # Refresh display
        self.window.Refresh()

        logger.info(f"Applied layout: {layout_name}")
        return True

    def save_current_layout(self, name: str):
        """Save current layout

        Args:
            name: Layout name
        """
        # Get current window state
        size = self.window.GetSize()
        position = self.window.GetPosition()

        # Get splitter position
        splitter_pos = 500
        if hasattr(self.window, 'splitter'):
            splitter_pos = self.window.splitter.GetSashPosition()

        # Create layout configuration
        layout = PanelLayout(
            name=name,
            width=size.GetWidth(),
            height=size.GetHeight(),
            position_x=position.x,
            position_y=position.y,
            is_visible=True,
            is_docked=True,
            splitter_pos=splitter_pos
        )

        self.layouts[name] = layout
        logger.info(f"Saved layout: {name}")

    def get_available_layouts(self) -> List[str]:
        """Get available layout list

        Returns:
            Layout name list
        """
        return list(self.layouts.keys())

    def get_current_layout(self) -> Optional[str]:
        """Get current layout name

        Returns:
            Current layout name
        """
        return self.current_layout

    def delete_layout(self, name: str) -> bool:
        """Delete layout

        Args:
            name: Layout name

        Returns:
            Success status
        """
        if name == 'default':
            logger.warning("Cannot delete default layout")
            return False

        if name in self.layouts:
            del self.layouts[name]
            logger.info(f"Deleted layout: {name}")
            return True

        return False
):
            path = path[1:].strip()

        # Validate syntax
        pattern = r'\["(.*?)"\]|\[(\d+)\]'
        matches = list(re.finditer(pattern, path))

        if not matches:
            errors.append(ValidationError(
                ValidationErrorType.SYNTAX_ERROR,
                "Path format is incorrect",
                0,
                "Correct format: [\"key\"] or [index]"
            ))
            return False, errors

        # Validate each path segment
        try:
            current_data = self.data

            for match in matches:
                key = match.group(1)
                index = match.group(2)

                if key:
                    # Validate key name
                    if isinstance(current_data, dict):
                        if key not in current_data:
                            errors.append(ValidationError(
                                ValidationErrorType.INVALID_NODE,
                                f"Key '{key}' does not exist",
                                match.start(),
                                f"Available keys: {', '.join(list(current_data.keys())[:5])}..."
                            ))
                            return False, errors
                        current_data = current_data[key]
                    else:
                        errors.append(ValidationError(
                            ValidationErrorType.SYNTAX_ERROR,
                            f"Current node is not an object, cannot access using key name",
                            match.start(),
                            "Use array index or check data structure"
                        ))
                        return False, errors

                elif index:
                    # Validate index
                    try:
                        idx = int(index)
                        if isinstance(current_data, list):
                            if idx < 0 or idx >= len(current_data):
                                errors.append(ValidationError(
                                    ValidationErrorType.OUT_OF_RANGE,
                                    f"Index {idx} is out of range (0-{len(current_data)-1})",
                                    match.start(),
                                    f"Valid range: 0-{len(current_data)-1}"
                                ))
                                return False, errors
                            current_data = current_data[idx]
                        else:
                            errors.append(ValidationError(
                                ValidationErrorType.SYNTAX_ERROR,
                                f"Current node is not an array, cannot access using index",
                                match.start(),
                                "Use key name access or check data structure"
                            ))
                            return False, errors
                    except ValueError:
                        errors.append(ValidationError(
                            ValidationErrorType.INVALID_INDEX,
                            f"Invalid index: {index}",
                            match.start(),
                            "Index must be an integer"
                        ))
                        return False, errors

            return True, []

        except Exception as e:
            errors.append(ValidationError(
                ValidationErrorType.SYNTAX_ERROR,
                f"Error during validation: {str(e)}",
                0
            ))
            return False, errors

    def _validate_xml_path(self, path: str) -> Tuple[bool, List[ValidationError]]:
        """Validate XML path

        Args:
            path: XML path

        Returns:
            (is_valid, error_list)
        """
        errors = []

        # Split path segments
        parts = [p.strip() for p in path.split('/') if p.strip()]

        if not parts:
            errors.append(ValidationError(
                ValidationErrorType.EMPTY_PATH,
                "Path cannot be empty",
                0,
                "Please enter a valid XML path"
            ))
            return False, errors

        # Validate each path segment
        try:
            current_element = self.data

            for i, part in enumerate(parts):
                # Parse tag name and index
                match = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if not match:
                    errors.append(ValidationError(
                        ValidationErrorType.SYNTAX_ERROR,
                        f"Invalid path segment: '{part}'",
                        sum(len(p) for p in parts[:i]) + i,
                        "Correct format: tag or tag[index]"
                    ))
                    return False, errors

                tag = match.group(1)
                index_str = match.group(2)

                # Find element
                children = list(current_element.findall(tag))
                if not children:
                    available_tags = list(set(child.tag for child in current_element))
                    errors.append(ValidationError(
                        ValidationErrorType.INVALID_NODE,
                        f"Tag '{tag}' not found",
                        sum(len(p) for p in parts[:i]) + i,
                        f"Available tags: {', '.join(available_tags[:5])}..."
                    ))
                    return False, errors

                # Handle index
                if index_str:
                    try:
                        index = int(index_str)
                        if index < 1:
                            errors.append(ValidationError(
                                ValidationErrorType.INVALID_INDEX,
                                f"XML index must be >= 1 (XPath standard)",
                                match.start(),
                                "Please use index >= 1"
                            ))
                            return False, errors

                        if index > len(children):
                            errors.append(ValidationError(
                                ValidationErrorType.OUT_OF_RANGE,
                                f"Index {index} is out of range (1-{len(children)})",
                                match.start(),
                                f"Valid range: 1-{len(children)}"
                            ))
                            return False, errors

                        current_element = children[index - 1]

                    except ValueError:
                        errors.append(ValidationError(
                            ValidationErrorType.INVALID_INDEX,
                            f"Invalid index: {index_str}",
                            match.start(),
                            "Index must be an integer"
                        ))
                        return False, errors
                else:
                    current_element = children[0]

            return True, []

        except Exception as e:
            errors.append(ValidationError(
                ValidationErrorType.SYNTAX_ERROR,
                f"Error during validation: {str(e)}",
                0
            ))
            return False, errors


class PathValidationPanel(wx.Panel):
    """Path validation panel"""

    def __init__(self, parent, on_path_change_callback=None):
        """Initialize path validation panel

        Args:
            parent: Parent window
            on_path_change_callback: Path change callback
        """
        super().__init__(parent)
        self.on_path_change_callback = on_path_change_callback
        self.validator: Optional[PathValidator] = None
        self.validation_timer = wx.Timer(self)

        self._create_ui()
        self._bind_events()

    def _create_ui(self):
        """Create UI"""
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Path input field
        self.path_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.path_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)

        # Validation status icon
        self.status_icon = wx.StaticBitmap(self, bitmap=wx.Bitmap(16, 16))
        sizer.Add(self.status_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        # Error hint
        self.error_label = wx.StaticText(self, label="")
        self.error_label.SetForegroundColour(wx.Colour(255, 0, 0))
        sizer.Add(self.error_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.SetSizer(sizer)

    def _bind_events(self):
        """Bind events"""
        self.path_ctrl.Bind(wx.EVT_TEXT, self._on_path_changed)
        self.Bind(wx.EVT_TIMER, self._on_validation_timer, self.validation_timer)

    def set_validator(self, validator: PathValidator):
        """Set validator

        Args:
            validator: Path validator
        """
        self.validator = validator

    def _on_path_changed(self, event):
        """Path change event"""
        # Delayed validation (debounce)
        self.validation_timer.Start(300, oneShot=True)
        event.Skip()

    def _on_validation_timer(self, event):
        """Validation timer event"""
        if not self.validator:
            return

        path = self.path_ctrl.GetValue()
        is_valid, errors = self.validator.validate(path)

        # Update status icon
        if not path:
            # Empty path
            self._draw_empty_icon()
            self.error_label.SetLabel("")
        elif is_valid:
            # Valid path
            self._draw_check_icon()
            self.error_label.SetLabel("Path is valid")
            self.error_label.SetForegroundColour(wx.Colour(0, 128, 0))
        else:
            # Invalid path
            self._draw_error_icon()
            if errors:
                error = errors[0]
                self.error_label.SetLabel(error.message)
                self.error_label.SetForegroundColour(wx.Colour(255, 0, 0))

        # Notify callback
        if self.on_path_change_callback:
            self.on_path_change_callback(path, is_valid, errors)

    def _draw_check_icon(self):
        """Draw check icon"""
        bitmap = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.TRANSPARENT))
        dc.Clear()

        # Green checkmark
        dc.SetPen(wx.Pen(wx.Colour(0, 128, 0), 2))
        dc.SetBrush(wx.Brush(wx.TRANSPARENT))

        # Draw circle
        dc.DrawCircle(8, 8, 7)

        # Draw checkmark
        dc.DrawLines([(5, 8), (7, 10), (11, 6)])

        dc.SelectObject(wx.NullBitmap)
        self.status_icon.SetBitmap(bitmap)

    def _draw_error_icon(self):
        """Draw error icon"""
        bitmap = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.TRANSPARENT))
        dc.Clear()

        # Red cross
        dc.SetPen(wx.Pen(wx.Colour(255, 0, 0), 2))
        dc.SetBrush(wx.Brush(wx.TRANSPARENT))

        # Draw circle
        dc.DrawCircle(8, 8, 7)

        # Draw cross
        dc.DrawLine(5, 5, 11, 11)
        dc.DrawLine(11, 5, 5, 11)

        dc.SelectObject(wx.NullBitmap)
        self.status_icon.SetBitmap(bitmap)

    def _draw_empty_icon(self):
        """Draw empty icon"""
        bitmap = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.TRANSPARENT))
        dc.Clear()
        dc.SelectObject(wx.NullBitmap)
        self.status_icon.SetBitmap(bitmap)

    def get_path(self) -> str:
        """Get path

        Returns:
            Path string
        """
        return self.path_ctrl.GetValue()

    def set_path(self, path: str):
        """Set path

        Args:
            path: Path string
        """
        self.path_ctrl.SetValue(path)


# ============================================================================
# Drag and Drop Support
# ============================================================================

class PathDropSource(wx.DropSource):
    """Path drag source"""

    def __init__(self, path: str, format_type: str = "text"):
        """Initialize drag source

        Args:
            path: Path string
            format_type: Format type (text/jsonpath/xpath)
        """
        super().__init__()
        self.path = path
        self.format_type = format_type

        # Create data object
        data = wx.DataObjectComposite()

        # Text format
        text_data = wx.TextDataObject(path)
        data.Add(text_data)

        # Custom format
        custom_data = wx.CustomDataObject("path")
        custom_data.SetData(path.encode('utf-8'))
        data.Add(custom_data)

        self.SetData(data)

    def DoDragDrop(self, flags: int = wx.Drag_AllowMove) -> int:
        """Execute drag and drop

        Args:
            flags: Drag and drop flags

        Returns:
            Drag and drop result
        """
        return super().DoDragDrop(flags)


class FileDropTarget(wx.FileDropTarget):
    """File drop target"""

    def __init__(self, frame):
        """Initialize file drop target

        Args:
            frame: Main window
        """
        super().__init__()
        self.frame = frame

    def OnDropFiles(self, x: int, y: int, filenames: List[str]) -> bool:
        """Handle file drop

        Args:
            x: X coordinate
            y: Y coordinate
            filenames: File name list

        Returns:
            Success status
        """
        for filename in filenames:
            if filename.endswith('.xml') or filename.endswith('.json'):
                # Call main window's file loading method
                if hasattr(self.frame, '_load_file_in_background'):
                    self.frame._load_file_in_background(
                        filename,
                        'json' if filename.endswith('.json') else 'xml'
                    )
                elif hasattr(self.frame, 'on_load_file'):
                    # Fallback method
                    self.frame.file_path = filename
                    self.frame.current_file_type = 'json' if filename.endswith('.json') else 'xml'
                    self.frame.on_load_file(None)
                break
        return True


class BookmarkDropTarget(wx.TextDropTarget):
    """Bookmark drop target"""

    def __init__(self, bookmark_manager):
        """Initialize bookmark drop target

        Args:
            bookmark_manager: Bookmark manager
        """
        super().__init__()
        self.bookmark_manager = bookmark_manager

    def OnDropText(self, x: int, y: int, text: str) -> bool:
        """Handle text drop

        Args:
            x: X coordinate
            y: Y coordinate
            text: Dropped text

        Returns:
            Success status
        """
        # Parse dropped bookmark data
        try:
            data = json.loads(text)
            if 'id' in data and 'name' in data:
                # Add bookmark
                if hasattr(self.bookmark_manager, 'add_bookmark'):
                    from allnew import Bookmark
                    bookmark = Bookmark(
                        id=data['id'],
                        name=data['name'],
                        path=data['path'],
                        file_path=data.get('file_path', ''),
                        file_type=data.get('file_type', 'json'),
                        description=data.get('description', ''),
                        created_time=data.get('created_time', ''),
                        group=data.get('group', 'Default Group')
                    )
                    self.bookmark_manager.add_bookmark(bookmark)
                return True
        except Exception as e:
            logger.error(f"Failed to parse bookmark data: {e}")

        return False


# ============================================================================
# Layout Management
# ============================================================================

@dataclass
class PanelLayout:
    """Panel layout configuration"""
    name: str
    width: int
    height: int
    position_x: int
    position_y: int
    is_visible: bool
    is_docked: bool
    dock_area: Optional[str] = None  # left, right, top, bottom
    splitter_pos: int = 500  # Splitter position


class LayoutManager:
    """Layout manager"""

    def __init__(self, window, config_manager):
        """Initialize layout manager

        Args:
            window: Main window
            config_manager: Configuration manager
        """
        self.window = window
        self.config = config_manager
        self.panels: Dict[str, wx.Window] = {}
        self.layouts: Dict[str, PanelLayout] = {}
        self.current_layout: Optional[str] = None

        # Define default layouts
        self._define_default_layouts()

        logger.info("LayoutManager initialized")

    def _define_default_layouts(self):
        """Define default layouts"""
        # Default layout
        self.layouts['default'] = PanelLayout(
            name='default',
            width=1000,
            height=700,
            position_x=100,
            position_y=100,
            is_visible=True,
            is_docked=True,
            splitter_pos=500
        )

        # Wide screen layout
        self.layouts['wide'] = PanelLayout(
            name='wide',
            width=1400,
            height=800,
            position_x=50,
            position_y=50,
            is_visible=True,
            is_docked=True,
            splitter_pos=700
        )

        # Compact layout
        self.layouts['compact'] = PanelLayout(
            name='compact',
            width=800,
            height=900,
            position_x=200,
            position_y=50,
            is_visible=True,
            is_docked=True,
            splitter_pos=400
        )

        # Large screen layout
        self.layouts['large'] = PanelLayout(
            name='large',
            width=1600,
            height=900,
            position_x=20,
            position_y=20,
            is_visible=True,
            is_docked=True,
            splitter_pos=800
        )

    def register_panel(self, panel_id: str, panel: wx.Window):
        """Register panel

        Args:
            panel_id: Panel ID
            panel: Panel window
        """
        self.panels[panel_id] = panel

    def apply_layout(self, layout_name: str):
        """Apply layout

        Args:
            layout_name: Layout name
        """
        if layout_name not in self.layouts:
            logger.warning(f"Layout does not exist: {layout_name}")
            return False

        layout = self.layouts[layout_name]
        self.current_layout = layout_name

        # Apply window size and position
        self.window.SetSize(layout.width, layout.height)
        self.window.SetPosition((layout.position_x, layout.position_y))

        # Update splitter position
        if hasattr(self.window, 'splitter'):
            self.window.splitter.SetSashPosition(layout.splitter_pos)

        # Refresh display
        self.window.Refresh()

        logger.info(f"Applied layout: {layout_name}")
        return True

    def save_current_layout(self, name: str):
        """Save current layout

        Args:
            name: Layout name
        """
        # Get current window state
        size = self.window.GetSize()
        position = self.window.GetPosition()

        # Get splitter position
        splitter_pos = 500
        if hasattr(self.window, 'splitter'):
            splitter_pos = self.window.splitter.GetSashPosition()

        # Create layout configuration
        layout = PanelLayout(
            name=name,
            width=size.GetWidth(),
            height=size.GetHeight(),
            position_x=position.x,
            position_y=position.y,
            is_visible=True,
            is_docked=True,
            splitter_pos=splitter_pos
        )

        self.layouts[name] = layout
        logger.info(f"Saved layout: {name}")

    def get_available_layouts(self) -> List[str]:
        """Get available layout list

        Returns:
            Layout name list
        """
        return list(self.layouts.keys())

    def get_current_layout(self) -> Optional[str]:
        """Get current layout name

        Returns:
            Current layout name
        """
        return self.current_layout

    def delete_layout(self, name: str) -> bool:
        """Delete layout

        Args:
            name: Layout name

        Returns:
            Success status
        """
        if name == 'default':
            logger.warning("Cannot delete default layout")
            return False

        if name in self.layouts:
            del self.layouts[name]
            logger.info(f"Deleted layout: {name}")
            return True

        return False
