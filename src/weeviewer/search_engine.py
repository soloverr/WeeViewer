"""
Search Engine Module

Provides search functionality for tree structures with advanced options including
regular expressions, case sensitivity, and whole word matching.
"""

import re
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from collections import deque
import logging
import wx

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Data class for search results"""
    item: Any  # TreeCtrl item
    path: str  # Node path
    match_text: str  # Matched text
    start_pos: int  # Match start position
    end_pos: int  # Match end position
    context: str = ""  # Match context

    def __eq__(self, other) -> bool:
        """Compare two search results for equality"""
        if not isinstance(other, SearchResult):
            return False
        return (
            self.path == other.path and
            self.match_text == other.match_text and
            self.start_pos == other.start_pos
        )

    def __hash__(self) -> int:
        """Return hash value for search result"""
        return hash((self.path, self.match_text, self.start_pos))


class TreeSearchEngine:
    """Tree Search Engine

    Supports searching nodes in tree structures with various search options
    and navigation capabilities.
    """

    def __init__(self, tree_ctrl: Any) -> None:
        """Initialize search engine

        Args:
            tree_ctrl: wx.TreeCtrl instance
        """
        self.tree = tree_ctrl
        self.results: List[SearchResult] = []
        self.current_index: int = -1
        self.last_query: str = ""
        self.last_options: Dict[str, Any] = {}

        # Performance statistics
        self.last_search_time: float = 0.0
        self.total_searches: int = 0

        logger.info("TreeSearchEngine initialization completed")
    
    def search(
        self,
        query: str,
        case_sensitive: bool = False,
        whole_word: bool = False,
        regex: bool = False,
        search_scope: str = "all"  # all, expanded, selected
    ) -> int:
        """Execute search

        Args:
            query: Search query string
            case_sensitive: Whether to be case sensitive
            whole_word: Whether to match whole words only
            regex: Whether to use regular expressions
            search_scope: Search scope (all=all nodes, expanded=expanded nodes, selected=selected node and its children)

        Returns:
            Number of matching results
        """
        start_time = time.time()

        # Clear previous results
        self.results = []
        self.current_index = -1
        self.last_query = query
        self.last_options = {
            'case_sensitive': case_sensitive,
            'whole_word': whole_word,
            'regex': regex,
            'search_scope': search_scope
        }

        # Return directly for empty query
        if not query or not query.strip():
            logger.debug("Search query is empty, returning 0 results")
            return 0

        # Compile search pattern
        pattern: Optional[re.Pattern] = None
        try:
            pattern = self._compile_search_pattern(query, case_sensitive, whole_word, regex)
        except re.error as e:
            logger.error(f"Regular expression compilation failed: {e}")
            return 0

        if pattern is None:
            return 0

        # Determine search root based on search scope
        root = self._get_search_root(search_scope)
        if not root or not root.IsOk():
            logger.warning(f"Search root node is invalid, scope={search_scope}")
            return 0

        # Execute search
        logger.info(f"Starting search: query='{query}', scope={search_scope}")
        self._search_recursive(root, pattern, search_scope)

        # Record performance
        self.last_search_time = time.time() - start_time
        self.total_searches += 1

        logger.info(f"Search completed: found {len(self.results)} matches, took {self.last_search_time:.3f} seconds")

        return len(self.results)
    
    def _compile_search_pattern(
        self,
        query: str,
        case_sensitive: bool,
        whole_word: bool,
        regex: bool
    ) -> Optional[re.Pattern]:
        """Compile search pattern

        Args:
            query: Search query
            case_sensitive: Whether to be case sensitive
            whole_word: Whether to match whole words only
            regex: Whether to use regular expressions

        Returns:
            Compiled regular expression, returns None on failure
        """
        try:
            if regex:
                # Regular expression mode
                flags: int = 0 if case_sensitive else re.IGNORECASE
                # Add Unicode support
                flags |= re.UNICODE
                pattern = re.compile(query, flags)
            else:
                # Plain text mode
                if whole_word:
                    # Whole word matching
                    pattern_str = r'\b' + re.escape(query) + r'\b'
                else:
                    # Partial matching
                    pattern_str = re.escape(query)

                flags = 0 if case_sensitive else re.IGNORECASE
                flags |= re.UNICODE
                pattern = re.compile(pattern_str, flags)

            return pattern

        except re.error as e:
            logger.error(f"Failed to compile search pattern: query='{query}', error={e}")
            return None
    
    def _get_search_root(self, search_scope: str) -> Any:
        """Get search root node

        Args:
            search_scope: Search scope

        Returns:
            Root node
        """
        if search_scope == "all":
            # Search all nodes
            return self.tree.GetRootItem()
        elif search_scope == "expanded":
            # Search only expanded nodes
            return self.tree.GetRootItem()
        elif search_scope == "selected":
            # Search selected node and its children
            selected = self.tree.GetSelection()
            if selected.IsOk():
                return selected
            else:
                return self.tree.GetRootItem()
        else:
            return self.tree.GetRootItem()
    
    def _search_recursive(
        self,
        item: Any,
        pattern: re.Pattern,
        search_scope: str
    ) -> None:
        """Recursively search nodes

        Args:
            item: Tree node
            pattern: Compiled regular expression
            search_scope: Search scope
        """
        # Check if current node should be searched
        if not self._should_search_item(item, search_scope):
            return

        # Search current node
        self._search_item(item, pattern)

        # Recursively search child nodes
        child, cookie = self.tree.GetFirstChild(item)
        while child.IsOk():
            self._search_recursive(child, pattern, search_scope)
            child, cookie = self.tree.GetNextChild(item, cookie)
    
    def _should_search_item(self, item: Any, search_scope: str) -> bool:
        """Determine if a node should be searched

        Args:
            item: Tree node
            search_scope: Search scope

        Returns:
            Whether to search
        """
        if search_scope == "all":
            return True
        elif search_scope == "expanded":
            # Search only expanded nodes
            return self.tree.IsExpanded(item)
        elif search_scope == "selected":
            # Search all child nodes
            return True
        else:
            return True
    
    def _search_item(self, item: Any, pattern: re.Pattern) -> None:
        """Search a single node

        Args:
            item: Tree node
            pattern: Compiled regular expression
        """
        # Get node text
        text: str = self.tree.GetItemText(item)
        if not text:
            return

        # Search for all matches
        for match in pattern.finditer(text):
            # Create search result
            result = SearchResult(
                item=item,
                path=self._get_item_path(item),
                match_text=match.group(),
                start_pos=match.start(),
                end_pos=match.end(),
                context=self._get_match_context(text, match)
            )

            self.results.append(result)

            # Performance optimization: limit maximum result count
            if len(self.results) >= 10000:
                logger.warning(f"Too many search results, limited to 10000")
                return
    
    def _get_item_path(self, item: Any) -> str:
        """Get full path of a node

        Args:
            item: Tree node

        Returns:
            Node path string
        """
        path_parts = []
        current_item = item

        while current_item.IsOk():
            text = self.tree.GetItemText(current_item)
            path_parts.append(text)
            current_item = self.tree.GetItemParent(current_item)

        # Reverse path
        path_parts.reverse()
        return " / ".join(path_parts)
    
    def _get_match_context(self, text: str, match: re.Match, context_size: int = 20) -> str:
        """Get context of match

        Args:
            text: Full text
            match: Match object
            context_size: Context size

        Returns:
            Context string
        """
        start = max(0, match.start() - context_size)
        end = min(len(text), match.end() + context_size)

        context = text[start:end]

        # Add ellipsis
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context
    
    def next_match(self) -> bool:
        """Jump to next match

        Returns:
            Whether navigation was successful
        """
        if not self.results:
            logger.debug("No search results")
            return False

        # Calculate next index
        self.current_index = (self.current_index + 1) % len(self.results)

        # Navigate to result
        self._navigate_to_result(self.results[self.current_index])

        logger.debug(f"Jumped to result {self.current_index + 1}/{len(self.results)}")
        return True
    
    def prev_match(self) -> bool:
        """Jump to previous match

        Returns:
            Whether navigation was successful
        """
        if not self.results:
            logger.debug("No search results")
            return False

        # Calculate previous index
        self.current_index = (self.current_index - 1) % len(self.results)

        # Navigate to result
        self._navigate_to_result(self.results[self.current_index])

        logger.debug(f"Jumped to result {self.current_index + 1}/{len(self.results)}")
        return True
    
    def _navigate_to_result(self, result: SearchResult) -> None:
        """Navigate to search result

        Args:
            result: Search result
        """
        # Ensure node is visible
        self.tree.EnsureVisible(result.item)

        # Select node
        self.tree.SelectItem(result.item)

        # Set focus
        self.tree.SetFocus()
    
    def go_to_match(self, index: int) -> bool:
        """Jump to match at specified index

        Args:
            index: Result index

        Returns:
            Whether navigation was successful
        """
        if not self.results or index < 0 or index >= len(self.results):
            logger.warning(f"Invalid result index: {index}")
            return False

        self.current_index = index
        self._navigate_to_result(self.results[index])

        logger.debug(f"Jumped to result {index + 1}/{len(self.results)}")
        return True
    
    def highlight_results(
        self,
        foreground_color: Any = None,
        background_color: Any = None
    ) -> None:
        """Highlight all matching results

        Args:
            foreground_color: Foreground color, defaults to orange
            background_color: Background color, defaults to light yellow
        """
        if foreground_color is None:
            foreground_color = wx.Colour(255, 140, 0)  # Dark orange
        if background_color is None:
            background_color = wx.Colour(255, 255, 200)  # Light yellow

        for result in self.results:
            try:
                self.tree.SetItemTextColour(result.item, foreground_color)
                self.tree.SetItemBackgroundColour(result.item, background_color)
            except Exception as e:
                logger.warning(f"Failed to highlight node: {e}")

        logger.info(f"Highlighted {len(self.results)} results")
    
    def clear_highlights(self) -> None:
        """Clear all highlights"""
        for result in self.results:
            try:
                self.tree.SetItemTextColour(result.item, wx.NullColour)
                self.tree.SetItemBackgroundColour(result.item, wx.NullColour)
            except Exception as e:
                logger.warning(f"Failed to clear highlight: {e}")

        logger.info("Cleared all highlights")
    
    def get_current_match(self) -> Optional[SearchResult]:
        """Get current match

        Returns:
            Current search result, returns None if none exists
        """
        if not self.results or self.current_index < 0:
            return None

        return self.results[self.current_index]
    
    def get_match_count(self) -> int:
        """Get number of matching results

        Returns:
            Number of results
        """
        return len(self.results)
    
    def get_current_index(self) -> int:
        """Get current result index

        Returns:
            Current index, returns -1 if none exists
        """
        return self.current_index
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search statistics

        Returns:
            Statistics dictionary
        """
        return {
            'total_results': len(self.results),
            'current_index': self.current_index,
            'last_query': self.last_query,
            'last_options': self.last_options,
            'last_search_time': self.last_search_time,
            'total_searches': self.total_searches
        }
    
    def clear_results(self) -> None:
        """Clear search results"""
        self.results = []
        self.current_index = -1
        self.last_query = ""
        self.last_options = {}
        logger.debug("Search results cleared")
    
    def repeat_last_search(self) -> int:
        """Repeat last search

        Returns:
            Number of matching results
        """
        if not self.last_query:
            logger.debug("No search to repeat")
            return 0

        logger.info("Repeating last search")
        return self.search(
            self.last_query,
            case_sensitive=self.last_options.get('case_sensitive', False),
            whole_word=self.last_options.get('whole_word', False),
            regex=self.last_options.get('regex', False),
            search_scope=self.last_options.get('search_scope', 'all')
        )