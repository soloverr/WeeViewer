import wx
import os
from lxml import etree as ET
import json
import threading
import re
import pyperclip  # For clipboard operations
from . import appico
import sys
from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('viewer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import configuration manager
try:
    from .config_manager import ConfigManager
except ImportError:
    logger.warning("Cannot import ConfigManager, using default configuration")
    ConfigManager = None

# Import search engine
try:
    from .search_engine import TreeSearchEngine, SearchResult
except ImportError:
    logger.warning("Cannot import TreeSearchEngine, search functionality will be unavailable")
    TreeSearchEngine = None
    SearchResult = None

# Configuration constants
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB - Large file warning threshold
WARNING_FILE_SIZE = 100 * 1024 * 1024  # 100 MB - Prohibit loading threshold

# Chinese error message mapping (for UI display)
ERROR_MESSAGES = {
    'tag_not_found': "Tag not found�?'{tag}'锛岃�锋��鏌ヨ矾寰勬槸鍚︽�ｇ�?,  # Tag not found, please check if the path is correct
    'index_out_of_bounds': "Index {index} out of range锛堟爣绛?'{tag}' 鍏辨湁 {count} 涓�瀛愬厓绱狅紝valid range: 1-{count}),  # Index out of bounds
    'invalid_index': "鏃犳晥鐨勭储寮?'{index}'锛氱储寮曞繀椤?>= 1锛圶Path 鏍囧噯锛?,  # Invalid index, must be >= 1 (XPath standard)
    'invalid_path_segment': "Invalid path segment: '{segment}'",  # Invalid path segment
    'file_too_large': "File too large ({size:.1f} MB)锛岃秴杩囬檺鍒?({limit:.0f} MB)\n\n寤鸿��锛歕n1. Use streaming parser\n2. Split file and load separately\n3. 浣跨敤涓撲笟鐨勫ぇ鏂囦欢鏌ョ湅鍣?,  # File too large
    'file_load_error': "Failed to load file: {reason}\n\n鏂囦欢: {path}\n\n璇锋��鏌ワ細\n1. 鏂囦欢鏍煎紡鏄�鍚︽�ｇ‘锛?xml 鎴?.json锛塡n2. File is corruptedn3. Has read permission\n4. File encoding is UTF-8",  # File load error
    'ui_update_error': "Error updating UI {reason}",  # UI update error
    'copy_success': "Copied key name {key_name}",  # Copied key name
    'copy_value_success': "宸插�嶅埗閿�鍊煎埌鍓�璐存�?,  # Copied value to clipboard
    'copy_failed': "Copy failed: {reason}\n璺�寰�: {path}",  # Copy failed
    'no_content_found': "No content found?,  # No content found
    'loading': "Loading file, please wait..",  # Loading file, please wait...
    'loading_complete': "Loading complete",  # Loading complete
    'loading_failed': "Loading failed",  # Loading failed
    'enter_valid_path': "Please enter a valid path",  # Please enter a valid path
    'root_node': "Root node,  # Root node
    'unknown_file_type': "Unknown file type?,  # Unknown file type
    'node_not_found': "Cannot find node content�",  # Cannot find node content
}



# ========== Data Class Definitions ==========

# TokenType
class TokenType(Enum):
    """Token type enumeration for syntax highlighting"""
    JSON_KEY = 'json_key'
    JSON_STRING = 'json_string'
    JSON_NUMBER = 'json_number'
    JSON_BOOLEAN = 'json_boolean'
    JSON_NULL = 'json_null'
    JSON_OBJECT_START = 'json_object_start'
    JSON_OBJECT_END = 'json_object_end'
    JSON_ARRAY_START = 'json_array_start'
    JSON_ARRAY_END = 'json_array_end'
    XML_TAG = 'xml_tag'
    XML_ATTRIBUTE_NAME = 'xml_attribute_name'
    XML_ATTRIBUTE_VALUE = 'xml_attribute_value'
    XML_COMMENT = 'xml_comment'
    XML_CDATA = 'xml_cdata'
    WHITESPACE = 'whitespace'
    UNKNOWN = 'unknown'



# Token
@dataclass
class Token:
    """Syntax token for highlighting

    Attributes:
        type: The token type
        value: The token value
        start: Starting position in the text
        end: Ending position in the text
    """
    type: TokenType
    value: str
    start: int
    end: int



# FileHistoryItem
@dataclass
class FileHistoryItem:
    """File history record item

    Attributes:
        file_path: Path to the file
        access_time: Last access timestamp
        access_count: Number of times accessed
        file_type: Type of file (json/xml)
    """
    file_path: str
    access_time: str
    access_count: int = 1
    file_type: str = ""
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, FileHistoryItem):
            return False
        return self.file_path == other.file_path
    
    def __hash__(self) -> int:
        return hash(self.file_path)



# PathHistoryItem
@dataclass
class PathHistoryItem:
    """Path history record item

    Attributes:
        path: Path string (XPath or JSONPath)
        access_time: Last access timestamp
        access_count: Number of times accessed
        file_path: Associated file path
        file_type: Type of file (json/xml)
    """
    path: str
    access_time: str
    access_count: int = 1
    file_path: str = ""
    file_type: str = ""
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, PathHistoryItem):
            return False
        return self.path == other.path and self.file_path == other.file_path
    
    def __hash__(self) -> int:
        return hash((self.path, self.file_path))



# Bookmark
@dataclass
class Bookmark:
    """Bookmark for saving important node locations

    Attributes:
        id: Unique bookmark identifier
        name: Bookmark display name
        path: Node path (XPath or JSONPath)
        file_path: Associated file path
        file_type: Type of file (json/xml)
        description: Optional description
        created_time: Creation timestamp
        group: Bookmark group name
    """
    id: str
    name: str
    path: str
    file_path: str
    file_type: str
    description: str = ""
    created_time: str = ""
    group: str = "Default Group"  # Default group



# TabData
@dataclass
class TabData:
    """Tab page data

    Attributes:
        id: Unique tab identifier
        title: Tab display title
        file_path: Associated file path
        file_type: Type of file (json/xml)
        data: File content data
        current_path: Current selected path
        is_modified: Whether tab has unsaved changes
    """
    id: str
    title: str
    file_path: str
    file_type: str
    data: Any
    current_path: str = ""
    is_modified: bool = False



