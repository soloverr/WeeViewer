"""
Performance Optimization Module
Contains virtual tree control, streaming parser, and cache system
"""
import wx
from typing import Optional, List, Dict, Any, Callable, Tuple
from collections import deque
import time
import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================================
# Virtual Tree Control
# ============================================================================

@dataclass
class VirtualTreeItem:
    """Virtual tree node"""
    item_id: str
    parent_id: Optional[str]
    text: str
    data: Any
    has_children: bool = False
    children_loaded: bool = False
    children: List[str] = None
    expanded: bool = False
    depth: int = 0

    def __post_init__(self):
        if self.children is None:
            self.children = []


class VirtualTreeCtrl(wx.ScrolledWindow):
    """Virtual tree control - supports on-demand loading of large-scale data"""

    def __init__(
        self,
        parent,
        data_loader: Callable[[str, int, int], List[VirtualTreeItem]],
        style=0,
        item_height: int = 24,
        indent_size: int = 20
    ):
        """Initialize virtual tree control

        Args:
            parent: Parent window
            data_loader: Data loading function (parent_id, offset, limit) -> items
            style: Window style
            item_height: Node height
            indent_size: Indent size
        """
        super().__init__(parent, style=style)

        self.data_loader = data_loader
        self.items: Dict[str, VirtualTreeItem] = {}
        self.visible_items: List[Tuple[str, int]] = []  # (item_id, indent)
        self.root_id = "root"

        # Visual configuration
        self.item_height = item_height
        self.indent_size = indent_size
        self.font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.selection_colour = wx.Colour(51, 153, 255)
        self.hover_colour = wx.Colour(230, 240, 255)

        # State
        self.selected_item_id: Optional[str] = None
        self.hover_item_id: Optional[str] = None
        self.expanded_cache: set = set()

        # Cache
        self.visible_cache: Dict[str, wx.Rect] = {}

        # Event binding
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_double_click)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mousewheel)
        self.Bind(wx.EVT_MOTION, self._on_mouse_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave_window)

        # Load root node
        self._load_root()

        # Set scrollbar
        self.SetScrollRate(10, self.item_height)

        logger.info("VirtualTreeCtrl initialized")

    def _load_root(self):
        """Load root node"""
        root_item = VirtualTreeItem(
            item_id=self.root_id,
            parent_id=None,
            text="Root",
            data=None,
            has_children=True,
            depth=0
        )
        self.items[self.root_id] = root_item
        self._update_visible_items()

    def _update_visible_items(self):
        """Update visible node list"""
        self.visible_items = []

        # Traverse from root node
        if self.root_id in self.items:
            self._collect_visible_items(self.root_id)

        # Update scroll range
        total_height = len(self.visible_items) * self.item_height
        self.SetVirtualSize((self.GetSize().width, total_height))

        # Refresh display
        self.Refresh()

    def _collect_visible_items(self, item_id: str):
        """Collect visible nodes

        Args:
            item_id: Node ID
        """
        if item_id in self.items:
            item = self.items[item_id]
            self.visible_items.append((item_id, item.depth))

            # If expanded and has children, add recursively
            if item.expanded and item.has_children:
                # Ensure children are loaded
                if not item.children_loaded:
                    self._load_children(item_id)

                for child_id in item.children:
                    self._collect_visible_items(child_id)

    def _load_children(self, parent_id: str):
        """Load child nodes

        Args:
            parent_id: Parent node ID
        """
        try:
            # Use data loader to load child nodes
            items = self.data_loader(parent_id, 0, 100)  # Load 100 child nodes by default

            # Update parent node
            if parent_id in self.items:
                parent = self.items[parent_id]
                parent.children = [item.item_id for item in items]
                parent.children_loaded = True
                parent.has_children = len(items) > 0

            # Add child nodes
            parent_depth = self.items[parent_id].depth if parent_id in self.items else 0
            for item in items:
                item.depth = parent_depth + 1
                self.items[item.item_id] = item

            logger.debug(f"Loaded {len(items)} child nodes to {parent_id}")
        except Exception as e:
            logger.error(f"Failed to load child nodes: {e}")

    def _on_paint(self, event):
        """Paint event"""
        dc = wx.PaintDC(self)

        # Set font
        dc.SetFont(self.font)

        # Calculate visible range
        view_start = self.GetViewStart()[1] * self.item_height
        view_height = self.GetSize().height

        # Draw background
        dc.SetBackground(wx.Brush(wx.WHITE))
        dc.Clear()

        # Draw visible nodes
        y_offset = 0
        for item_id, depth in self.visible_items:
            if y_offset >= view_start and y_offset < view_start + view_height:
                self._draw_item(dc, item_id, depth, y_offset - view_start)

            y_offset += self.item_height

        event.Skip()

    def _draw_item(self, dc: wx.DC, item_id: str, depth: int, y: int):
        """Draw node

        Args:
            dc: Device context
            item_id: Node ID
            depth: Depth
            y: Y coordinate
        """
        if item_id not in self.items:
            return

        item = self.items[item_id]
        x = depth * self.indent_size

        # Draw selected background
        if item_id == self.selected_item_id:
            dc.SetBrush(wx.Brush(self.selection_colour))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(0, y, self.GetSize().width, self.item_height)
        elif item_id == self.hover_item_id:
            dc.SetBrush(wx.Brush(self.hover_colour))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(0, y, self.GetSize().width, self.item_height)

        # Draw expand/collapse icon
        icon_size = 16
        icon_x = x
        icon_y = y + (self.item_height - icon_size) // 2

        if item.has_children:
            if item.expanded:
                # Draw minus sign (expanded)
                dc.SetBrush(wx.Brush(wx.Colour(200, 200, 200)))
                dc.SetPen(wx.Pen(wx.Colour(100, 100, 100)))
                dc.DrawRectangle(icon_x, icon_y, icon_size, icon_size)
                dc.DrawLine(icon_x + 4, icon_y + icon_size // 2,
                           icon_x + icon_size - 4, icon_y + icon_size // 2)
            else:
                # Draw plus sign (collapsed)
                dc.SetBrush(wx.Brush(wx.Colour(200, 200, 200)))
                dc.SetPen(wx.Pen(wx.Colour(100, 100, 100)))
                dc.DrawRectangle(icon_x, icon_y, icon_size, icon_size)
                dc.DrawLine(icon_x + 4, icon_y + icon_size // 2,
                           icon_x + icon_size - 4, icon_y + icon_size // 2)
                dc.DrawLine(icon_x + icon_size // 2, icon_y + 4,
                           icon_x + icon_size // 2, icon_y + icon_size - 4)

        # Draw text
        text_x = icon_x + icon_size + 5
        text_y = y + (self.item_height - dc.GetCharHeight()) // 2

        # Set text color
        if item_id == self.selected_item_id:
            dc.SetTextForeground(wx.WHITE)
        else:
            dc.SetTextForeground(wx.BLACK)

        dc.DrawText(item.text, text_x, text_y)

    def _on_left_down(self, event):
        """Mouse left button click"""
        pos = event.GetPosition()
        view_start = self.GetViewStart()[1] * self.item_height

        # Calculate clicked node
        clicked_index = (pos.y + view_start) // self.item_height
        if 0 <= clicked_index < len(self.visible_items):
            item_id, depth = self.visible_items[clicked_index]

            # Check if expand/collapse icon was clicked
            icon_x = depth * self.indent_size
            icon_y = clicked_index * self.item_height - view_start
            icon_size = 16

            if (icon_x <= pos.x <= icon_x + icon_size and
                icon_y <= pos.y <= icon_y + icon_size):
                self._toggle_expand(item_id)
            else:
                # Select node
                self._select_item(item_id)

        event.Skip()

    def _on_double_click(self, event):
        """Mouse double click"""
        pos = event.GetPosition()
        view_start = self.GetViewStart()[1] * self.item_height

        # Calculate double-clicked node
        clicked_index = (pos.y + view_start) // self.item_height
        if 0 <= clicked_index < len(self.visible_items):
            item_id, _ = self.visible_items[clicked_index]
            self._on_item_activated(item_id)

        event.Skip()

    def _on_mouse_motion(self, event):
        """Mouse motion"""
        pos = event.GetPosition()
        view_start = self.GetViewStart()[1] * self.item_height

        # Calculate hovered node
        hover_index = (pos.y + view_start) // self.item_height
        old_hover = self.hover_item_id

        if 0 <= hover_index < len(self.visible_items):
            item_id, _ = self.visible_items[hover_index]
            self.hover_item_id = item_id
        else:
            self.hover_item_id = None

        # If hovered node changed, refresh display
        if old_hover != self.hover_item_id:
            self.Refresh()

        event.Skip()

    def _on_leave_window(self, event):
        """Mouse leave window"""
        if self.hover_item_id is not None:
            self.hover_item_id = None
            self.Refresh()
        event.Skip()

    def _toggle_expand(self, item_id: str):
        """Toggle expand/collapse state

        Args:
            item_id: Node ID
        """
        if item_id in self.items:
            item = self.items[item_id]

            if item.has_children:
                item.expanded = not item.expanded
                if item.expanded:
                    self.expanded_cache.add(item_id)
                else:
                    self.expanded_cache.discard(item_id)

                self._update_visible_items()
                logger.debug(f"Toggled node {item_id} expand state: {item.expanded}")

    def _select_item(self, item_id: str):
        """Select node

        Args:
            item_id: Node ID
        """
        old_selection = self.selected_item_id
        self.selected_item_id = item_id

        if old_selection != item_id:
            self.Refresh()
            self._on_item_selected(item_id)

    def _on_item_activated(self, item_id: str):
        """Node activation event (can be overridden by subclasses)

        Args:
            item_id: Node ID
        """
        logger.debug(f"Node activated: {item_id}")
        pass

    def _on_item_selected(self, item_id: str):
        """Node selection event (can be overridden by subclasses)

        Args:
            item_id: Node ID
        """
        logger.debug(f"Node selected: {item_id}")
        pass

    def _on_size(self, event):
        """Size change event"""
        self._update_visible_items()
        event.Skip()

    def _on_mousewheel(self, event):
        """Mouse wheel event"""
        rotation = event.GetWheelRotation()
        lines = rotation // event.GetWheelDelta()

        current_pos = self.GetViewStart()[1]
        new_pos = max(0, current_pos - lines)

        self.Scroll(-1, new_pos)

    def GetSelection(self):
        """Get selected node ID

        Returns:
            Node ID, returns None if nothing is selected
        """
        return self.selected_item_id

    def SelectItem(self, item_id: str):
        """Select node

        Args:
            item_id: Node ID
        """
        self._select_item(item_id)

    def Expand(self, item_id: str):
        """Expand node

        Args:
            item_id: Node ID
        """
        if item_id in self.items and not self.items[item_id].expanded:
            self._toggle_expand(item_id)

    def Collapse(self, item_id: str):
        """Collapse node

        Args:
            item_id: Node ID
        """
        if item_id in self.items and self.items[item_id].expanded:
            self._toggle_expand(item_id)

    def ExpandAll(self):
        """Expand all nodes"""
        for item_id in self.items:
            if self.items[item_id].has_children:
                self.Expand(item_id)

    def CollapseAll(self):
        """Collapse all nodes"""
        for item_id in self.items:
            if self.items[item_id].has_children and item_id != self.root_id:
                self.Collapse(item_id)

    def Clear(self):
        """Clear all nodes"""
        self.items.clear()
        self.visible_items.clear()
        self.expanded_cache.clear()
        self.selected_item_id = None
        self.hover_item_id = None
        self._load_root()

    def GetItemCount(self) -> int:
        """Get total node count

        Returns:
            Node count
        """
        return len(self.items)

    def GetVisibleItemCount(self) -> int:
        """Get visible node count

        Returns:
            Visible node count
        """
        return len(self.visible_items)


# ============================================================================
# Cache System
# ============================================================================

class LRUCache:
    """Custom LRU cache"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """Initialize LRU cache

        Args:
            max_size: Maximum cache size
            ttl: Time to live (seconds)
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.access_order: List[str] = []
        self.hits = 0
        self.misses = 0

        logger.debug(f"LRUCache 初始化: max_size={max_size}, ttl={ttl}")

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Cache key
        """
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, *args, **kwargs) -> Optional[Any]:
        """Get cache value

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Cache value, returns None if not found
        """
        key = self._generate_key(*args, **kwargs)

        if key in self.cache:
            value, timestamp = self.cache[key]

            # Check if expired
            if time.time() - timestamp < self.ttl:
                # Update access order
                self.access_order.remove(key)
                self.access_order.append(key)
                self.hits += 1
                return value
            else:
                # Delete expired item
                del self.cache[key]
                self.access_order.remove(key)

        self.misses += 1
        return None

    def set(self, value: Any, *args, **kwargs) -> None:
        """Set cache value

        Args:
            value: Cache value
            *args: Positional arguments
            **kwargs: Keyword arguments
        """
        key = self._generate_key(*args, **kwargs)

        # If cache is full, delete oldest item
        if len(self.cache) >= self.max_size and key not in self.cache:
            if self.access_order:
                oldest_key = self.access_order.pop(0)
                del self.cache[oldest_key]

        # Add new item
        self.cache[key] = (value, time.time())
        self.access_order.append(key)

    def clear(self) -> None:
        """Clear cache"""
        self.cache.clear()
        self.access_order.clear()
        self.hits = 0
        self.misses = 0
        logger.debug("LRUCache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics

        Returns:
            Statistics dictionary
        """
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0

        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'total_requests': total_requests
        }


class CacheManager:
    """Cache manager - manages multiple types of caches"""

    def __init__(self):
        """Initialize cache manager"""
        # Node cache: 30-minute TTL, max 5000 items
        self.node_cache = LRUCache(max_size=5000, ttl=1800)

        # Search results cache: 10-minute TTL, max 1000 items
        self.search_cache = LRUCache(max_size=1000, ttl=600)

        # Content cache: 5-minute TTL, max 2000 items
        self.content_cache = LRUCache(max_size=2000, ttl=300)

        logger.info("CacheManager initialized")

    def get_node(self, path: str, file_type: str) -> Optional[Any]:
        """Get cached node

        Args:
            path: Node path
            file_type: File type

        Returns:
            Node data
        """
        return self.node_cache.get(path, file_type)

    def set_node(self, path: str, file_type: str, data: Any) -> None:
        """Set node cache

        Args:
            path: Node path
            file_type: File type
            data: Node data
        """
        self.node_cache.set(data, path, file_type)

    def get_search_results(self, query: str, options: Dict[str, Any]) -> Optional[List[Any]]:
        """Get cached search results

        Args:
            query: Search query
            options: Search options

        Returns:
            Search results list
        """
        key = frozenset(options.items())
        return self.search_cache.get(query, key)

    def set_search_results(self, query: str, options: Dict[str, Any], results: List[Any]) -> None:
        """Set search results cache

        Args:
            query: Search query
            options: Search options
            results: Search results
        """
        key = frozenset(options.items())
        self.search_cache.set(results, query, key)

    def get_content(self, path: str, file_type: str) -> Optional[str]:
        """Get cached content

        Args:
            path: Node path
            file_type: File type

        Returns:
            Content string
        """
        return self.content_cache.get(path, file_type)

    def set_content(self, path: str, file_type: str, content: str) -> None:
        """Set content cache

        Args:
            path: Node path
            file_type: File type
            content: Content string
        """
        self.content_cache.set(content, path, file_type)

    def clear_all(self) -> None:
        """Clear all caches"""
        self.node_cache.clear()
        self.search_cache.clear()
        self.content_cache.clear()
        logger.info("All caches cleared")

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all caches

        Returns:
            Statistics dictionary
        """
        return {
            'node_cache': self.node_cache.get_stats(),
            'search_cache': self.search_cache.get_stats(),
            'content_cache': self.content_cache.get_stats()
        }


# ============================================================================
# Streaming Parser (Placeholder Implementation)
# ============================================================================

class StreamingJSONParser:
    """Streaming JSON parser"""

    def __init__(self, file_path: str):
        """Initialize streaming JSON parser

        Args:
            file_path: JSON file path
        """
        self.file_path = file_path
        logger.info(f"StreamingJSONParser 初始化: {file_path}")

    def parse(self) -> List[Dict[str, Any]]:
        """Parse JSON file

        Returns:
            Parsed results list
        """
        try:
            import ijson
            results = []

            with open(self.file_path, 'r', encoding='utf-8') as f:
                parser = ijson.parse(f)

                for prefix, event, value in parser:
                    results.append({
                        'type': event,
                        'path': prefix,
                        'value': value
                    })

            return results
        except ImportError:
            logger.warning("ijson not installed, using standard json module")
            import json
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return [{'type': 'complete', 'path': '', 'value': data}]


class StreamingXMLParser:
    """Streaming XML parser"""

    def __init__(self, file_path: str):
        """Initialize streaming XML parser

        Args:
            file_path: XML file path
        """
        self.file_path = file_path
        logger.info(f"StreamingXMLParser 初始化: {file_path}")

    def parse(self) -> List[Dict[str, Any]]:
        """Parse XML file

        Returns:
            Parsed results list
        """
        import xml.sax
        from xml.sax.handler import ContentHandler

        class XMLHandler(ContentHandler):
            def __init__(self):
                self.elements = []
                self.element_stack = []
                self.current_path = ""

            def startElement(self, name, attrs):
                if self.element_stack:
                    self.current_path += f"/{name}"
                else:
                    self.current_path = name

                self.element_stack.append(name)

                self.elements.append({
                    'type': 'start',
                    'name': name,
                    'path': self.current_path,
                    'attributes': dict(attrs)
                })

            def endElement(self, name):
                if self.element_stack and self.element_stack[-1] == name:
                    self.element_stack.pop()

                if self.element_stack:
                    parts = self.current_path.rsplit('/', 1)
                    if len(parts) > 1:
                        self.current_path = parts[0]
                    else:
                        self.current_path = ""
                else:
                    self.current_path = ""

                self.elements.append({
                    'type': 'end',
                    'name': name,
                    'path': self.current_path
                })

            def characters(self, content):
                if content.strip():
                    self.elements.append({
                        'type': 'text',
                        'path': self.current_path,
                        'value': content.strip()
                    })

        handler = XMLHandler()
        parser = xml.sax.make_parser()
        parser.setContentHandler(handler)

        with open(self.file_path, 'r', encoding='utf-8') as f:
            parser.parse(f)

        return handler.elements