class WeeViewer(wx.Frame):
    """Main application window for viewing XML/JSON files

    Provides a tree view of structured data with path navigation,
    search functionality, bookmarks, and export options.
    """

    def __init__(self):
        """Initialize the WeeViewer main window"""
        super().__init__(parent=None, title='WeeViewer', size=(1000, 700))
        self.SetIcon(appico.create_icon())

        # Basic state
        self.current_file_type = None
        self.file_path = None
        self.current_data = None

        # Flags to prevent recursive calls
        self._is_syncing = False
        self._is_updating_path = False  # Prevent triggering sync during path updates

        # Initialize configuration manager
        try:
            self.config_manager = ConfigManager()
        except:
            self.config_manager = None
            logger.warning("Configuration manager initialization failed, using default configuration")

        # Initialize history managers
        self.file_history_manager = FileHistoryManager(self.config_manager)
        self.path_history_manager = PathHistoryManager(self.config_manager)

        # Initialize theme manager
        self.theme_manager = ThemeManager(self.config_manager)

        # Initialize export engine
        self.export_engine = ExportEngine()

        # Initialize bookmark manager
        self.bookmark_manager = BookmarkManager(self.config_manager)

        # Initialize cache manager
        try:
            from performance_optimizations import CacheManager
            self.cache_manager = CacheManager()
            logger.info("Cache manager initialized successfully")
        except ImportError:
            self.cache_manager = None
            logger.warning("Cache manager initialization failed")

        # Initialize layout manager
        try:
            from interaction_improvements import LayoutManager
            self.layout_manager = LayoutManager(self, self.config_manager)
            logger.info("Layout manager initialized successfully")
        except ImportError:
            self.layout_manager = None
            logger.warning("Layout manager initialization failed")

        # Initialize search engine
        try:
            self.search_engine = None  # Will be initialized after tree creation
        except:
            self.search_engine = None
            logger.warning("Search engine initialization failed")

        # Create panel
        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Create toolbar
        self._create_toolbar()

        # Create search panel
        search_panel = self._create_search_panel()
        vbox.Add(search_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Splitter for tree and text display
        self.splitter = wx.SplitterWindow(self.panel)
        self.tree = wx.TreeCtrl(self.splitter)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_item_selected)
        self.text_display = wx.TextCtrl(self.splitter, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL)

        self.splitter.SplitVertically(self.tree, self.text_display)
        self.splitter.SetSashGravity(0.75)
        self.splitter.SetMinimumPaneSize(200)
        vbox.Add(self.splitter, 1, flag=wx.EXPAND | wx.ALL, border=10)

        # Path display (Now editable)
        self.path_text = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE, size=(400, 70))
        self.path_text.Bind(wx.EVT_TEXT, self.on_path_text_changed)
        vbox.Add(self.path_text, flag=wx.EXPAND | wx.ALL, border=10)

        self.panel.SetSizer(vbox)
        self.Show()

        # Set font
        font = self.tree.GetFont()
        font.SetPointSize(12)
        self.tree.SetFont(font)

        # Initialize search engine (now tree is created)
        if TreeSearchEngine:
            try:
                self.search_engine = TreeSearchEngine(self.tree)
                logger.info("Search engine initialized successfully")
            except Exception as e:
                logger.error(f"Search engine initialization failed: {e}")

        # Set drag-and-drop target
        self.SetDropTarget(FileDropTarget(self))

        # Right-click menu setup
        self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_tree_item_right_click)

        # Status bar
        self.CreateStatusBar()
        self.SetStatusText("Ready")  # Ready

        # Load menu
        self._create_menu()

        # Setup accelerators
        self._setup_accelerators()

        logger.info("Main window initialization complete")
    
    def _create_menu(self):
        """Create the menu bar"""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        open_item = file_menu.Append(wx.ID_OPEN, "Open File(&O)\tCtrl+O", "Open File")  # Open file
        file_menu.AppendSeparator()

        # Recent files menu
        recent_menu = wx.Menu()
        self._update_recent_files_menu(recent_menu)
        file_menu.AppendSubMenu(recent_menu, "Recent Files&R)")  # Recent files

        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "Exit&X)\tCtrl+Q", "閫�鍑虹▼搴?)  # Exit program
        menubar.Append(file_menu, "鏂囦欢(&F)")  # File

        # Edit menu
        edit_menu = wx.Menu()
        search_item = edit_menu.Append(wx.ID_FIND, "Search(&F)\tCtrl+F", "Search鑺傜偣")  # Search node
        clear_highlights_item = edit_menu.Append(wx.ID_ANY, "娓呴櫎楂樹寒(&C)\tCtrl+H", "娓呴櫎Search楂樹寒")  # Clear search highlights
        edit_menu.AppendSeparator()
        copy_path_item = edit_menu.Append(wx.ID_COPY, "Copy Path(&P)\tCtrl+C", "Copy Current Path")  # Copy current path
        edit_menu.AppendSeparator()
        export_item = edit_menu.Append(wx.ID_ANY, "Export Current Node(&E)", "Export Current Selected Node")  # Export current selected node
        bookmark_item = edit_menu.Append(wx.ID_ANY, "Add Bookmark�(&B)", "Add Current Node as Bookmark�")  # Add current node as bookmark
        manage_bookmarks_item = edit_menu.Append(wx.ID_ANY, "Manage Bookmarks�(&M)", "Open Bookmark Management Window")  # Open bookmark management window
        menubar.Append(edit_menu, "Edit(&E)")  # Edit

        # View menu
        view_menu = wx.Menu()
        expand_all_item = view_menu.Append(wx.ID_ANY, "Expand All&A)", "Expand All Nodes)  # Expand all nodes
        collapse_all_item = view_menu.Append(wx.ID_ANY, "Collapse All&L)", "Collapse All Nodes)  # Collapse all nodes
        view_menu.AppendSeparator()
        refresh_item = view_menu.Append(wx.ID_REFRESH, "Refresh(&R)\tF5", "Refresh瑙嗗浘")  # Refresh view
        view_menu.AppendSeparator()
        cache_info_item = view_menu.Append(wx.ID_ANY, "Cache Info(&I)", "鏌ョ湅Cache Statistics")  # View cache statistics
        clear_cache_item = view_menu.Append(wx.ID_ANY, "Clear Cache(&C)", "Clear All Cache)  # Clear all cache
        menubar.Append(view_menu, "View(&V)")  # View

        # Help menu
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "About(&A)", "About绋嬪簭")  # About program
        menubar.Append(help_menu, "Help(&H)")  # Help

        # Theme submenu in View menu
        theme_menu = wx.Menu()
        for theme_name in self.theme_manager.get_available_themes():
            item = theme_menu.Append(wx.ID_ANY, theme_name)
            self.Bind(wx.EVT_MENU, lambda e, tn=theme_name: self.on_change_theme(tn), item)
        view_menu.AppendSubMenu(theme_menu, "Theme�(&T)")  # Theme

        # Layout submenu
        layout_menu = wx.Menu()
        if self.layout_manager:
            for layout_name in self.layout_manager.get_available_layouts():
                item = layout_menu.Append(wx.ID_ANY, layout_name)
                self.Bind(wx.EVT_MENU, lambda e, ln=layout_name: self.on_apply_layout(ln), item)
        view_menu.AppendSubMenu(layout_menu, "Layout(&L)")  # Layout

        self.SetMenuBar(menubar)

        # Bind menu events
        self.Bind(wx.EVT_MENU, self.on_load_file, open_item)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), exit_item)
        self.Bind(wx.EVT_MENU, self.on_search, search_item)
        self.Bind(wx.EVT_MENU, self.on_clear_highlights, clear_highlights_item)
        self.Bind(wx.EVT_MENU, self.on_copy_path, copy_path_item)
        self.Bind(wx.EVT_MENU, self.on_export_current, export_item)
        self.Bind(wx.EVT_MENU, self.on_add_bookmark_current, bookmark_item)
        self.Bind(wx.EVT_MENU, self.on_manage_bookmarks, manage_bookmarks_item)
        self.Bind(wx.EVT_MENU, self.on_expand_all, expand_all_item)
        self.Bind(wx.EVT_MENU, self.on_collapse_all, collapse_all_item)
        self.Bind(wx.EVT_MENU, self.on_show_cache_info, cache_info_item)
        self.Bind(wx.EVT_MENU, self.on_clear_cache, clear_cache_item)
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        self.Bind(wx.EVT_MENU, lambda e: self._refresh_view(), refresh_item)
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
    
    def _update_recent_files_menu(self, menu):
        """Update the recent files menu

        Args:
            menu: The recent files menu to update
        """
        # Delete all existing menu items
        while menu.GetMenuItemCount() > 0:
            menu.Delete(menu.FindItemByPosition(0))

        recent_items = self.file_history_manager.get_menu_items()

        if not recent_items:
            item = menu.Append(wx.ID_ANY, "No recent files)  # No recent files
            item.Enable(False)
        else:
            for i, (display_text, file_path, file_type) in enumerate(recent_items):
                # Use wx.ID_ANY to let the system assign unique IDs
                item_id = wx.ID_ANY
                item = menu.Append(item_id, display_text, file_path)
                # Use function factory pattern to create event handlers
                def make_handler(fp, ft):
                    def handler(event):
                        self._open_recent_file(fp, ft)
                    return handler
                self.Bind(wx.EVT_MENU, make_handler(file_path, file_type), item)

    def _open_recent_file(self, file_path, file_type):
        """Open a file from recent files list

        Args:
            file_path: Path to the file
            file_type: Type of file (json/xml)
        """
        if os.path.exists(file_path):
            self.file_path = file_path
            self.current_file_type = file_type or ('json' if file_path.endswith('.json') else 'xml')
            self.load_file_in_thread(file_path)
        else:
            wx.MessageBox(f"File does not exist {file_path}", "Error", wx.OK | wx.ICON_ERROR)  # File does not exist
            self.file_history_manager.remove_file(file_path)
    
    def _create_toolbar(self):
        """Create the toolbar"""
        self.toolbar = self.CreateToolBar(wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)

        # Add toolbar buttons
        open_tool = self.toolbar.AddTool(wx.ID_OPEN, "鎵撳紑", wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR, (16, 16)), shortHelp="Open File")  # Open file
        self.toolbar.AddSeparator()

        search_tool = self.toolbar.AddTool(wx.ID_FIND, "Search", wx.ArtProvider.GetBitmap(wx.ART_FIND, wx.ART_TOOLBAR, (16, 16)), shortHelp="Search")  # Search
        clear_tool = self.toolbar.AddTool(wx.ID_CLEAR, "娓呴櫎", wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_TOOLBAR, (16, 16)), shortHelp="娓呴櫎楂樹寒")  # Clear highlights
        self.toolbar.AddSeparator()

        self.expand_collapse_tool = self.toolbar.AddTool(wx.ID_ANY, "灞曞紑", wx.ArtProvider.GetBitmap(wx.ART_PLUS, wx.ART_TOOLBAR, (16, 16)), shortHelp="灞曞紑/Collapse All Nodes)  # Expand/collapse all nodes
        self.is_expanded = False  # Track expand/collapse state

        self.toolbar.Realize()

        # Bind toolbar events
        self.Bind(wx.EVT_TOOL, self.on_load_file, open_tool)
        self.Bind(wx.EVT_TOOL, self.on_search, search_tool)
        self.Bind(wx.EVT_TOOL, self.on_clear_highlights, clear_tool)
        self.Bind(wx.EVT_TOOL, self.on_toggle_expand_collapse, self.expand_collapse_tool)
    
    def _create_search_panel(self):
        """Create the search panel"""
        panel = wx.Panel(self.panel)
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Search text box
        self.search_text = wx.TextCtrl(panel, size=(200, -1), style=wx.TE_PROCESS_ENTER)
        self.search_text.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.search_text.SetToolTip("杈撳叆Search鍐呭�癸紝鎸夊洖杞︽悳绱�")  # Enter search content and press Enter to search
        sizer.Add(self.search_text, 0, wx.RIGHT, 5)

        # Search button
        self.search_btn = wx.Button(panel, label="Search")  # Search
        self.search_btn.SetMinSize((60, -1))
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        sizer.Add(self.search_btn, 0, wx.RIGHT, 5)

        # Next button
        self.next_btn = wx.Button(panel, label="Next)  # Next
        self.next_btn.SetMinSize((60, -1))
        self.next_btn.Bind(wx.EVT_BUTTON, self.on_next_match)
        sizer.Add(self.next_btn, 0, wx.RIGHT, 5)

        # Previous button
        self.prev_btn = wx.Button(panel, label="Previous)  # Previous
        self.prev_btn.SetMinSize((60, -1))
        self.prev_btn.Bind(wx.EVT_BUTTON, self.on_prev_match)
        sizer.Add(self.prev_btn, 0, wx.RIGHT, 5)

        # Clear highlights button
        self.clear_btn = wx.Button(panel, label="娓呴櫎")  # Clear
        self.clear_btn.SetMinSize((60, -1))
        self.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear_highlights)
        sizer.Add(self.clear_btn, 0)

        # Search options
        self.whole_word = wx.CheckBox(panel, label="Whole Word Match")  # Whole word match
        sizer.Add(self.whole_word, 0, wx.LEFT, 10)

        self.regex_mode = wx.CheckBox(panel, label="Regular Expression)  # Regular expression
        sizer.Add(self.regex_mode, 0, wx.LEFT, 5)

        # Search result label
        self.search_result_label = wx.StaticText(panel, label="")
        self.search_result_label.SetMinSize((80, -1))
        sizer.Add(self.search_result_label, 0, wx.LEFT, 10)

        # Jump text box and button
        self.jump_text = wx.TextCtrl(panel, size=(50, -1), style=wx.TE_PROCESS_ENTER)
        self.jump_text.SetToolTip("Enter result index to jump to?)  # Enter the result index to jump to
        self.jump_text.Bind(wx.EVT_TEXT_ENTER, self.on_jump_to_match)
        sizer.Add(self.jump_text, 0, wx.LEFT, 10)

        self.jump_btn = wx.Button(panel, label="Jump")  # Jump
        self.jump_btn.SetMinSize((60, -1))
        self.jump_btn.Bind(wx.EVT_BUTTON, self.on_jump_to_match)
        sizer.Add(self.jump_btn, 0, wx.LEFT, 5)

        panel.SetSizer(sizer)
        return panel

    def _setup_accelerators(self):
        """Setup keyboard shortcuts"""
        entries = [
            (wx.ACCEL_CTRL, ord('O'), wx.ID_OPEN),
            (wx.ACCEL_CTRL, ord('F'), wx.ID_FIND),
            (wx.ACCEL_CTRL, ord('H'), wx.ID_CLEAR),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
            (wx.ACCEL_CTRL, ord('Q'), wx.ID_EXIT),
            (wx.WXK_F5, wx.ID_REFRESH, wx.ID_REFRESH),
        ]

        self.accelerator_table = wx.AcceleratorTable(entries)
        self.SetAcceleratorTable(self.accelerator_table)

        # Bind accelerator events
        self.Bind(wx.EVT_MENU, self.on_load_file, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.on_search, id=wx.ID_FIND)
        self.Bind(wx.EVT_MENU, self.on_clear_highlights, id=wx.ID_CLEAR)
        self.Bind(wx.EVT_MENU, self.on_copy_path, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, lambda e: self._refresh_view(), id=wx.ID_REFRESH)
    
    # ======== Search Functionality Event Handlers ========

    def on_search(self, event):
        """Handle search event

        Performs a search operation on the tree nodes with the specified query.
        Supports caching, whole word matching, and regular expression modes.

        Args:
            event: The menu event
        """
        if not self.search_engine:
            wx.MessageBox("Search寮曟搸鏈�鍒濆�嬪寲", "Error", wx.OK | wx.ICON_ERROR)  # Search engine not initialized
            return

        query = self.search_text.GetValue().strip()

        if not query:
            wx.MessageBox("Please enter search content, "Information", wx.OK | wx.ICON_INFORMATION)  # Please enter search content
            return

        # Get search options
        whole_word = self.whole_word.GetValue()
        regex_mode = self.regex_mode.GetValue()

        # Build search options dictionary (always case-insensitive)
        search_options = {
            'case_sensitive': False,
            'whole_word': whole_word,
            'regex': regex_mode,
            'search_scope': 'all'
        }

        # Try to get search results from cache
        if self.cache_manager:
            cached_results = self.cache_manager.get_search_results(query, search_options)
            if cached_results is not None:
                logger.info(f"Retrieved search results from cache: {query}")
                # Use cached results
                self.search_engine.results = cached_results
                self.search_engine.current_index = -1
                count = len(cached_results)
            else:
                # Execute search
                count = self.search_engine.search(
                    query,
                    case_sensitive=False,
                    whole_word=whole_word,
                    regex=regex_mode,
                    search_scope="all"
                )
                # Cache search results
                self.cache_manager.set_search_results(query, search_options, self.search_engine.results)
        else:
            # Execute search
            count = self.search_engine.search(
                query,
                case_sensitive=False,
                whole_word=whole_word,
                regex=regex_mode,
                search_scope="all"
            )

        # Update result label
        if count > 0:
            self.search_result_label.SetLabel(f"Found {count} matches?)  # Found X matches
            # Highlight first match
            self.search_engine.next_match()
            self.search_engine.highlight_results()
            # Update current match position display
            self.search_result_label.SetLabel(
                f"{self.search_engine.get_current_index() + 1}/{self.search_engine.get_match_count()}"
            )
        else:
            self.search_result_label.SetLabel("No matches found?)  # No matches found
            wx.MessageBox(f"No matches found? {query}", "Search缁撴灉", wx.OK | wx.ICON_INFORMATION)  # No matches found

        # Save search history
        if self.current_file_path:
            self.path_history_manager.add_path(
                f"Search: {query}",  # Search: query
                self.current_file_path,
                self.current_file_type
            )

        logger.info(f"Search completed: query='{query}', count={count}")
    
    def on_next_match(self, event):
        """Jump to the next match

        Args:
            event: The button event
        """
        if not self.search_engine:
            return

        # If no search results or search query is empty, automatically trigger search
        query = self.search_text.GetValue().strip()
        if not self.search_engine.results or (query and query != self.search_engine.last_query):
            # Automatically execute search
            self.on_search(event)
            return

        self.search_engine.next_match()

        # Update current match information
        current = self.search_engine.get_current_match()
        if current:
            self.search_result_label.SetLabel(
                f"{self.search_engine.get_current_index() + 1}/{self.search_engine.get_match_count()}"
            )

    def on_prev_match(self, event):
        """Jump to the previous match

        Args:
            event: The button event
        """
        if not self.search_engine:
            return

        # If no search results or search query is empty, automatically trigger search
        query = self.search_text.GetValue().strip()
        if not self.search_engine.results or (query and query != self.search_engine.last_query):
            # Automatically execute search
            self.on_search(event)
            return

        self.search_engine.prev_match()

        # Update current match information
        current = self.search_engine.get_current_match()
        if current:
            self.search_result_label.SetLabel(
                f"{self.search_engine.get_current_index() + 1}/{self.search_engine.get_match_count()}"
            )

    def on_jump_to_match(self, event):
        """Jump to match at specified index

        Args:
            event: The button event
        """
        if not self.search_engine:
            return

        # Get index value
        index_str = self.jump_text.GetValue().strip()
        if not index_str:
            return

        try:
            # Try to parse as integer
            index = int(index_str) - 1  # User input is 1-based, convert to 0-based

            # If no search results or search query is empty, automatically trigger search
            query = self.search_text.GetValue().strip()
            if not self.search_engine.results or (query and query != self.search_engine.last_query):
                # Automatically execute search
                self.on_search(event)
                # Try to jump again after search completes
                if self.search_engine.results:
                    if 0 <= index < len(self.search_engine.results):
                        self.search_engine.go_to_match(index)
                        self.search_result_label.SetLabel(
                            f"{self.search_engine.get_current_index() + 1}/{self.search_engine.get_match_count()}"
                        )
                    else:
                        wx.MessageBox(f"绱㈠紩瓒呭嚭鑼冨洿锛屾湁鏁堣寖鍥? 1-{len(self.search_engine.results)}",  # Index out of range
                                    "Error", wx.OK | wx.ICON_ERROR)  # Error
                return

            # Jump to specified index
            if self.search_engine.go_to_match(index):
                self.search_result_label.SetLabel(
                    f"{self.search_engine.get_current_index() + 1}/{self.search_engine.get_match_count()}"
                )
            else:
                wx.MessageBox(f"绱㈠紩瓒呭嚭鑼冨洿锛屾湁鏁堣寖鍥? 1-{len(self.search_engine.results)}",  # Index out of range
                            "Error", wx.OK | wx.ICON_ERROR)  # Error
        except ValueError:
            wx.MessageBox("Please enter a valid numeric index", "Error", wx.OK | wx.ICON_ERROR)  # Please enter a valid numeric index

    def on_clear_highlights(self, event):
        """Clear search highlights

        Args:
            event: The button event
        """
        if self.search_engine:
            self.search_engine.clear_highlights()
            self.search_engine.clear_results()
            self.search_result_label.SetLabel("")
            self.jump_text.SetValue("")
            logger.debug("Search highlights cleared")

    def on_copy_path(self, event):
        """Copy current path to clipboard

        Args:
            event: The menu event
        """
        path = self.path_text.GetValue()
        if path:
            pyperclip.copy(path)
            self.SetStatusText(f"宸插�嶅埗璺�寰? {path}")  # Path copied: path
            logger.debug(f"Path copied: {path}")
        else:
            wx.MessageBox("No path to copy", "Information", wx.OK | wx.ICON_INFORMATION)  # No path to copy

    def on_toggle_expand_collapse(self, event):
        """Toggle expand/collapse all nodes (toolbar button)

        Args:
            event: The tool event
        """
        if self.is_expanded:
            # Currently expanded, perform collapse
            root = self.tree.GetRootItem()
            if root.IsOk():
                self.tree.CollapseAllChildren(root)
            self.expand_collapse_tool.SetShortHelp("Expand All Nodes)  # Expand all nodes
            self.SetStatusText("宸叉姌鍙犳墍鏈夎妭鐐?)  # All nodes collapsed
            logger.debug("All nodes collapsed")
        else:
            # Currently collapsed, perform expand
            self.tree.ExpandAll()
            self.expand_collapse_tool.SetShortHelp("Collapse All Nodes)  # Collapse all nodes
            self.SetStatusText("宸插睍寮�鎵�鏈夎妭鐐?)  # All nodes expanded
            logger.debug("All nodes expanded")

        # Toggle state
        self.is_expanded = not self.is_expanded

    def on_expand_all(self, event):
        """Expand all nodes (menu)

        Args:
            event: The menu event
        """
        self.tree.ExpandAll()
        self.is_expanded = True
        self.expand_collapse_tool.SetShortHelp("Collapse All Nodes)  # Collapse all nodes
        self.SetStatusText("宸插睍寮�鎵�鏈夎妭鐐?)  # All nodes expanded
        logger.debug("All nodes expanded")

    def on_collapse_all(self, event):
        """Collapse all nodes (menu)

        Args:
            event: The menu event
        """
        root = self.tree.GetRootItem()
        if root.IsOk():
            self.tree.CollapseAllChildren(root)
        self.is_expanded = False
        self.expand_collapse_tool.SetShortHelp("Expand All Nodes)  # Expand all nodes
        self.SetStatusText("宸叉姌鍙犳墍鏈夎妭鐐?)  # All nodes collapsed
        logger.debug("All nodes collapsed")

    def _refresh_view(self):
        """Refresh the view"""
        if self.current_data and self.current_file_type:
            self.tree.DeleteAllItems()

            if self.current_file_type == 'xml':
                self.populate_tree_xml(self.current_data)
            else:
                self.populate_tree_json(self.current_data)

            self.display_root_content()
            # Reset expand/collapse button state
            self.is_expanded = False
            self.expand_collapse_tool.SetShortHelp("Expand All Nodes)  # Expand all nodes
            self.SetStatusText("瑙嗗浘宸插埛鏂?)  # View refreshed
            logger.info("View refreshed")

    def on_about(self, event):
        """Show about dialog

        Args:
            event: The menu event
        """
        info = wx.adv.AboutDialogInfo()
        info.SetName("WeeViewer")
        info.SetVersion("1.0")
        info.SetDescription("涓�涓�鐢ㄤ簬蹇�閫熸煡鐪嬪拰鑾峰彇 JSON/XML 鏌ヨ�㈣矾寰勭殑宸ュ�?)  # A tool for quickly viewing and getting JSON/XML query paths
        info.SetCopyright("(C) 2026")
        info.SetWebSite("https://github.com/yourusername/weeviewer")

        wx.adv.AboutBox(info)

    def on_show_cache_info(self, event):
        """Display cache statistics

        Args:
            event: The menu event
        """
        if not self.cache_manager:
            wx.MessageBox("缂撳瓨绠＄悊鍣ㄦ湭鍒濆�嬪�?, "Information", wx.OK | wx.ICON_INFORMATION)  # Cache manager not initialized
            return

        stats = self.cache_manager.get_all_stats()

        info_text = "缂撳瓨缁熻�′俊鎭痋n"  # Cache statistics
        info_text += "="*50 + "\n\n"

        # Node cache
        node_stats = stats['node_cache']
        info_text += f"鑺傜偣缂撳瓨:\n"  # Node cache
        info_text += f"  澶у皬: {node_stats['size']}/{node_stats['max_size']}\n"  # Size
        info_text += f"  鍛戒腑: {node_stats['hits']}\n"  # Hits
        info_text += f"  鏈�鍛戒�? {node_stats['misses']}\n"  # Misses
        info_text += f"  鍛戒腑鐜? {node_stats['hit_rate']:.2%}\n\n"  # Hit rate

        # Search cache
        search_stats = stats['search_cache']
        info_text += f"Search缂撳瓨:\n"  # Search cache
        info_text += f"  澶у皬: {search_stats['size']}/{search_stats['max_size']}\n"
        info_text += f"  鍛戒腑: {search_stats['hits']}\n"
        info_text += f"  鏈�鍛戒�? {search_stats['misses']}\n"
        info_text += f"  鍛戒腑鐜? {search_stats['hit_rate']:.2%}\n\n"

        # Content cache
        content_stats = stats['content_cache']
        info_text += f"鍐呭�圭紦瀛�:\n"  # Content cache
        info_text += f"  澶у皬: {content_stats['size']}/{content_stats['max_size']}\n"
        info_text += f"  鍛戒腑: {content_stats['hits']}\n"
        info_text += f"  鏈�鍛戒�? {content_stats['misses']}\n"
        info_text += f"  鍛戒腑鐜? {content_stats['hit_rate']:.2%}\n"

        wx.MessageBox(info_text, "Cache Statistics", wx.OK | wx.ICON_INFORMATION)

    def on_clear_cache(self, event):
        """Clear all cache

        Args:
            event: The menu event
        """
        if not self.cache_manager:
            wx.MessageBox("缂撳瓨绠＄悊鍣ㄦ湭鍒濆�嬪�?, "Information", wx.OK | wx.ICON_INFORMATION)  # Cache manager not initialized
            return

        result = wx.MessageBox(
            "纭�瀹氳�佹竻绌烘墍鏈夌紦瀛樺悧锛焅n\n杩欏皢娓呴櫎鎵�鏈夌紦瀛樼殑鑺傜偣銆佹悳绱㈢粨鏋滃拰鍐呭�广�?,  # Are you sure you want to clear all cache? This will clear all cached nodes, search results, and content.
            "Confirm Clear Cache",  # Confirm clear cache
            wx.YES_NO | wx.ICON_QUESTION
        )

        if result == wx.YES:
            self.cache_manager.clear_all()
            wx.MessageBox("All cache cleared", "鎴愬姛", wx.OK | wx.ICON_INFORMATION)  # All cache cleared
            logger.info("User cleared all cache")

    def on_apply_layout(self, layout_name: str):
        """Apply layout

        Args:
            layout_name: Layout name
        """
        if not self.layout_manager:
            wx.MessageBox("Layout绠＄悊鍣ㄦ湭鍒濆�嬪�?, "Information", wx.OK | wx.ICON_INFORMATION)  # Layout manager not initialized
            return

        if self.layout_manager.apply_layout(layout_name):
            wx.MessageBox(f"Layout applied: {layout_name}", "鎴愬姛", wx.OK | wx.ICON_INFORMATION)  # Layout applied
        else:
            wx.MessageBox(f"搴旂敤Layout澶辫触: {layout_name}", "Error", wx.OK | wx.ICON_ERROR)  # Failed to apply layout

    def on_change_theme(self, theme_name: str):
        """Change theme

        Args:
            theme_name: Theme name
        """
        if self.theme_manager.set_theme(theme_name):
            # Apply theme to text control
            theme = self.theme_manager.get_current_theme()
            self.text_display.SetBackgroundColour(wx.Colour(theme.background))
            self.text_display.SetForegroundColour(wx.Colour(theme.foreground))

            # Refresh display
            self.text_display.Refresh()

            # Update status bar
            self.SetStatusText(f"Theme樺凡鍒囨�? {theme_name}")  # Theme changed
            logger.info(f"Theme changed: {theme_name}")

    def on_export_current(self, event):
        """Export currently selected node

        Args:
            event: The menu event
        """
        selected = self.tree.GetSelection()
        if selected.IsOk():
            path = self.get_path(selected)
            self.on_export_node(path)
        else:
            wx.MessageBox("璇峰厛閫夋嫨涓�涓�鑺傜�?, "Information", wx.OK | wx.ICON_INFORMATION)  # Please select a node first

    def on_add_bookmark_current(self, event):
        """Add current node as bookmark

        Args:
            event: The menu event
        """
        selected = self.tree.GetSelection()
        if selected.IsOk():
            path = self.get_path(selected)
            self.on_add_bookmark(path)
        else:
            wx.MessageBox("璇峰厛閫夋嫨涓�涓�鑺傜�?, "Information", wx.OK | wx.ICON_INFORMATION)  # Please select a node first

    def on_export_node(self, path: str):
        """Export node

        Args:
            path: Node path
        """
        if not path or not self.current_data:
            wx.MessageBox("No content to export", "Information", wx.OK | wx.ICON_INFORMATION)  # No content to export
            return

        # Create export dialog
        with wx.FileDialog(
            self,
            "Export Node",  # Export node
            wildcard="JSON Files (*.json)|*.json|XML Files (*.xml)|*.xml|HTML Files (*.html)|*.html|CSV Files (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_OK:
                filepath = fileDialog.GetPath()
                file_ext = os.path.splitext(filepath)[1].lower()

                # Get node data
                try:
                    if self.current_file_type == 'json':
                        node_data = self.get_json_value_by_path(self.current_data, path)
                    else:
                        # XML requires special handling
                        node_data = self._get_xml_node_by_path(path)

                    if node_data == "No content found" or node_data is None:
                        wx.MessageBox("鏈�鎵惧埌鑺傜偣鍐呭�?, "Error", wx.OK | wx.ICON_ERROR)  # Node content not found
                        return

                    # Export based on file extension
                    success = False
                    if file_ext == '.json':
                        success = self.export_engine.export_json(node_data, filepath)
                    elif file_ext == '.xml':
                        success = self.export_engine.export_xml(node_data, filepath)
                    elif file_ext == '.html':
                        success = self.export_engine.export_html(node_data, filepath, self.current_file_type)
                    elif file_ext == '.csv':
                        success = self.export_engine.export_csv(node_data, filepath)
                    else:
                        wx.MessageBox("Unsupported file format", "Error", wx.OK | wx.ICON_ERROR)  # Unsupported file format
                        return

                    if success:
                        wx.MessageBox("瀵煎嚭鎴愬姛锛?, "鎴愬姛", wx.OK | wx.ICON_INFORMATION)  # Export successful
                    else:
                        wx.MessageBox("Export failed", "Error", wx.OK | wx.ICON_ERROR)  # Export failed

                except Exception as e:
                    wx.MessageBox(f"Export failed: {e}", "Error", wx.OK | wx.ICON_ERROR)  # Export failed

    def _get_xml_node_by_path(self, path: str):
        """Get XML node by path

        Args:
            path: XML path

        Returns:
            XML node
        """
        try:
            content = self.current_data
            parts = path.split('/')

            for part in parts:
                if not part:
                    continue

                match = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if match:
                    tag = match.group(1)
                    index_str = match.group(2)

                    if index_str:
                        content = self._get_xml_child_by_index(content, tag, index_str)
                    else:
                        children = list(content.findall(tag))
                        if children:
                            content = children[0]

            return content

        except Exception as e:
            logger.error(f"Failed to get XML node: {e}")
            return None

    def on_add_bookmark(self, path: str):
        """Add bookmark

        Args:
            path: Node path
        """
        if not path or not self.file_path:
            wx.MessageBox("璇峰厛閫夋嫨涓�涓�鑺傜�?, "Information", wx.OK | wx.ICON_INFORMATION)  # Please select a node first
            return

        # Create bookmark dialog
        dialog = wx.Dialog(self, title="Add Bookmark�", size=(400, 300))  # Add bookmark

        panel = wx.Panel(dialog)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Bookmark name
        name_label = wx.StaticText(panel, label="Bookmark Name:")  # Bookmark name
        name_ctrl = wx.TextCtrl(panel, value=f"Bookmark_{datetime.now().strftime('%H%M%S')}")
        sizer.Add(name_label, 0, wx.ALL, 5)
        sizer.Add(name_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        # Description
        desc_label = wx.StaticText(panel, label="Description:")  # Description
        desc_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 80))
        sizer.Add(desc_label, 0, wx.ALL, 5)
        sizer.Add(desc_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        # Group
        group_label = wx.StaticText(panel, label="Group:")  # Group
        group_ctrl = wx.ComboBox(panel, choices=self.bookmark_manager.get_groups(), value="Default Group")  # Default group
        sizer.Add(group_label, 0, wx.ALL, 5)
        sizer.Add(group_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(panel, wx.ID_OK, "OK")  # OK
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel")  # Cancel
        btn_sizer.Add(ok_btn, 0, wx.ALL, 5)
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(sizer)

        if dialog.ShowModal() == wx.ID_OK:
            name = name_ctrl.GetValue().strip()
            description = desc_ctrl.GetValue().strip()
            group = group_ctrl.GetValue().strip()

            if not name:
                wx.MessageBox("璇疯緭鍏ヤ功绛惧悕绉?, "Information", wx.OK | wx.ICON_WARNING)  # Please enter bookmark name
                return

            success = self.bookmark_manager.add_bookmark(
                name=name,
                path=path,
                file_path=self.file_path,
                file_type=self.current_file_type,
                description=description,
                group=group
            )
            
            if success:
                wx.MessageBox(f"涔︾�� '{name}' 宸叉坊鍔?, "鎴愬姛", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Add Bookmark惧け璐�", "Error", wx.OK | wx.ICON_ERROR)
        
        dialog.Destroy()
    
    def on_manage_bookmarks(self, event):
        """Manage Bookmarks�"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        if not bookmarks:
            wx.MessageBox("No bookmarks�", "Information", wx.OK | wx.ICON_INFORMATION)
            return
        
        # 鍒涘缓涔︾�剧�＄悊瀵硅瘽妗?        dialog = wx.Dialog(self, title="涔︾�剧�＄悊", size=(600, 400))
        
        panel = wx.Panel(dialog)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 涔︾�惧垪琛�
        list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        list_ctrl.AppendColumn("鍚嶇О", width=150)
        list_ctrl.AppendColumn("璺�寰�", width=200)
        list_ctrl.AppendColumn("Group", width=100)
        list_ctrl.AppendColumn("鍒涘缓鏃堕棿", width=150)
        
        for bookmark in bookmarks:
            index = list_ctrl.InsertItem(list_ctrl.GetItemCount(), bookmark.name)
            list_ctrl.SetItem(index, 1, bookmark.path[:50] + "..." if len(bookmark.path) > 50 else bookmark.path)
            list_ctrl.SetItem(index, 2, bookmark.group)
            list_ctrl.SetItem(index, 3, bookmark.created_time[:19])
        
        sizer.Add(list_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        
        # 鎸夐挳
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        goto_btn = wx.Button(panel, wx.ID_ANY, "Jump鍒颁功绛?)
        delete_btn = wx.Button(panel, wx.ID_ANY, "Delete Bookmark�")
        close_btn = wx.Button(panel, wx.ID_CANCEL, "Close")
        
        btn_sizer.Add(goto_btn, 0, wx.ALL, 5)
        btn_sizer.Add(delete_btn, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(close_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        
        # Jump鍔熻兘
        def on_goto(event):
            selected = list_ctrl.GetFirstSelected()
            if selected != -1:
                bookmark = bookmarks[selected]
                self._goto_bookmark(bookmark)
        
        # 鍒犻櫎鍔熻兘
        def on_delete(event):
            selected = list_ctrl.GetFirstSelected()
            if selected != -1:
                bookmark = bookmarks[selected]
                result = wx.MessageBox(
                    f"纭�瀹氳�佸垹闄や功绛?'{bookmark.name}' 鍚楋紵",
                    "Confirm",
                    wx.YES_NO | wx.ICON_QUESTION
                )
                if result == wx.YES:
                    if self.bookmark_manager.remove_bookmark(bookmark.id):
                        list_ctrl.DeleteItem(selected)
                        wx.MessageBox("涔︾�惧凡鍒犻�?, "鎴愬姛", wx.OK | wx.ICON_INFORMATION)
        
        goto_btn.Bind(wx.EVT_BUTTON, on_goto)
        delete_btn.Bind(wx.EVT_BUTTON, on_delete)
        
        dialog.ShowModal()
        dialog.Destroy()
    
    def _goto_bookmark(self, bookmark: Bookmark):
        """Jump鍒颁功绛?        
        Args:
            bookmark: 涔︾�惧�硅薄
        """
        # 妫�鏌ユ枃浠舵槸鍚﹀瓨鍦?        if not os.path.exists(bookmark.file_path):
            wx.MessageBox(
                f"File does not exist {bookmark.file_path}\n\n璇烽噸鏂版墦寮�鏂囦欢鍚庡啀娆¤�块棶涔︾�俱�?,
                "Error",
                wx.OK | wx.ICON_ERROR
            )
            return
        
        # 濡傛灉鏂囦欢涓嶆槸褰撳墠鏂囦欢锛屾墦寮�瀹?        if self.file_path != bookmark.file_path:
            self.file_path = bookmark.file_path
            self.current_file_type = bookmark.file_type
            self.load_file_in_thread(bookmark.file_path)
            # 绛夊緟鏂囦欢Loading complete
            wx.CallLater(500, lambda: self._navigate_to_path(bookmark.path))
        else:
            self._navigate_to_path(bookmark.path)
    
    def _navigate_to_path(self, path: str):
        """瀵艰埅鍒版寚瀹氳矾寰?        
        Args:
            path: 璺�寰�
        """
        # 杩欓噷闇�瑕佸疄鐜拌矾寰勫�艰埅閫昏緫
        # 鐢变簬璺�寰勫�艰埅姣旇緝澶嶆潅锛岃繖閲岀畝鍖栧�勭�?        self.path_text.SetValue(path)
        self.SetStatusText(f"宸插�艰埅鍒拌矾寰�: {path}")
        logger.info(f"瀵艰埅鍒拌矾寰? {path}")

    def on_path_text_changed(self, event):
        """褰撹矾寰勬枃鏈�妗嗗唴瀹瑰彉鍖栨椂瑙﹀彂鐨勪簨浠�"""
        # 濡傛灉姝ｅ湪鏇存柊璺�寰勶紙鐢� on_item_selected 瑙﹀彂锛夛紝鍒欒烦杩囧�勭�?        if self._is_updating_path:
            return

        try:
            path = self.path_text.GetValue().strip()

            if not path:
                self.text_display.SetValue(ERROR_MESSAGES['enter_valid_path'])
                return

            # 澶勭悊浠?寮�澶寸殑JSONPath
            if path.startswith('$'):
                path = path[1:].strip()  # 鍘绘帀寮�澶寸殑$绗﹀彿

            # 灏濊瘯浠庣紦瀛樿幏鍙栧唴瀹?            cache_key = f"{self.file_path}:{self.current_file_type}:{path}"
            if self.cache_manager:
                cached_content = self.cache_manager.get_content(path, self.current_file_type)
                if cached_content is not None:
                    self.text_display.SetValue(cached_content)
                    # 鍚屾�ユ爲褰㈣�嗗浘
                    if self.current_file_type == 'json':
                        self.sync_tree_with_json_path(path)
                    elif self.current_file_type == 'xml':
                        self.sync_tree_with_xml_path(path)
                    return

            # 鏍规嵁鏂囦欢绫诲瀷瑙ｆ瀽璺�寰�
            if self.current_file_type == 'json':
                # 瑙ｆ瀽 JSONPath
                json_path = path  # 鍙嶅悜瑙ｆ瀽璺�寰�
                content = self.get_json_value_by_path(self.current_data, json_path)  # 鑾峰彇鐩稿簲鍐呭��
                content_str = json.dumps(content, indent=4) if content!= "No content found" else ERROR_MESSAGES['no_content_found']
                self.text_display.SetValue(content_str)
                # 鍚屾�ユ爲褰㈣�嗗浘
                self.sync_tree_with_json_path(path)
                # 缂撳瓨鍐呭��
                if self.cache_manager:
                    self.cache_manager.set_content(path, self.current_file_type, content_str)
            elif self.current_file_type == 'xml':
                # 瑙ｆ瀽 XPath
                parts = path.split('/')  # 淇�澶嶏細浣跨敤姝ｇ‘鐨勫垎闅旂�?                content = self.current_data

                for part in parts:
                    match = re.match(r'(\w+)(?:\[(\d+)\])?', part)  # 鍖归厤鏍囩�惧悕鍜岀储寮�
                    if match:
                        tag = match.group(1)
                        index_str = match.group(2)
                        elements = content.findall(tag)  # 鏌ユ壘鍏冪礌

                        if elements:
                            if index_str:
                                # 浣跨敤缁熶竴鐨勭储寮曡幏鍙栨柟娉?                                content = self._get_xml_child_by_index(content, tag, index_str)
                            else:
                                content = elements[0]  # 榛樿�ら�夋嫨绗�涓�涓�鍏冪�?                        else:
                            raise ValueError(ERROR_MESSAGES['tag_not_found'].format(tag=tag))
                    else:
                        raise ValueError(ERROR_MESSAGES['invalid_path_segment'].format(segment=part))

                if content is not None:
                    xml_string = ET.tostring(content, encoding='unicode', method='xml')
                    self.text_display.SetValue(xml_string)  # 鏄剧ず鍐呭��
                    # 鍚屾�ユ爲褰㈣�嗗浘
                    self.sync_tree_with_xml_path(path)
                    # 缂撳瓨鍐呭��
                    if self.cache_manager:
                        self.cache_manager.set_content(path, self.current_file_type, xml_string)
                else:
                    self.text_display.SetValue(ERROR_MESSAGES['no_content_found'])
        except Exception as e:
            self.text_display.SetValue(f'Error: {str(e)}')
            logger.error(f"璺�寰勮В鏋愰敊璇�: {e}")

    def sync_tree_with_json_path(self, path):
        """鏍规嵁JSON璺�寰勫悓姝ユ爲褰㈣�嗗浘锛屽睍寮�骞惰仛鐒﹀埌瀵瑰簲鑺傜偣"""
        try:
            if not path or not path.strip():
                return

            logger.info(f"=== sync_tree_with_json_path 寮�濮?===")
            logger.info(f"鐩�鏍囪矾寰�: {path}")

            # 璁剧疆鍚屾�ユ爣蹇楋紝闃叉�㈤�掑綊璋冪敤
            self._is_syncing = True

            # 瑙ｆ瀽JSON璺�寰�
            keys = re.findall(r'\["(.*?)"\]|\[(\d+)\]', path)
            logger.info(f"瑙ｆ瀽鐨勯敭: {keys}")
            
            # 璺宠繃Root node"Root"
            if keys and keys[0][0] == "Root":
                keys = keys[1:]

            # 浠庢牴鑺傜偣寮�濮嬫煡鎵?            root_item = self.tree.GetRootItem()
            if not root_item.IsOk():
                self._is_syncing = False
                return

            current_item = root_item
            self.tree.Expand(current_item)

            for key in keys:
                if key[0]:  # 瀛楃�︿覆閿�
                    search_text = f"{key[0]}"
                else:  # 鏁板瓧绱㈠紩
                    search_text = f"[{key[1]}]"
                
                logger.info(f"鏌ユ壘: {search_text}")

                # 鍦ㄥ綋鍓嶈妭鐐圭殑瀛愯妭鐐逛腑鏌ユ壘鍖归厤鐨勮妭鐐?                child_item, cookie = self.tree.GetFirstChild(current_item)
                found = False
                while child_item.IsOk():
                    item_text = self.tree.GetItemText(child_item)
                    # 鎻愬彇鑺傜偣鍚嶇О锛堝幓鎺夊瓙鑺傜偣璁℃暟锛?                    if '[' in item_text:
                        node_name = item_text.split(' [')[0]
                    else:
                        node_name = item_text

                    if node_name == search_text or item_text.startswith(search_text):
                        current_item = child_item
                        self.tree.Expand(current_item)
                        found = True
                        logger.info(f"鎵惧埌鍖归厤鑺傜偣: {item_text}")
                        break
                    child_item, cookie = self.tree.GetNextChild(current_item, cookie)

                if not found:
                    logger.warning(f"No matches found? {search_text}")
                    break

            # 閫変腑骞惰仛鐒︽壘鍒扮殑鑺傜偣
            if current_item != root_item:
                selected_text = self.tree.GetItemText(current_item)
                logger.info(f"閫夋嫨鑺傜偣: {selected_text}")
                self.tree.SelectItem(current_item)
                self.tree.EnsureVisible(current_item)
            else:
                logger.warning("鍋滅暀鍦ㄦ牴鑺傜偣")

            # 娓呴櫎鍚屾�ユ爣蹇�
            self._is_syncing = False
            logger.info(f"=== sync_tree_with_json_path 缁撴潫 ===")
        except Exception as e:
            self._is_syncing = False  # 纭�淇濆湪寮傚父鎯呭喌涓嬩篃娓呴櫎鏍囧�?            logger.error(f"sync_tree_with_json_path Error: {e}")

    def sync_tree_with_xml_path(self, path):
        """鏍规嵁XML璺�寰勫悓姝ユ爲褰㈣�嗗浘锛屽睍寮�骞惰仛鐒﹀埌瀵瑰簲鑺傜偣"""
        try:
            if not path or not path.strip():
                return

            # 璁剧疆鍚屾�ユ爣蹇楋紝闃叉�㈤�掑綊璋冪敤
            self._is_syncing = True

            # 瑙ｆ瀽XML璺�寰�
            parts = path.split('/')
            if not parts:
                self._is_syncing = False
                return

            # 浠庢牴鑺傜偣寮�濮嬫煡鎵?            root_item = self.tree.GetRootItem()
            if not root_item.IsOk():
                self._is_syncing = False
                return

            current_item = root_item
            self.tree.Expand(current_item)

            for part in parts:
                if not part:
                    continue

                # 瑙ｆ瀽鏍囩�惧悕鍜岀储寮�
                match = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if match:
                    tag = match.group(1)
                    index_str = match.group(2)

                    # 鏋勫缓瑕佹悳绱㈢殑鏂囨湰
                    if index_str:
                        search_text = f"{tag} [{index_str}]"
                    else:
                        search_text = tag

                    # 鍦ㄥ綋鍓嶈妭鐐圭殑瀛愯妭鐐逛腑鏌ユ壘鍖归厤鐨勮妭鐐?                    child_item, cookie = self.tree.GetFirstChild(current_item)
                    found = False
                    while child_item.IsOk():
                        item_text = self.tree.GetItemText(child_item)
                        # 鎻愬彇鑺傜偣鍚嶇О锛堝幓鎺夊瓙鑺傜偣璁℃暟锛?                        if '(' in item_text:
                            node_text = item_text.split(' (')[0]
                        else:
                            node_text = item_text

                        if node_text == search_text or item_text.startswith(search_text):
                            current_item = child_item
                            self.tree.Expand(current_item)
                            found = True
                            break
                        child_item, cookie = self.tree.GetNextChild(current_item, cookie)

                    if not found:
                        break

            # 閫変腑骞惰仛鐒︽壘鍒扮殑鑺傜偣
            if current_item != root_item:
                self.tree.SelectItem(current_item)
                self.tree.EnsureVisible(current_item)

            # 娓呴櫎鍚屾�ユ爣蹇�
            self._is_syncing = False
        except Exception as e:
            self._is_syncing = False  # 纭�淇濆湪寮傚父鎯呭喌涓嬩篃娓呴櫎鏍囧�?
    def on_tree_item_right_click(self, event):
        """鍙抽敭鑿滃崟浜嬩欢澶勭悊"""
        item = event.GetItem()
        path = self.get_path(item)

        menu = wx.Menu()
        copy_name_item = menu.Append(wx.ID_ANY, "澶嶅埗閿�鍚�")
        copy_value_item = menu.Append(wx.ID_ANY, "澶嶅埗閿�鍊?)
        menu.AppendSeparator()
        export_item = menu.Append(wx.ID_ANY, "Export Node...")
        bookmark_item = menu.Append(wx.ID_ANY, "Add Bookmark�...")

        self.Bind(wx.EVT_MENU, lambda e: self.copy_key_name(path), copy_name_item)
        self.Bind(wx.EVT_MENU, lambda e: self.copy_key_value(path), copy_value_item)
        self.Bind(wx.EVT_MENU, lambda e: self.on_export_node(path), export_item)
        self.Bind(wx.EVT_MENU, lambda e: self.on_add_bookmark(path), bookmark_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def copy_key_name(self, path):
        """澶嶅埗閿�鍚嶅埌鍓�璐存澘"""
        try:
            if self.current_file_type == 'json':
                # JSON 璺�寰勬牸寮忥細["key1"][0]["key2"]
                last_match = None
                for match in re.finditer(r'\["(.*?)"\]|\[(\d+)\]', path):
                    last_match = match

                if last_match:
                    if last_match.group(1):  # 瀛楃�︿覆閿�
                        key_name = f'["{last_match.group(1)}"]'
                    elif last_match.group(2):  # 鏁板瓧绱㈠紩
                        key_name = f'[{last_match.group(2)}]'
                    else:
                        key_name = path
                else:
                    key_name = path
            elif self.current_file_type == 'xml':
                # XML 璺�寰勬牸寮忥細tag1[1]/tag2[2]/tag3
                parts = path.split('/')
                if parts:
                    last_part = parts[-1]
                    match = re.match(r'(\w+)(?:\[(\d+)\])?', last_part)
                    if match:
                        tag = match.group(1)
                        index_str = match.group(2)
                        if index_str:
                            key_name = f"{tag}[{index_str}]"
                        else:
                            key_name = tag
                    else:
                        key_name = last_part
                else:
                    key_name = path
            else:
                key_name = path

            pyperclip.copy(key_name)
            wx.MessageBox(ERROR_MESSAGES['copy_success'].format(key_name=key_name), "Copy Successful", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(ERROR_MESSAGES['copy_failed'].format(reason=str(e), path=path), "Copy failed", wx.OK | wx.ICON_ERROR)

    def copy_key_value(self, path):
        """澶嶅埗閿�鍊煎埌鍓�璐存�?""
        try:
            if self.current_file_type == 'json':
                value = self.get_json_value_by_path(self.current_data, path)
                if value == "No content found":
                    raise ValueError(ERROR_MESSAGES['node_not_found'])
                content_to_copy = json.dumps(value, indent=4)  # 鏍煎紡鍖栧悗澶嶅埗
            elif self.current_file_type == 'xml':
                # XML 璺�寰勬牸寮忥細tag1[1]/tag2[2]/tag3
                # 妫�鏌ユ槸鍚︿负鏍硅妭鐐癸紙绌鸿矾寰勩�佺┖鐧藉瓧绗︽垨 "root" 瀛楃�︿覆锛�
                if not path or not path.strip() or path.strip() == "root":
                    # 绌鸿矾寰勬垨 "root" 琛ㄧず鏍硅妭鐐癸紝澶嶅埗鏁翠釜 XML 鏍瑰厓绱?                    content_to_copy = ET.tostring(self.current_data, encoding='unicode', method='xml')
                else:
                    # 娓呯悊璺�寰勶紝绉婚櫎鍙�鑳界殑绌虹櫧瀛楃��
                    path = path.strip()
                    content = self.current_data  # 鏍瑰厓绱?                    parts = path.split('/')
                    for part in parts:
                        if not part:
                            continue
                        match = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                        if match:
                            tag = match.group(1)
                            index_str = match.group(2)
                            if index_str:
                                # 浣跨敤缁熶竴鐨勭储寮曡幏鍙栨柟娉?                                content = self._get_xml_child_by_index(content, tag, index_str)
                            else:
                                # 娌℃湁绱㈠紩锛屼娇鐢ㄧ��涓�涓�鍖归厤椤�
                                children = list(content.findall(tag))
                                if not children:
                                    raise ValueError(ERROR_MESSAGES['tag_not_found'].format(tag=tag))
                                content = children[0]
                        else:
                            raise ValueError(ERROR_MESSAGES['invalid_path_segment'].format(segment=part))
                    content_to_copy = ET.tostring(content, encoding='unicode', method='xml')
            else:
                raise ValueError(ERROR_MESSAGES['unknown_file_type'])

            pyperclip.copy(content_to_copy)
            wx.MessageBox(ERROR_MESSAGES['copy_value_success'], "Copy Successful", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(ERROR_MESSAGES['copy_failed'].format(reason=str(e), path=path), "Copy failed", wx.OK | wx.ICON_ERROR)

    def on_load_file(self, event):
        """Open File瀵硅瘽妗嗗苟閫夋嫨鏂囦欢"""
        with wx.FileDialog(self, "Open File", wildcard="XML/JSON Files (*.xml;*.json)|*.xml;*.json",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_OK:
                self.file_path = fileDialog.GetPath()
                self.current_file_type = 'json' if self.file_path.endswith('.json') else 'xml'
                self.load_file_in_thread(self.file_path)

    def load_file_in_thread(self, path):
        """鍦ㄥ悗鍙扮嚎绋嬩腑鍔犺浇鏂囦欢"""
        thread = threading.Thread(target=self._load_file_in_background, args=(path,))
        thread.daemon = True  # 璁剧疆涓哄畧鎶ょ嚎绋嬶紝閬垮厤绋嬪簭鏃犳硶Exit        thread.start()

    def _load_file_in_background(self, path):
        """鍦ㄥ悗鍙扮嚎绋嬩腑瑙ｆ瀽鏂囦欢鏁版嵁"""
        try:
            # 妫�鏌ユ枃浠跺ぇ灏?            file_size = os.path.getsize(path)
            
            if file_size > WARNING_FILE_SIZE:
                error_msg = f"File too large ({file_size/1024/1024:.1f} MB)锛岃秴杩囬檺鍒?({WARNING_FILE_SIZE/1024/1024:.0f} MB)\n\n寤鸿��锛歕n1. Use streaming parser\n2. Split file and load separately\n3. 浣跨敤涓撲笟鐨勫ぇ鏂囦欢鏌ョ湅鍣?
                wx.CallAfter(self._handle_load_error, path, error_msg)
                return
            
            if file_size > MAX_FILE_SIZE:
                # 鏄剧ず璀﹀憡锛屼絾鍏佽�哥户缁�鍔犺浇
                warning_msg = f"鏂囦欢杈冨ぇ ({file_size/1024/1024:.1f} MB)\n\n缁х画鍔犺浇鍙�鑳藉崰鐢ㄥぇ閲忓唴瀛橈紝寤鸿��璋ㄦ厧鎿嶄綔銆俓n\n鏄�鍚︾户缁�锛?
                wx.CallAfter(self._confirm_large_file_load, path, warning_msg)
                return
            
            file_type = 'json' if path.endswith('.json') else 'xml'
            data = None
            error_msg = None

            if file_type == 'xml':
                tree = ET.parse(path)
                data = tree.getroot()
            elif file_type == 'json':
                with open(path, 'r', encoding='utf-8-sig') as file:
                    json_str = file.read()
                    data = json.loads(json_str)

            # 鍦ㄤ富绾跨▼涓�鏇存柊UI鍜岀姸鎬?            wx.CallAfter(self._update_after_load, path, file_type, data)
        except Exception as e:
            error_msg = str(e)
            wx.CallAfter(self._handle_load_error, path, error_msg)

    def _confirm_large_file_load(self, path, warning_msg):
        """纭�璁ゆ槸鍚﹀姞杞藉ぇ鏂囦�?""
        result = wx.MessageBox(warning_msg, "鏂囦欢澶у皬璀﹀憡", wx.YES_NO | wx.ICON_WARNING)
        if result == wx.YES:
            # 鐢ㄦ埛纭�璁ょ户缁�鍔犺浇
            thread = threading.Thread(target=self._load_file_data_only, args=(path,))
            thread.daemon = True
            thread.start()

    def _load_file_data_only(self, path):
        """浠呭姞杞芥暟鎹�锛堢敤浜庡ぇ鏂囦欢纭�璁ゅ悗锛?""
        try:
            file_type = 'json' if path.endswith('.json') else 'xml'
            data = None

            if file_type == 'xml':
                tree = ET.parse(path)
                data = tree.getroot()
            elif file_type == 'json':
                with open(path, 'r', encoding='utf-8-sig') as file:
                    json_str = file.read()
                    data = json.loads(json_str)

            wx.CallAfter(self._update_after_load, path, file_type, data)
        except Exception as e:
            wx.CallAfter(self._handle_load_error, path, str(e))

    def _update_after_load(self, path, file_type, data):
        """鍦ㄤ富绾跨▼涓�鏇存柊UI鍜岀姸鎬侊紙绾跨▼瀹夊叏锛?""
        try:
            self.tree.DeleteAllItems()
            self.text_display.SetValue(ERROR_MESSAGES['loading_complete'])
            self.SetTitle(f'WeeViewer - {os.path.basename(path)}')
            
            # 鍦ㄤ富绾跨▼涓�鏇存柊鍏变韩鍙橀�?            self.file_path = path
            self.current_file_type = file_type
            self.current_data = data
            
            # 娓呴櫎Search缁撴灉
            if self.search_engine:
                self.search_engine.clear_results()
                self.search_engine.clear_highlights()
                self.search_result_label.SetLabel("")
            
            if file_type == 'xml':
                self.populate_tree_xml(data)
            else:
                self.populate_tree_json(data)
            self.display_root_content()
            
            # 娣诲姞鍒版枃浠跺巻鍙?            self.file_history_manager.add_file(path, file_type)

            # 閲嶇疆灞曞紑/鎶樺彔鎸夐挳鐘舵�?            self.is_expanded = False
            self.expand_collapse_tool.SetShortHelp("Expand All Nodes)

            # 鏇存柊鏈�杩戞枃浠惰彍鍗?            menubar = self.GetMenuBar()
            if menubar:
                file_menu = menubar.GetMenu(0)
                if file_menu:
                    menu_items = file_menu.GetMenuItems()
                    if len(menu_items) > 1:
                        recent_menu = menu_items[1].GetSubMenu()
                        if recent_menu:
                            self._update_recent_files_menu(recent_menu)
            
            self.SetStatusText(f"宸插姞杞? {os.path.basename(path)}")
            logger.info(f"鏂囦欢鍔犺浇鎴愬姛: {path}")
        except Exception as e:
            wx.MessageBox(ERROR_MESSAGES['ui_update_error'].format(reason=str(e)), "Error", wx.OK | wx.ICON_ERROR)

    def _handle_load_error(self, path, error_msg):
        """澶勭悊鏂囦欢鍔犺浇Error"""
        self.tree.DeleteAllItems()
        self.text_display.SetValue(ERROR_MESSAGES['loading_failed'])
        wx.MessageBox(ERROR_MESSAGES['file_load_error'].format(reason=error_msg, path=path), "Error", wx.OK | wx.ICON_ERROR)

    def load_file(self, path):
        """鍔犺浇鏂囦欢骞惰В鏋愶紙淇濈暀鍏煎�规�э紝宸插純鐢�锛�"""
        wx.CallAfter(self.tree.DeleteAllItems)
        wx.CallAfter(self.text_display.SetValue, "Loading file, please wait...")
        wx.CallAfter(self.SetTitle, f'WeeViewer - {path}')

        try:
            if path.endswith('.xml'):
                self.current_file_type = 'xml'
                tree = ET.parse(path)
                self.current_data = tree.getroot()
                wx.CallAfter(self.populate_tree_xml, self.current_data)
                wx.CallAfter(self.display_root_content)
            elif path.endswith('.json'):
                self.current_file_type = 'json'
                with open(path, 'r', encoding='utf-8-sig') as file:
                    json_str = file.read()
                    self.current_data = json.loads(json_str)
                    wx.CallAfter(self.populate_tree_json, self.current_data)
                    wx.CallAfter(self.display_root_content)
        except Exception as e:
            wx.CallAfter(wx.MessageBox, f'Error loading file: {e}', "Error", wx.OK | wx.ICON_ERROR)

    def populate_tree_xml(self, root, parent=None, path=''):  # Changed initial path to ''
        """Recursively populate XML data into TreeCtrl, showing index only for multiple sibling nodes

        Args:
            root: XML element to populate
            parent: Parent tree item
            path: Current path
        """
        if parent is None:
            parent = self.tree.AddRoot('root')  # Root node displays as 'root'

        # Step 1: Count occurrences of each tag
        tag_counts = {}
        for child in root:
            tag = child.tag
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Step 2: Traverse and create nodes, adding index only for multiple siblings
        tag_indices = {}  # Record current index for each tag
        for child in root:
            tag = child.tag

            # Update current tag index
            tag_indices[tag] = tag_indices.get(tag, 0) + 1
            current_index = tag_indices[tag]

            # Only add index when there are multiple siblings with same name
            if tag_counts[tag] > 1:
                item_text = f"{tag} [{current_index}] ({len(child)})" if len(child) > 1 else f"{tag} [{current_index}]"
                item_path = path + f"/{tag}[{current_index}]"
            else:
                item_text = f"{tag} ({len(child)})" if len(child) > 1 else tag
                item_path = path + f"/{tag}"

            item = self.tree.AppendItem(parent, item_text)
            self.populate_tree_xml(child, item, item_path)

    def populate_tree_json(self, data, parent=None, path='Root'):
        """Recursively populate JSON data into TreeCtrl

        Args:
            data: JSON data to populate
            parent: Parent tree item
            path: Current path
        """
        if parent is None:
            parent = self.tree.AddRoot(path)

        if isinstance(data, dict):
            for key, value in data.items():
                child_count = self.count_children(value)
                if child_count > 0:
                    item = self.tree.AppendItem(parent, f"{key} [{child_count}]")
                else:
                    item = self.tree.AppendItem(parent, f"{key}")
                self.populate_tree_json(value, item, path + '.' + key)
        elif isinstance(data, list):
            for index, item in enumerate(data):
                child_count = self.count_children(item)
                if child_count > 0:
                    item_text = f"[{index}] [{child_count}]"
                else:
                    item_text = f"[{index}]"
                item_node = self.tree.AppendItem(parent, item_text)
                self.populate_tree_json(item, item_node, path + f'[{index}]')

    def count_children(self, data):
        """Count number of child elements for a node

        Args:
            data: Data to count

        Returns:
            Number of children
        """
        if isinstance(data, dict):
            return len(data)
        elif isinstance(data, list):
            return len(data)
        return 0

    def on_item_selected(self, event):
        """Handle tree item selection event

        Args:
            event: Tree selection event
        """
        # Skip event handling if syncing (prevent recursion)
        if self._is_syncing:
            logger.info("=== on_item_selected skipped (syncing) ===")
            return

        selected_item = event.GetItem()

        logger.info(f"=== on_item_selected started ===")
        logger.info(f"Selected node: {self.tree.GetItemText(selected_item)}")

        # Get parent of current selected item
        parent_item = self.tree.GetItemParent(selected_item)

        # Collapse all other items under same parent
        if parent_item.IsOk():
            # Traverse all children of current parent
            child_item, cookie = self.tree.GetFirstChild(parent_item)
            while child_item.IsOk():
                if child_item != selected_item:  # If it's another sibling node
                    if self.tree.IsExpanded(child_item):  # If node is expanded, collapse it
                        self.tree.Collapse(child_item)
                child_item, cookie = self.tree.GetNextChild(parent_item, cookie)

        # Expand current selected node
        if not self.tree.IsExpanded(selected_item):
            self.tree.Expand(selected_item)

        # Display node path and content
        path = self.get_path(selected_item)
        logger.info(f"Generated path: {path}")

        # Set flag to prevent triggering path text change event
        self._is_updating_path = True
        self.path_text.SetValue(path)
        self._is_updating_path = False

        if self.current_file_type == 'json':
            self.display_json_content(path)
        else:
            self.display_xml_content(path)

        # Add to path history
        if path and self.file_path:
            self.path_history_manager.add_path(path, self.file_path, self.current_file_type)

        # Update status bar
        self.SetStatusText(f"璺�寰�: {path}")  # Path: path
        logger.info(f"=== on_item_selected ended ===")

    def generate_xml_path(self, item):
        """Generate accurate XPath expression for XML node, avoiding redundant indices

        Args:
            item: Tree item

        Returns:
            XPath string
        """
        path_parts = []
        while item.IsOk():
            part_text = self.tree.GetItemText(item)
            tag = part_text.split(' [')[0]
            index_match = re.search(r'\[(\d+)\]', part_text)
            index = index_match.group(1) if index_match else ""
            if index:
                path_parts.append(f"{tag}[{index}]")
            else:
                path_parts.append(tag)
            parent_item = self.tree.GetItemParent(item)
            item = parent_item

        return "/".join(reversed(path_parts))

    def get_path(self, item):
        """Get path for selected node

        Args:
            item: Tree item

        Returns:
            Path string (XPath or JSONPath)
        """
        path_parts = []
        current_item = item
        while current_item.IsOk():
            part_text = self.tree.GetItemText(current_item)
            path_parts.append(part_text)
            current_item = self.tree.GetItemParent(current_item)

        # 妫�鏌ユ槸鍚︿负Root node        # 瀵逛簬 XML锛氭牴鑺傜偣鏄剧ず涓?'root'锛屽�逛�?JSON锛氭牴鑺傜偣鏄剧ず涓?'Root'
        if len(path_parts) == 1:
            # 鍙�鏈変竴涓�鑺傜偣锛岃�存槑鏄�鏍硅妭鐐�
            return ""

        # 瀵逛簬 XML 鏂囦欢锛屾瀯寤?XPath 鏍煎紡鐨勮矾寰?        if self.current_file_type == 'xml':
            # path_parts 鏄�浠庡彾瀛愯妭鐐瑰埌鏍硅妭鐐圭殑椤哄�?            # path_parts[0] 鏄�鍙跺瓙鑺傜偣锛宲ath_parts[-1] 鏄�铏氭嫙鏍硅妭鐐� 'root'
            # 妫�鏌ユ渶鍚庝竴涓�鍏冪礌鏄�鍚︿负铏氭嫙Root node'root'
            if path_parts and path_parts[-1] == 'root':
                # 鍘绘帀铏氭嫙鏍硅妭鐐癸紝鍙�鍙栧疄闄� XML 璺�寰勯儴鍒�
                xml_path_parts = path_parts[:-1]
            else:
                xml_path_parts = path_parts

            # 濡傛灉鍘绘帀铏氭嫙鏍硅妭鐐瑰悗涓虹┖锛岃�存槑鐐瑰嚮鐨勫氨鏄�铏氭嫙Root node            if not xml_path_parts:
                return ""

            xml_path = []
            for part in reversed(xml_path_parts):  # 浠庣埗鑺傜偣鍒板瓙鑺傜偣鐨勯『搴?                # 浠庢樉绀烘枃鏈�涓�鎻愬彇鏍囩�惧悕鍜岀储寮曪紝渚嬪�傦細tag [1] (3) -> tag[1]
                match = re.match(r'(\w+)(?:\s*\[(\d+)\])?', part)
                if match:
                    tag = match.group(1)
                    index = match.group(2)
                    if index:
                        xml_path.append(f"{tag}[{index}]")
                    else:
                        xml_path.append(tag)
            return "/".join(xml_path)
        else:
            # 瀵逛簬 JSON 鏂囦欢锛屾瀯寤?JSON 璺�寰�
            # 妫�鏌ユ槸鍚︾偣鍑讳簡鏄剧ず涓?'Root' 鐨勬牴鑺傜偣
            if path_parts and path_parts[0] == 'Root':
                if len(path_parts) == 1:
                    return ""

            json_path = []
            for part in reversed(path_parts):  # 浠庢牴鑺傜偣鍒板彾瀛愯妭鐐圭殑椤哄簭
                # 璺宠繃Root node'Root'
                if part == 'Root':
                    continue
                # 妫�鏌ユ槸鍚︿负鏁扮粍绱㈠紩鑺傜偣锛歔1] 鎴?[1] [3]
                array_match = re.match(r'^\[(\d+)\](?:\s*\[\d+\])?$', part)
                if array_match:
                    index = array_match.group(1)
                    json_path.append(f"[{index}]")
                else:
                    # 绉婚櫎瀛愯妭鐐硅�℃暟锛屼緥濡傦細key [3] -> key
                    clean_part = part.split(' [')[0]
                    json_path.append(f'["{clean_part}"]')
            return ''.join(json_path)

    def display_json_content(self, path):
        try:
            data = self.current_data
            content = self.get_json_value_by_path(data, path)
            
            # 妫�鏌ユ槸鍚﹁繑鍥炰簡Error娑堟伅
            if content == "No content found":
                self.text_display.SetValue(ERROR_MESSAGES['no_content_found'])
            else:
                self.text_display.SetValue(json.dumps(content, indent=4))
        except Exception as e:
            self.text_display.SetValue(f'鑾峰彇鍐呭�规椂鍑洪�? {e}')

    def display_xml_content(self, path):
        try:
            content = self.current_data  # 鏍瑰厓绱?
            # 瑙ｆ瀽 XPath 鏍煎紡鐨勮矾寰勶紝渚嬪�傦細tag1[1]/tag2[2]/tag3
            parts = path.split('/')
            for part in parts:
                if not part:
                    continue

                # 瑙ｆ瀽鏍囩�惧悕鍜岀储寮曪紝渚嬪�傦細tag[1] -> tag, 1
                match = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if match:
                    tag = match.group(1)
                    index_str = match.group(2)

                    if index_str:
                        # 浣跨敤缁熶竴鐨勭储寮曡幏鍙栨柟娉?                        content = self._get_xml_child_by_index(content, tag, index_str)
                    else:
                        # 娌℃湁绱㈠紩锛屼娇鐢ㄧ��涓�涓�鍖归厤椤�
                        children = list(content.findall(tag))
                        if not children:
                            raise ValueError(ERROR_MESSAGES['tag_not_found'].format(tag=tag))
                        content = children[0]
                else:
                    raise ValueError(ERROR_MESSAGES['invalid_path_segment'].format(segment=part))

            # 濡傛灉鍐呭�瑰瓨鍦�锛岃浆鍖栦负 XML 瀛楃�︿覆骞舵樉绀�
            if content is not None:
                xml_string = ET.tostring(content, encoding='unicode', method='xml')
                self.text_display.SetValue(xml_string)
            else:
                self.text_display.SetValue(ERROR_MESSAGES['no_content_found'])
        except Exception as e:
            self.text_display.SetValue(f"鑾峰彇 XML 鍐呭�规椂鍑洪�? {e}")

    def get_json_value_by_path(self, data, path):
        try:
            keys = re.findall(r'\["(.*?)"\]|\[(\d+)\]', path)
            content = data

            # 璺宠繃璺�寰勫紑澶寸殑 "Root" 閿�锛堝�傛灉瀛樺湪锛?            if keys and keys[0][0] == "Root":
                keys = keys[1:]

            for key in keys:
                if key[0]:
                    content = content[key[0]]
                else:
                    content = content[int(key[1])]
            return content
        except Exception:
            return "No content found"

    def _get_xml_child_by_index(self, parent, tag, index_str):
        """缁熶竴澶勭悊 XML 瀛愬厓绱犵储寮曡幏鍙?        
        Args:
            parent: 鐖跺厓绱?            tag: 鏍囩�惧�?            index_str: 绱㈠紩瀛楃�︿覆锛圶Path 鏍煎紡锛屼粠 1 寮�濮嬶級
            
        Returns:
            鍖归厤鐨勫瓙鍏冪礌
            
        Raises:
            ValueError: 濡傛灉绱㈠紩鏃犳晥鎴栬秴鍑鸿寖鍥?        """
        try:
            # 妫�鏌ョ储寮曟槸鍚︿负鏈夋晥鏁板瓧
            if not index_str or not index_str.strip():
                raise ValueError("绱㈠紩涓嶈兘涓虹┖")
            
            index = int(index_str.strip())
            
            # XPath 绱㈠紩浠?1 寮�濮嬶紝杞�鎹�涓?0-based
            if index < 1:
                raise ValueError(f"Index must be >= 1锛圶Path 鏍囧噯锛夛紝褰撳墠: {index}")
            
            # 鏌ユ壘鎵�鏈夊尮閰嶇殑鏍囩��
            children = list(parent.findall(tag))
            
            if not children:
                raise ValueError(f"鍦ㄥ綋鍓嶈妭鐐逛腑Tag not found�?'{tag}'")
            
            # 杞�鎹�涓?0-based 绱㈠紩
            zero_based_index = index - 1
            
            if zero_based_index >= len(children):
                raise ValueError(
                    f"Index {index} out of range锛堟爣绛?'{tag}' 鍏辨湁 {len(children)} 涓�瀛愬厓绱狅紝鏈夋晥鑼冨�? 1-{len(children)}锛?
                )
            
            return children[zero_based_index]
            
        except ValueError as e:
            # 閲嶆柊鎶涘嚭宸叉牸寮忓寲鐨勯敊璇?            raise ValueError(f"鏃犳晥鐨勭储寮?'{index_str}': {e}")
        except Exception as e:
            raise ValueError(f"澶勭悊绱㈠紩鏃跺嚭閿? {e}")

    def display_root_content(self):
        """鏄剧ず鏍硅妭鐐圭殑鍐呭��"""
        try:
            if self.current_file_type == 'json':
                # 鏄剧ず鏁翠釜 JSON 鏁版嵁
                self.text_display.SetValue(json.dumps(self.current_data, indent=4))
            elif self.current_file_type == 'xml':
                # 鏄剧ず XML 鏍瑰厓绱?                xml_string = ET.tostring(self.current_data, encoding='unicode', method='xml')
                self.text_display.SetValue(xml_string)
        except Exception as e:
            self.text_display.SetValue(f'鏄剧ず鍐呭�规椂鍑洪�? {e}')


class FileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame

    def OnDropFiles(self, x, y, filenames):
        for filename in filenames:
            if filename.endswith('.xml') or filename.endswith('.json'):
                self.frame.load_file_in_thread(filename)
                break
        return True


# ======== Week 1 Development: Search Functionality + History Records ========

# Import created modules
import sys
import os
from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime
from collections import OrderedDict
from dataclasses import dataclass
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('viewer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import configuration manager
try:
    from config_manager import ConfigManager
except ImportError:
    logger.warning("Cannot import ConfigManager, using default configuration")
    ConfigManager = None

# Import search engine
try:
    from search_engine import TreeSearchEngine, SearchResult
except ImportError:
    logger.warning("Cannot import TreeSearchEngine, search functionality will be unavailable")
    TreeSearchEngine = None
    SearchResult = None


# ======== History Managers ========



class FileHistoryManager:
    """File history record manager

    Manages the history of opened files, tracking access times and counts.
    """

    DEFAULT_MAX_HISTORY = 10
    CONFIG_KEY = "file_history"

    def __init__(self, config_manager: Any = None, max_history: Optional[int] = None):
        """Initialize the file history manager

        Args:
            config_manager: Configuration manager instance
            max_history: Maximum number of history entries to keep
        """
        self.config = config_manager
        self.max_history = max_history or (config_manager.get('history.max_file_history', self.DEFAULT_MAX_HISTORY) if config_manager else self.DEFAULT_MAX_HISTORY)
        self.history: OrderedDict[str, FileHistoryItem] = OrderedDict()
        self._load_history()
        logger.info(f"FileHistoryManager initialized, max history count: {self.max_history}")

    def _load_history(self) -> None:
        """Load history from configuration"""
        try:
            if self.config:
                enable_history = self.config.get('history.enable_file_history', True)
                if not enable_history:
                    logger.info("File history feature disabled")
                    return

                history_data = self.config.get(self.CONFIG_KEY, [])
                for item_data in history_data:
                    if isinstance(item_data, dict):
                        file_path = item_data.get('file_path', '')
                        if file_path and os.path.exists(file_path):
                            history_item = FileHistoryItem(
                                file_path=file_path,
                                access_time=item_data.get('access_time', ''),
                                access_count=item_data.get('access_count', 1),
                                file_type=item_data.get('file_type', '')
                            )
                            self.history[file_path] = history_item
                logger.info(f"Loaded {len(self.history)} file history entries")
        except Exception as e:
            logger.error(f"Failed to load file history: {e}")

    def _save_history(self) -> None:
        """Save history to configuration"""
        try:
            if self.config:
                enable_history = self.config.get('history.enable_file_history', True)
                if not enable_history:
                    return

                history_data = []
                for item in self.history.values():
                    history_data.append({
                        'file_path': item.file_path,
                        'access_time': item.access_time,
                        'access_count': item.access_count,
                        'file_type': item.file_type
                    })
                self.config.set(self.CONFIG_KEY, history_data)
                self.config.save()
                logger.debug(f"Saved {len(history_data)} file history entries")
        except Exception as e:
            logger.error(f"Failed to save file history: {e}")

    def add_file(self, file_path: str, file_type: str = "") -> bool:
        """Add a file to history

        Args:
            file_path: Path to the file
            file_type: Type of file (json/xml)

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = os.path.normpath(file_path)
            if not os.path.exists(file_path):
                logger.warning(f"File does not exist, not adding to history: {file_path}")
                return False

            if file_path in self.history:
                item = self.history.pop(file_path)
                item.access_time = datetime.now().isoformat()
                item.access_count += 1
                item.file_type = file_type or item.file_type
                self.history[file_path] = item
            else:
                item = FileHistoryItem(
                    file_path=file_path,
                    access_time=datetime.now().isoformat(),
                    access_count=1,
                    file_type=file_type
                )
                self.history[file_path] = item
                while len(self.history) > self.max_history:
                    oldest_key = next(iter(self.history))
                    self.history.pop(oldest_key)

            self._save_history()
            logger.debug(f"File added to history: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to add file to history: {e}")
            return False

    def remove_file(self, file_path: str) -> bool:
        """Remove a file from history

        Args:
            file_path: Path to the file

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = os.path.normpath(file_path)
            if file_path in self.history:
                del self.history[file_path]
                self._save_history()
                logger.debug(f"File removed from history: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove file from history: {e}")
            return False

    def clear_history(self) -> bool:
        """Clear all history entries

        Returns:
            True if successful, False otherwise
        """
        try:
            self.history.clear()
            self._save_history()
            logger.info("File history cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear file history: {e}")
            return False

    def get_history(self) -> List[FileHistoryItem]:
        """Get history entries, most recent first

        Returns:
            List of history items
        """
        return list(reversed(self.history.values()))

    def get_menu_items(self) -> List[Tuple[str, str, str]]:
        """Get history items formatted for menu display

        Returns:
            List of tuples (display_text, file_path, file_type)
        """
        items = []
        for i, item in enumerate(self.get_history()):
            filename = os.path.basename(item.file_path)
            display_text = f"{i+1}. {filename}"
            items.append((display_text, item.file_path, item.file_type))
        return items

    def get_recent_files(self, count: int = 5) -> List[str]:
        """Get most recent file paths

        Args:
            count: Number of files to return

        Returns:
            List of file paths
        """
        recent = self.get_history()[:count]
        return [item.file_path for item in recent]

    def contains(self, file_path: str) -> bool:
        """Check if file is in history

        Args:
            file_path: Path to the file

        Returns:
            True if file exists in history
        """
        file_path = os.path.normpath(file_path)
        return file_path in self.history

    def get_access_count(self, file_path: str) -> int:
        """Get access count for a file

        Args:
            file_path: Path to the file

        Returns:
            Number of times file was accessed, 0 if not found
        """
        file_path = os.path.normpath(file_path)
        if file_path in self.history:
            return self.history[file_path].access_count
        return 0


class PathHistoryManager:
    """Path history record manager

    Manages the history of accessed paths (XPath/JSONPath),
    tracking access times and counts.
    """

    DEFAULT_MAX_HISTORY = 20
    CONFIG_KEY = "path_history"

    def __init__(self, config_manager: Any = None, max_history: Optional[int] = None):
        """Initialize the path history manager

        Args:
            config_manager: Configuration manager instance
            max_history: Maximum number of history entries to keep
        """
        self.config = config_manager
        self.max_history = max_history or (config_manager.get('history.max_path_history', self.DEFAULT_MAX_HISTORY) if config_manager else self.DEFAULT_MAX_HISTORY)
        self.history: OrderedDict[str, PathHistoryItem] = OrderedDict()
        self._load_history()
        logger.info(f"PathHistoryManager initialized, max history count: {self.max_history}")

    def _load_history(self) -> None:
        """Load history from configuration"""
        try:
            if self.config:
                enable_history = self.config.get('history.enable_path_history', True)
                if not enable_history:
                    logger.info("Path history feature disabled")
                    return

                history_data = self.config.get(self.CONFIG_KEY, [])
                for item_data in history_data:
                    if isinstance(item_data, dict):
                        path = item_data.get('path', '')
                        if path:
                            history_item = PathHistoryItem(
                                path=path,
                                access_time=item_data.get('access_time', ''),
                                access_count=item_data.get('access_count', 1),
                                file_path=item_data.get('file_path', ''),
                                file_type=item_data.get('file_type', '')
                            )
                            self.history[path] = history_item
                logger.info(f"Loaded {len(self.history)} path history entries")
        except Exception as e:
            logger.error(f"Failed to load path history: {e}")

    def _save_history(self) -> None:
        """Save history to configuration"""
        try:
            if self.config:
                enable_history = self.config.get('history.enable_path_history', True)
                if not enable_history:
                    return

                history_data = []
                for item in self.history.values():
                    history_data.append({
                        'path': item.path,
                        'access_time': item.access_time,
                        'access_count': item.access_count,
                        'file_path': item.file_path,
                        'file_type': item.file_type
                    })
                self.config.set(self.CONFIG_KEY, history_data)
                self.config.save()
                logger.debug(f"Saved {len(history_data)} path history entries")
        except Exception as e:
            logger.error(f"Failed to save path history: {e}")

    def add_path(self, path: str, file_path: str = "", file_type: str = "") -> bool:
        """Add a path to history

        Args:
            path: Path string (XPath or JSONPath)
            file_path: Associated file path
            file_type: Type of file (json/xml)

        Returns:
            True if successful, False otherwise
        """
        try:
            if path in self.history:
                item = self.history.pop(path)
                item.access_time = datetime.now().isoformat()
                item.access_count += 1
                item.file_path = file_path or item.file_path
                item.file_type = file_type or item.file_type
                self.history[path] = item
            else:
                item = PathHistoryItem(
                    path=path,
                    access_time=datetime.now().isoformat(),
                    access_count=1,
                    file_path=file_path,
                    file_type=file_type
                )
                self.history[path] = item
                while len(self.history) > self.max_history:
                    oldest_key = next(iter(self.history))
                    self.history.pop(oldest_key)

            self._save_history()
            logger.debug(f"Path added to history: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to add path to history: {e}")
            return False

    def remove_path(self, path: str) -> bool:
        """Remove a path from history

        Args:
            path: Path string

        Returns:
            True if successful, False otherwise
        """
        try:
            if path in self.history:
                del self.history[path]
                self._save_history()
                logger.debug(f"Path removed from history: {path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove path from history: {e}")
            return False

    def clear_history(self) -> bool:
        """Clear all history entries

        Returns:
            True if successful, False otherwise
        """
        try:
            self.history.clear()
            self._save_history()
            logger.info("Path history cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear path history: {e}")
            return False

    def get_history(self) -> List[PathHistoryItem]:
        """Get history entries, most recent first

        Returns:
            List of history items
        """
        return list(reversed(self.history.values()))

    def get_recent_paths(self, count: int = 10) -> List[str]:
        """Get most recent paths

        Args:
            count: Number of paths to return

        Returns:
            List of path strings
        """
        recent = self.get_history()[:count]
        return [item.path for item in recent]


# ======== Week 2 Development: Syntax Highlighting + Theme Support ========



class JSONHighlighter:
    """JSON syntax highlighter

    Provides tokenization and highlighting for JSON content.
    """

    def __init__(self):
        """Initialize the JSON highlighter with regex patterns"""
        self.patterns = [
            (TokenType.JSON_STRING, r'"(?:\\"|[^\\"])*"'),
            (TokenType.JSON_NUMBER, r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?'),
            (TokenType.JSON_BOOLEAN, r'\b(?:true|false)\b'),
            (TokenType.JSON_NULL, r'\bnull\b'),
            (TokenType.JSON_OBJECT_START, r'\{'),
            (TokenType.JSON_OBJECT_END, r'\}'),
            (TokenType.JSON_ARRAY_START, r'\['),
            (TokenType.JSON_ARRAY_END, r'\]'),
            (TokenType.WHITESPACE, r'\s+'),
        ]
        self.compiled_patterns = [(t, re.compile(p)) for t, p in self.patterns]

    def highlight(self, text: str) -> List[Token]:
        """Highlight JSON text by tokenizing it

        Args:
            text: JSON text to highlight

        Returns:
            List of tokens
        """
        if not text:
            return []
        tokens = []
        pos = 0
        while pos < len(text):
            matched = False
            for token_type, pattern in self.compiled_patterns:
                match = pattern.match(text, pos)
                if match:
                    tokens.append(Token(token_type, match.group(), pos, match.end()))
                    pos = match.end()
                    matched = True
                    break
            if not matched:
                tokens.append(Token(TokenType.UNKNOWN, text[pos], pos, pos + 1))
                pos += 1
        self._identify_keys(tokens)
        return tokens

    def _identify_keys(self, tokens: List[Token]):
        """Identify JSON keys from string tokens

        Args:
            tokens: List of tokens to process
        """
        for i, token in enumerate(tokens):
            if token.type == TokenType.JSON_STRING:
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    if next_token.type == TokenType.WHITESPACE and i + 2 < len(tokens):
                        next_token = tokens[i + 2]
                    if next_token.value == ':':
                        token.type = TokenType.JSON_KEY


class XMLHighlighter:
    """XML syntax highlighter

    Provides tokenization and highlighting for XML content.
    """

    def highlight(self, text: str) -> List[Token]:
        """Highlight XML text by tokenizing it

        Args:
            text: XML text to highlight

        Returns:
            List of tokens
        """
        if not text:
            return []
        tokens = []
        pos = 0
        while pos < len(text):
            if text.startswith('<!--', pos):
                end = text.find('-->', pos)
                if end != -1:
                    tokens.append(Token(TokenType.XML_COMMENT, text[pos:end+3], pos, end+3))
                    pos = end + 3
                    continue
            if text.startswith('<![CDATA[', pos):
                end = text.find(']]>', pos)
                if end != -1:
                    tokens.append(Token(TokenType.XML_CDATA, text[pos:end+3], pos, end+3))
                    pos = end + 3
                    continue
            if text[pos] == '<':
                end = text.find('>', pos)
                if end != -1:
                    tokens.append(Token(TokenType.XML_TAG, text[pos:end+1], pos, end+1))
                    pos = end + 1
                    continue
            attr_match = re.match(r'\s+([a-zA-Z_][a-zA-Z0-9_\-\.]*)\s*=', text[pos:])
            if attr_match:
                tokens.append(Token(TokenType.XML_ATTRIBUTE_NAME, attr_match.group(1), pos, pos + len(attr_match.group(1))))
                pos += len(attr_match.group(0))
                continue
            if text[pos] in '"\'':
                quote = text[pos]
                end = text.find(quote, pos + 1)
                if end != -1:
                    tokens.append(Token(TokenType.XML_ATTRIBUTE_VALUE, text[pos:end+1], pos, end+1))
                    pos = end + 1
                    continue
            if text[pos].isspace():
                pos += 1
                continue
            pos += 1
        return tokens


class Theme:
    """Theme class for syntax highlighting colors

    Defines color schemes for different token types.
    """

    def __init__(self, name: str, background: str, foreground: str, colors: Dict[str, str]):
        """Initialize theme

        Args:
            name: Theme name
            background: Background color hex code
            foreground: Default foreground color hex code
            colors: Dictionary mapping token types to colors
        """
        self.name = name
        self.background = background
        self.foreground = foreground
        self.colors = colors

    def get_color(self, token_type: TokenType) -> str:
        """Get color for a token type

        Args:
            token_type: The token type

        Returns:
            Color hex code, or default foreground if not found
        """
        return self.colors.get(token_type.value, self.foreground)


BUILTIN_THEMES = {
    'light': Theme('娴呰壊', '#FFFFFF', '#000000', {  # Light theme
        TokenType.JSON_KEY.value: '#0000FF',
        TokenType.JSON_STRING.value: '#008000',
        TokenType.JSON_NUMBER.value: '#FF0000',
        TokenType.JSON_BOOLEAN.value: '#800080',
        TokenType.XML_TAG.value: '#0000FF',
        TokenType.XML_ATTRIBUTE_NAME.value: '#FF0000',
        TokenType.XML_ATTRIBUTE_VALUE.value: '#008000',
    }),
    'dark': Theme('娣辫壊', '#1E1E1E', '#D4D4D4', {  # Dark theme
        TokenType.JSON_KEY.value: '#9CDCFE',
        TokenType.JSON_STRING.value: '#CE9178',
        TokenType.JSON_NUMBER.value: '#B5CEA8',
        TokenType.JSON_BOOLEAN.value: '#569CD6',
        TokenType.XML_TAG.value: '#569CD6',
        TokenType.XML_ATTRIBUTE_NAME.value: '#9CDCFE',
        TokenType.XML_ATTRIBUTE_VALUE.value: '#CE9178',
    }),
}


class ThemeManager:
    """Theme manager

    Manages available themes and current theme selection.
    """

    def __init__(self, config_manager: Any = None):
        """Initialize theme manager

        Args:
            config_manager: Configuration manager instance
        """
        self.config = config_manager
        self.current_theme = 'light'
        if config_manager:
            self.current_theme = config_manager.get('theme.current_theme', 'light')
        logger.info(f"ThemeManager initialized, current theme: {self.current_theme}")

    def get_current_theme(self) -> Theme:
        """Get current theme

        Returns:
            Current theme object
        """
        return BUILTIN_THEMES.get(self.current_theme, BUILTIN_THEMES['light'])

    def set_theme(self, theme_name: str) -> bool:
        """Set current theme

        Args:
            theme_name: Name of the theme to set

        Returns:
            True if successful, False if theme not found
        """
        if theme_name in BUILTIN_THEMES:
            self.current_theme = theme_name
            if self.config:
                self.config.set('theme.current_theme', theme_name)
                self.config.save()
            logger.info(f"Theme changed: {theme_name}")
            return True
        return False

    def get_available_themes(self) -> List[str]:
        """Get list of available theme names

        Returns:
            List of theme names
        """
        return list(BUILTIN_THEMES.keys())


# ======== Week 3 Development: Export Functionality + Bookmark Functionality ========


class ExportEngine:
    """Export engine

    Handles exporting data to various formats (JSON, XML, HTML, CSV).
    """

    def __init__(self):
        """Initialize the export engine"""
        logger.info("ExportEngine initialized")

    def export_json(self, data: Any, filepath: str, indent: int = 4) -> bool:
        """Export data to JSON format

        Args:
            data: Data to export
            filepath: Output file path
            indent: Number of spaces for indentation

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            logger.info(f"JSON export successful: {filepath}")
            return True
        except Exception as e:
            logger.error(f"JSON export failed: {e}")
            return False

    def export_xml(self, data: Any, filepath: str) -> bool:
        """Export data to XML format

        Args:
            data: Data to export (lxml Element)
            filepath: Output file path

        Returns:
            True if successful, False otherwise
        """
        try:
            xml_string = ET.tostring(data, encoding='unicode', method='xml', pretty_print=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml_string)
            logger.info(f"XML export successful: {filepath}")
            return True
        except Exception as e:
            logger.error(f"XML export failed: {e}")
            return False

    def export_html(self, data: Any, filepath: str, content_type: str = 'json') -> bool:
        """Export data to HTML format

        Args:
            data: Data to export
            filepath: Output file path
            content_type: Content type (json/xml)

        Returns:
            True if successful, False otherwise
        """
        try:
            html_content = self._generate_html(data, content_type)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"HTML export successful: {filepath}")
            return True
        except Exception as e:
            logger.error(f"HTML export failed: {e}")
            return False

    def _generate_html(self, data: Any, content_type: str) -> str:
        """Generate HTML content

        Args:
            data: Data to convert
            content_type: Content type

        Returns:
            HTML string
        """
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>鏁版嵁瀵煎嚭</title>
    <style>
        body { font-family: 'Consolas', 'Monaco', monospace; padding: 20px; background: #f5f5f5; }
        pre { background: white; padding: 15px; border-radius: 5px; overflow-x: auto; }
        .key { color: #0000FF; }
        .string { color: #008000; }
        .number { color: #FF0000; }
        .boolean { color: #800080; }
        .null { color: #808080; }
        .tag { color: #0000FF; }
        .attr-name { color: #FF0000; }
        .attr-value { color: #008000; }
    </style>
</head>
<body>
    <h1>鏁版嵁瀵煎嚭</h1>
    <pre>
"""
        
        if content_type == 'json':
            html += self._highlight_json_html(data)
        else:
            xml_string = ET.tostring(data, encoding='unicode', method='xml', pretty_print=True)
            html += self._highlight_xml_html(xml_string)
        
        html += """
    </pre>
</body>
</html>
"""
        return html
    
    def _highlight_json_html(self, data: Any, indent: int = 0) -> str:
        """楂樹寒 JSON 涓?HTML
        
        Args:
            data: JSON 鏁版嵁
            indent: 缂╄繘绾у埆
            
        Returns:
            HTML 瀛楃�︿�?        """
        indent_str = '  ' * indent
        
        if isinstance(data, dict):
            if not data:
                return '<span class="null">{}</span>'
            
            result = ['<span class="null">{</span>']
            items = list(data.items())
            for i, (key, value) in enumerate(items):
                result.append(f'\n{indent_str}  <span class="key">"{key}"</span>: ')
                result.append(self._highlight_json_html(value, indent + 1))
                if i < len(items) - 1:
                    result.append(',')
            result.append(f'\n{indent_str}<span class="null">}}</span>')
            return ''.join(result)
        
        elif isinstance(data, list):
            if not data:
                return '<span class="null">[]</span>'
            
            result = ['<span class="null">[</span>']
            for i, item in enumerate(data):
                result.append(f'\n{indent_str}  ')
                result.append(self._highlight_json_html(item, indent + 1))
                if i < len(data) - 1:
                    result.append(',')
            result.append(f'\n{indent_str}<span class="null">]</span>')
            return ''.join(result)
        
        elif isinstance(data, str):
            return f'<span class="string">"{self._escape_html(data)}"</span>'
        elif isinstance(data, bool):
            return f'<span class="boolean">{str(data).lower()}</span>'
        elif data is None:
            return '<span class="null">null</span>'
        elif isinstance(data, (int, float)):
            return f'<span class="number">{data}</span>'
        else:
            return str(data)
    
    def _highlight_xml_html(self, xml_string: str) -> str:
        """楂樹寒 XML 涓?HTML
        
        Args:
            xml_string: XML 瀛楃�︿�?            
        Returns:
            HTML 瀛楃�︿�?        """
        import html as html_module
        escaped = html_module.escape(xml_string)
        
        # 楂樹寒鏍囩��
        escaped = re.sub(
            r'(&lt;/?)([\w\-\.]+)',
            r'\1<span class="tag">\2</span>',
            escaped
        )
        
        # 楂樹寒灞炴�у悕
        escaped = re.sub(
            r'([\s])([\w\-\.]+)(=)',
            r'\1<span class="attr-name">\2</span>\3',
            escaped
        )
        
        # 楂樹寒灞炴�у�?        escaped = re.sub(
            r'(=)(&quot;.*?&quot;)',
            r'\1<span class="attr-value">\2</span>',
            escaped
        )
        
        return escaped
    
    def _escape_html(self, text: str) -> str:
        """杞�涔� HTML 鐗规畩瀛楃��
        
        Args:
            text: 鏂囨湰
            
        Returns:
            杞�涔夊悗鐨勬枃鏈�
        """
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
    
    def export_csv(self, data: Any, filepath: str) -> bool:
        """瀵煎嚭涓?CSV 鏍煎紡锛堜粎閫傜敤浜庡垪琛?鏁扮粍锛?        
        Args:
            data: 瑕佸�煎嚭鐨勬暟鎹�
            filepath: 杈撳嚭鏂囦欢璺�寰�
            
        Returns:
            鏄�鍚︽垚鍔�
        """
        try:
            if not isinstance(data, list):
                logger.error("CSV 瀵煎嚭浠呮敮鎸佸垪琛?鏁扮粍绫诲瀷")
                return False
            
            if not data:
                with open(filepath, 'w', encoding='utf-8-sig') as f:
                    f.write('')
                logger.info(f"CSV 瀵煎嚭鎴愬姛锛堢┖鏁版嵁锛? {filepath}")
                return True
            
            # 鏀堕泦鎵�鏈夊彲鑳界殑閿?            all_keys = set()
            for item in data:
                if isinstance(item, dict):
                    all_keys.update(item.keys())
            
            if not all_keys:
                logger.error("娌℃湁鎵惧埌鍙�瀵煎嚭鐨勯�?)
                return False
            
            keys = sorted(all_keys)
            
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                
                for item in data:
                    if isinstance(item, dict):
                        # 澶勭悊宓屽�楀�硅薄
                        row = {}
                        for key in keys:
                            value = item.get(key, '')
                            if isinstance(value, (dict, list)):
                                value = json.dumps(value, ensure_ascii=False)
                            row[key] = str(value)
                        writer.writerow(row)
            
            logger.info(f"CSV 瀵煎嚭鎴愬姛: {filepath}")
            return True
        
        except Exception as e:
            logger.error(f"CSV Export failed: {e}")
            return False
    
    def export_pdf(self, data: Any, filepath: str, content_type: str = 'json') -> bool:
        """瀵煎嚭涓?PDF 鏍煎紡
        
        Args:
            data: 瑕佸�煎嚭鐨勬暟鎹�
            filepath: 杈撳嚭鏂囦欢璺�寰�
            content_type: 鍐呭�圭被鍨� (json/xml)
            
        Returns:
            鏄�鍚︽垚鍔�
        """
        try:
            # 鐢熸垚 HTML
            html_content = self._generate_html(data, content_type)
            
            # 浣跨敤娴忚�堝櫒鎵撳嵃涓� PDF锛堢畝鍖栫増锛?            # 瀹為檯瀹炵幇闇�瑕佷娇鐢?reportlab 鎴?weasyprint
            logger.warning("PDF 瀵煎嚭闇�瑕?reportlab 搴擄紝褰撳墠浠呯敓鎴?HTML")
            
            # 鐢熸垚 HTML 鏂囦欢浣滀负鏇夸唬
            html_filepath = filepath.rsplit('.', 1)[0] + '.html'
            with open(html_filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"HTML 鏂囦欢宸茬敓鎴愶紙PDF 闇�瑕佹墜鍔ㄦ墦鍗帮級: {html_filepath}")
            return True
        
        except Exception as e:
            logger.error(f"PDF Export failed: {e}")
            return False


import csv


class BookmarkManager:
    """Bookmark manager

    Manages bookmarks for important node locations, supporting
    grouping and organization.
    """

    DEFAULT_GROUP = "Default Group"  # Default group
    CONFIG_KEY = "bookmarks"

    def __init__(self, config_manager: Any = None):
        """Initialize bookmark manager

        Args:
            config_manager: Configuration manager instance
        """
        self.config = config_manager
        self.bookmarks: Dict[str, Bookmark] = {}
        self.groups: Dict[str, List[str]] = {self.DEFAULT_GROUP: []}

        self._load_bookmarks()
        logger.info(f"BookmarkManager initialized, bookmark count: {len(self.bookmarks)}")

    def _load_bookmarks(self):
        """Load bookmarks from configuration"""
        try:
            if not self.config:
                return

            bookmarks_data = self.config.get(self.CONFIG_KEY, [])

            for item_data in bookmarks_data:
                if isinstance(item_data, dict):
                    bookmark = Bookmark(
                        id=item_data.get('id', ''),
                        name=item_data.get('name', ''),
                        path=item_data.get('path', ''),
                        file_path=item_data.get('file_path', ''),
                        file_type=item_data.get('file_type', ''),
                        description=item_data.get('description', ''),
                        created_time=item_data.get('created_time', ''),
                        group=item_data.get('group', self.DEFAULT_GROUP)
                    )

                    if bookmark.id:
                        self.bookmarks[bookmark.id] = bookmark

                        # Update groups
                        if bookmark.group not in self.groups:
                            self.groups[bookmark.group] = []
                        self.groups[bookmark.group].append(bookmark.id)

            logger.info(f"Loaded {len(self.bookmarks)} bookmarks")

        except Exception as e:
            logger.error(f"Failed to load bookmarks: {e}")

    def _save_bookmarks(self):
        """Save bookmarks to configuration"""
        try:
            if not self.config:
                return

            bookmarks_data = []
            for bookmark in self.bookmarks.values():
                bookmarks_data.append({
                    'id': bookmark.id,
                    'name': bookmark.name,
                    'path': bookmark.path,
                    'file_path': bookmark.file_path,
                    'file_type': bookmark.file_type,
                    'description': bookmark.description,
                    'created_time': bookmark.created_time,
                    'group': bookmark.group
                })

            self.config.set(self.CONFIG_KEY, bookmarks_data)
            self.config.save()

            logger.debug(f"Saved {len(bookmarks_data)} bookmarks")

        except Exception as e:
            logger.error(f"Failed to save bookmarks: {e}")

    def add_bookmark(
        self,
        name: str,
        path: str,
        file_path: str,
        file_type: str,
        description: str = "",
        group: str = DEFAULT_GROUP
    ) -> bool:
        """Add a bookmark

        Args:
            name: Bookmark name
            path: Node path
            file_path: File path
            file_type: File type
            description: Description
            group: Group name

        Returns:
            鏄�鍚︽垚鍔�
        """
        try:
            # 鐢熸垚鍞�涓�ID
            bookmark_id = f"bookmark_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            
            bookmark = Bookmark(
                id=bookmark_id,
                name=name,
                path=path,
                file_path=file_path,
                file_type=file_type,
                description=description,
                created_time=datetime.now().isoformat(),
                group=group
            )
            
            self.bookmarks[bookmark_id] = bookmark
            
            # 鏇存柊Group
            if group not in self.groups:
                self.groups[group] = []
            self.groups[group].append(bookmark_id)
            
            self._save_bookmarks()
            logger.info(f"涔︾�惧凡娣诲�? {name}")
            return True
        
        except Exception as e:
            logger.error(f"Add Bookmark惧け璐�: {e}")
            return False
    
    def remove_bookmark(self, bookmark_id: str) -> bool:
        """绉婚櫎涔︾��
        
        Args:
            bookmark_id: 涔︾�綢D
            
        Returns:
            鏄�鍚︽垚鍔�
        """
        try:
            if bookmark_id in self.bookmarks:
                bookmark = self.bookmarks[bookmark_id]
                
                # 浠庡垎缁勪腑绉婚櫎
                if bookmark.group in self.groups:
                    if bookmark_id in self.groups[bookmark.group]:
                        self.groups[bookmark.group].remove(bookmark_id)
                
                # 绉婚櫎涔︾��
                del self.bookmarks[bookmark_id]
                
                self._save_bookmarks()
                logger.info(f"涔︾�惧凡绉婚�? {bookmark_id}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"绉婚櫎涔︾�惧け璐�: {e}")
            return False
    
    def get_bookmark(self, bookmark_id: str) -> Optional[Bookmark]:
        """鑾峰彇涔︾��
        
        Args:
            bookmark_id: 涔︾�綢D
            
        Returns:
            涔︾�惧�硅薄锛屼笉瀛樺湪杩斿洖 None
        """
        return self.bookmarks.get(bookmark_id)
    
    def get_all_bookmarks(self) -> List[Bookmark]:
        """鑾峰彇鎵�鏈変功绛?        
        Returns:
            涔︾�惧垪琛�
        """
        return list(self.bookmarks.values())
    
    def get_bookmarks_by_group(self, group: str) -> List[Bookmark]:
        """鑾峰彇鎸囧畾Group鐨勪功绛?        
        Args:
            group: Group鍚嶇О
            
        Returns:
            涔︾�惧垪琛�
        """
        if group not in self.groups:
            return []
        
        return [self.bookmarks[bid] for bid in self.groups[group] if bid in self.bookmarks]
    
    def get_groups(self) -> List[str]:
        """鑾峰彇鎵�鏈夊垎缁?        
        Returns:
            Group鍒楄〃
        """
        return list(self.groups.keys())
    
    def create_group(self, group_name: str) -> bool:
        """鍒涘缓Group
        
        Args:
            group_name: Group鍚嶇О
            
        Returns:
            鏄�鍚︽垚鍔�
        """
        if group_name not in self.groups:
            self.groups[group_name] = []
            logger.info(f"Group宸插垱寤? {group_name}")
            return True
        return False
    
    def delete_group(self, group_name: str) -> bool:
        """鍒犻櫎Group
        
        Args:
            group_name: Group鍚嶇О
            
        Returns:
            鏄�鍚︽垚鍔�
        """
        if group_name not in self.groups:
            return False
        
        if group_name == self.DEFAULT_GROUP:
            logger.warning("涓嶈兘鍒犻櫎Default Group")
            return False
        
        # 绉诲姩璇ュ垎缁勭殑鎵�鏈変功绛惧埌Default Group
        for bookmark_id in self.groups[group_name]:
            if bookmark_id in self.bookmarks:
                self.bookmarks[bookmark_id].group = self.DEFAULT_GROUP
                self.groups[self.DEFAULT_GROUP].append(bookmark_id)
        
        # 鍒犻櫎Group
        del self.groups[group_name]
        
        self._save_bookmarks()
        logger.info(f"Group宸插垹闄? {group_name}")
        return True
    
    def update_bookmark(
        self,
        bookmark_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        group: Optional[str] = None
    ) -> bool:
        """鏇存柊涔︾��
        
        Args:
            bookmark_id: 涔︾�綢D
            name: 鏂板悕绉?            description: 鏂版弿杩?            group: 鏂板垎缁?            
        Returns:
            鏄�鍚︽垚鍔�
        """
        try:
            if bookmark_id not in self.bookmarks:
                return False
            
            bookmark = self.bookmarks[bookmark_id]
            old_group = bookmark.group
            
            if name is not None:
                bookmark.name = name
            if description is not None:
                bookmark.description = description
            if group is not None:
                bookmark.group = group
                
                # 鏇存柊Group
                if old_group != group:
                    if bookmark_id in self.groups[old_group]:
                        self.groups[old_group].remove(bookmark_id)
                    
                    if group not in self.groups:
                        self.groups[group] = []
                    self.groups[group].append(bookmark_id)
            
            self._save_bookmarks()
            logger.info(f"涔︾�惧凡鏇存�? {bookmark_id}")
            return True
        
        except Exception as e:
            logger.error(f"鏇存柊涔︾�惧け璐�: {e}")
            return False
    
    def clear_all(self) -> bool:
        """娓呯┖鎵�鏈変功绛?        
        Returns:
            鏄�鍚︽垚鍔�
        """
        try:
            self.bookmarks.clear()
            self.groups = {self.DEFAULT_GROUP: []}
            self._save_bookmarks()
            logger.info("鎵�鏈変功绛惧凡娓呯┖")
            return True
        except Exception as e:
            logger.error(f"娓呯┖涔︾�惧け璐�: {e}")
            return False


# ======== Week 4 Development: Multi-tab + Keyboard Shortcuts ========


class TabPanel(wx.Panel):
    """Tab page panel

    Provides a panel for displaying file content with tree view
    and text display, supporting path navigation and selection.
    """
    
    def __init__(self, parent, tab_id: str, tab_manager: Any):
        super().__init__(parent)
        self.tab_id = tab_id
        self.tab_manager = tab_manager
        self.data = None
        self.file_type = None
        
        self.splitter = wx.SplitterWindow(self)
        self.tree = wx.TreeCtrl(self.splitter)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_item_selected)
        self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_right_click)
        
        self.text_display = wx.TextCtrl(self.splitter, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL)
        
        self.splitter.SplitVertically(self.tree, self.text_display)
        self.splitter.SetSashGravity(0.75)
        self.splitter.SetMinimumPaneSize(200)
        
        self.path_text = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 70))
        self.path_text.Bind(wx.EVT_TEXT, self.on_path_changed)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.splitter, 1, wx.EXPAND)
        sizer.Add(self.path_text, 0, wx.EXPAND | wx.TOP, 5)
        self.SetSizer(sizer)
        
        font = self.tree.GetFont()
        font.SetPointSize(12)
        self.tree.SetFont(font)
        
        logger.info(f"TabPanel 鍒濆�嬪寲瀹屾�? {tab_id}")
    
    def load_data(self, data: Any, file_type: str, file_path: str):
        self.data = data
        self.file_type = file_type
        self.tree.DeleteAllItems()
        
        if file_type == 'xml':
            self._populate_xml(data)
        else:
            self._populate_json(data)
        
        self._display_root()
        logger.info(f"鏁版嵁宸插姞杞藉埌鏍囩�鹃�? {file_path}")
    
    def _populate_xml(self, root, parent=None):
        if parent is None:
            parent = self.tree.AddRoot('root')
        
        siblings = {}
        for child in root:
            tag = child.tag
            siblings[tag] = siblings.get(tag, 0) + 1
            item = self.tree.AppendItem(parent, f"{tag} [{siblings[tag]}]")
            self._populate_xml(child, item)
    
    def _populate_json(self, data, parent=None, path=''):
        if parent is None:
            parent = self.tree.AddRoot('Root')
        
        if isinstance(data, dict):
            for key, value in data.items():
                item = self.tree.AppendItem(parent, key)
                self._populate_json(value, item, path + '.' + key)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                child = self.tree.AppendItem(parent, f"[{i}]")
                self._populate_json(item, child, path + f'[{i}]')
    
    def _display_root(self):
        try:
            if self.file_type == 'json':
                self.text_display.SetValue(json.dumps(self.data, indent=4, ensure_ascii=False))
            else:
                xml_str = ET.tostring(self.data, encoding='unicode', method='xml', pretty_print=True)
                self.text_display.SetValue(xml_str)
        except Exception as e:
            self.text_display.SetValue(f'鏄剧ずError: {e}')
    
    def on_item_selected(self, event):
        self.tab_manager.on_tab_item_selected(self.tab_id, event)
    
    def on_right_click(self, event):
        self.tab_manager.on_tab_right_click(self.tab_id, event)
    
    def on_path_changed(self, event):
        path = self.path_text.GetValue()
        self.tab_manager.on_tab_path_changed(self.tab_id, path)
    
    def set_path(self, path: str):
        self.path_text.SetValue(path)
    
    def get_path(self, item):
        parts = []
        curr = item
        while curr.IsOk():
            parts.append(self.tree.GetItemText(curr))
            curr = self.tree.GetItemParent(curr)
        
        if len(parts) == 1:
            return ""
        
        if self.file_type == 'xml':
            if parts[-1] == 'root':
                xml_parts = parts[:-1]
            else:
                xml_parts = parts
            
            if not xml_parts:
                return ""
            
            result = []
            for part in reversed(xml_parts):
                m = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if m:
                    tag = m.group(1)
                    idx = m.group(2)
                    if idx:
                        result.append(f"{tag}[{idx}]")
                    else:
                        result.append(tag)
            return "/".join(result)
        else:
            result = []
            for part in reversed(parts[1:]):
                # 妫�鏌ユ槸鍚︿负鏁扮粍绱㈠紩鑺傜偣锛歔1] 鎴?[1] [3]
                array_match = re.match(r'^\[(\d+)\](?:\s*\[\d+\])?$', part)
                if array_match:
                    index = array_match.group(1)
                    result.append(f"[{index}]")
                else:
                    clean = part.split(' [')[0]
                    result.append(f'["{clean}"]')
            return ''.join(result)


class TabManager:
    """Tab page manager

    Manages multiple file tabs with separate data, views, and navigation states.
    """

    def __init__(self, notebook: wx.Notebook):
        """Initialize tab manager

        Args:
            notebook: The wxPython notebook widget
        """
        self.notebook = notebook
        self.tabs: Dict[str, TabData] = {}
        self.panels: Dict[str, TabPanel] = {}
        self.current_id: Optional[str] = None
        logger.info("TabManager initialized")

    def add_tab(self, file_path: str, file_type: str, data: Any) -> str:
        """Add a new tab

        Args:
            file_path: Path to the file
            file_type: Type of file (json/xml)
            data: File content data

        Returns:
            Tab ID
        """
        tab_id = f"tab_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        tab_data = TabData(
            id=tab_id,
            title=os.path.basename(file_path),
            file_path=file_path,
            file_type=file_type,
            data=data
        )

        panel = TabPanel(self.notebook, tab_id, self)
        panel.load_data(data, file_type, file_path)

        self.notebook.AddPage(panel, tab_data.title)
        self.tabs[tab_id] = tab_data
        self.panels[tab_id] = panel

        self.notebook.SetSelection(self.notebook.GetPageCount() - 1)
        self.current_id = tab_id

        logger.info(f"Tab added: {tab_data.title}")
        return tab_id

    def close_tab(self, tab_id: str) -> bool:
        """Close a tab

        Args:
            tab_id: Tab ID to close

        Returns:
            True if successful, False otherwise
        """
        if tab_id not in self.tabs:
            return False

        for i in range(self.notebook.GetPageCount()):
            page = self.notebook.GetPage(i)
            if isinstance(page, TabPanel) and page.tab_id == tab_id:
                self.notebook.RemovePage(i)
                break

        del self.tabs[tab_id]
        del self.panels[tab_id]

        if self.current_id == tab_id:
            idx = self.notebook.GetSelection()
            if idx != -1:
                page = self.notebook.GetPage(idx)
                if isinstance(page, TabPanel):
                    self.current_id = page.tab_id
            else:
                self.current_id = None

        logger.info(f"Tab closed: {tab_id}")
        return True

    def on_tab_item_selected(self, tab_id: str, event):
        """Handle item selection in a tab

        Args:
            tab_id: Tab ID
            event: Tree selection event
        """
        if tab_id not in self.panels:
            return

        panel = self.panels[tab_id]
        item = event.GetItem()
        parent = panel.tree.GetItemParent(item)

        if parent.IsOk():
            child, cookie = panel.tree.GetFirstChild(parent)
            while child.IsOk():
                if child != item and panel.tree.IsExpanded(child):
                    panel.tree.Collapse(child)
                child, cookie = panel.tree.GetNextChild(parent, cookie)

        if not panel.tree.IsExpanded(item):
            panel.tree.Expand(item)

        path = panel.get_path(item)
        panel.set_path(path)
        self._display(tab_id, path)

        if tab_id in self.tabs:
            self.tabs[tab_id].current_path = path

    def on_tab_right_click(self, tab_id: str, event):
        """Handle right-click in a tab

        Args:
            tab_id: Tab ID
            event: Tree right-click event
        """
        pass

    def on_tab_path_changed(self, tab_id: str, path: str):
        """Handle path text change in a tab

        Args:
            tab_id: Tab ID
            path: New path string
        """
        if tab_id in self.tabs:
            self.tabs[tab_id].current_path = path
        self._display(tab_id, path)

    def _display(self, tab_id: str, path: str):
        """Display content for a path in a tab

        Args:
            tab_id: Tab ID
            path: Path to display
        """
        if tab_id not in self.tabs or tab_id not in self.panels:
            return

        tab = self.tabs[tab_id]
        panel = self.panels[tab_id]

        try:
            if tab.file_type == 'json':
                content = self._get_json(tab.data, path)
                panel.text_display.SetValue(json.dumps(content, indent=4, ensure_ascii=False))
            else:
                content = self._get_xml(tab.data, path)
                if content:
                    xml_str = ET.tostring(content, encoding='unicode', method='xml', pretty_print=True)
                    panel.text_display.SetValue(xml_str)
        except Exception as e:
            panel.text_display.SetValue(f'鏄剧ずError: {e}')  # Display error

    def _get_json(self, data: Any, path: str):
        """Get JSON value by path

        Args:
            data: JSON data
            path: JSON path

        Returns:
            Value at path, or None if not found
        """
        try:
            keys = re.findall(r'\["(.*?)"\]|\[(\d+)\]', path)
            content = data
            for k in keys:
                if k[0]:
                    content = content[k[0]]
                else:
                    content = content[int(k[1])]
            return content
        except:
            return None

    def _get_xml(self, data: Any, path: str):
        """Get XML element by path

        Args:
            data: XML data
            path: XPath

        Returns:
            Element at path, or None if not found
        """
        try:
            content = data
            parts = path.split('/')
            for part in parts:
                if not part:
                    continue
                m = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if m:
                    tag = m.group(1)
                    idx_str = m.group(2)
                    if idx_str:
                        children = list(content.findall(tag))
                        if children:
                            idx = int(idx_str) - 1
                            if 0 <= idx < len(children):
                                content = children[idx]
                    else:
                        children = list(content.findall(tag))
                        if children:
                            content = children[0]
            return content
        except:
            return None


class ShortcutManager:
    """Shortcut key manager

    Manages keyboard shortcuts for various actions.
    """

    DEFAULTS = {
        'file_open': ('Ctrl+O', 'Open File'),  # Open file
        'file_close': ('Ctrl+W', 'Close鏍囩�鹃�?),  # Close tab
        'edit_search': ('Ctrl+F', 'Search'),  # Search
        'view_expand': ('Ctrl+E', 'Expand All),  # Expand all
        'view_collapse': ('Ctrl+Shift+E', 'Collapse All),  # Collapse all
        'view_refresh': ('F5', 'Refresh'),  # Refresh
        'tab_next': ('Ctrl+Tab', '涓嬩竴涓�鏍囩�鹃〉'),  # Next tab
        'tab_prev': ('Ctrl+Shift+Tab', '涓婁竴涓�鏍囩�鹃〉'),  # Previous tab
    }

    def __init__(self, config_manager: Any = None):
        """Initialize shortcut manager

        Args:
            config_manager: Configuration manager instance
        """
        self.config = config_manager
        self.shortcuts: Dict[str, Tuple[str, str]] = {}
        self._load()
        logger.info("ShortcutManager initialized")

    def _load(self):
        """Load shortcuts from configuration"""
        try:
            if self.config:
                saved = self.config.get('shortcuts', {})
                self.shortcuts = self.DEFAULTS.copy()
                self.shortcuts.update(saved)
            else:
                self.shortcuts = self.DEFAULTS.copy()
        except Exception as e:
            logger.error(f"Failed to load shortcuts: {e}")
            self.shortcuts = self.DEFAULTS.copy()

    def _save(self):
        """Save shortcuts to configuration"""
        try:
            if self.config:
                self.config.set('shortcuts', self.shortcuts)
                self.config.save()
        except Exception as e:
            logger.error(f"Failed to save shortcuts: {e}")

    def get(self, action: str) -> Optional[Tuple[str, str]]:
        """Get shortcut for an action

        Args:
            action: Action name

        Returns:
            Tuple of (shortcut_string, description) or None
        """
        return self.shortcuts.get(action)

    def set(self, action: str, shortcut: str, desc: str = "") -> bool:
        """Set shortcut for an action

        Args:
            action: Action name
            shortcut: Shortcut string (e.g., "Ctrl+O")
            desc: Description

        Returns:
            True if successful, False if shortcut conflicts
        """
        try:
            for act, (sc, _) in self.shortcuts.items():
                if sc == shortcut and act != action:
                    logger.warning(f"Shortcut conflict: {shortcut}")
                    return False

            self.shortcuts[action] = (shortcut, desc)
            self._save()
            return True
        except Exception as e:
            logger.error(f"Failed to set shortcut: {e}")
            return False

    def reset(self) -> bool:
        """Reset all shortcuts to defaults

        Returns:
            True if successful
        """
        try:
            self.shortcuts = self.DEFAULTS.copy()
            self._save()
            return True
        except Exception as e:
            logger.error(f"Failed to reset shortcuts: {e}")
            return False

    def get_all(self) -> Dict[str, Tuple[str, str]]:
        """Get all shortcuts

        Returns:
            Dictionary mapping actions to (shortcut, description)
        """
        return self.shortcuts.copy()

    def parse(self, shortcut: str) -> Tuple[int, int]:
        """Parse shortcut string into flags and keycode

        Args:
            shortcut: Shortcut string (e.g., "Ctrl+O")

        Returns:
            Tuple of (accelerator_flags, keycode)
        """
        flags = 0
        keycode = 0
        parts = shortcut.split('+')

        for part in parts:
            p = part.strip().upper()
            if p == 'CTRL':
                flags |= wx.ACCEL_CTRL
            elif p == 'ALT':
                flags |= wx.ACCEL_ALT
            elif p == 'SHIFT':
                flags |= wx.ACCEL_SHIFT
            else:
                if len(p) == 1:
                    keycode = ord(p[0])
                elif p.startswith('F') and p[1:].isdigit():
                    keycode = wx.WXK_F1 + int(p[1:]) - 1
                elif p == 'TAB':
                    keycode = wx.WXK_TAB
                elif p == 'ENTER':
                    keycode = wx.WXK_RETURN
                elif p == 'ESC':
                    keycode = wx.WXK_ESCAPE
                elif p == 'SPACE':
                    keycode = wx.WXK_SPACE
                elif p == 'DELETE':
                    keycode = wx.WXK_DELETE
                elif p == 'BACK':
                    keycode = wx.WXK_BACK
                elif p == 'HOME':
                    keycode = wx.WXK_HOME
                elif p == 'END':
                    keycode = wx.WXK_END
                elif p == 'PAGEUP':
                    keycode = wx.WXK_PAGEUP
                elif p == 'PAGEDOWN':
                    keycode = wx.WXK_PAGEDOWN
                elif p == 'LEFT':
                    keycode = wx.WXK_LEFT
                elif p == 'RIGHT':
                    keycode = wx.WXK_RIGHT
                elif p == 'UP':
                    keycode = wx.WXK_UP
                elif p == 'DOWN':
                    keycode = wx.WXK_DOWN
                else:
                    keycode = ord(p[0])

        return (flags, keycode)

    def build_table(self) -> wx.AcceleratorTable:
        """Build wxPython accelerator table

        Returns:
            AcceleratorTable object
        """
        entries = []
        for action, (shortcut, _) in self.shortcuts.items():
            flags, keycode = self.parse(shortcut)
            entries.append((flags, keycode, getattr(wx, f'ID_{action.upper()}', wx.ID_ANY)))
        return wx.AcceleratorTable(entries)


if __name__ == '__main__':
    app = wx.App(False)
    viewer = WeeViewer()
    viewer.Center()
    app.MainLoop()
        
        tab = self.tabs[tab_id]
        panel = self.panels[tab_id]
        
        try:
            if tab.file_type == 'json':
                content = self._get_json(tab.data, path)
                panel.text_display.SetValue(json.dumps(content, indent=4, ensure_ascii=False))
            else:
                content = self._get_xml(tab.data, path)
                if content:
                    xml_str = ET.tostring(content, encoding='unicode', method='xml', pretty_print=True)
                    panel.text_display.SetValue(xml_str)
        except Exception as e:
            panel.text_display.SetValue(f'鏄剧ずError: {e}')
    
    def _get_json(self, data: Any, path: str):
        try:
            keys = re.findall(r'\["(.*?)"\]|\[(\d+)\]', path)
            content = data
            for k in keys:
                if k[0]:
                    content = content[k[0]]
                else:
                    content = content[int(k[1])]
            return content
        except:
            return None
    
    def _get_xml(self, data: Any, path: str):
        try:
            content = data
            parts = path.split('/')
            for part in parts:
                if not part:
                    continue
                m = re.match(r'(\w+)(?:\[(\d+)\])?', part)
                if m:
                    tag = m.group(1)
                    idx_str = m.group(2)
                    if idx_str:
                        children = list(content.findall(tag))
                        if children:
                            idx = int(idx_str) - 1
                            if 0 <= idx < len(children):
                                content = children[idx]
                    else:
                        children = list(content.findall(tag))
                        if children:
                            content = children[0]
            return content
        except:
            return None


class ShortcutManager:
    """蹇�鎹烽敭绠＄悊鍣�"""
    
