#!/usr/bin/env python3
"""
WeeViewer startup script
Run this script to launch WeeViewer application
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from weeviewer.main import WeeViewer
import wx

if __name__ == '__main__':
    app = wx.App(False)
    viewer = WeeViewer()
    viewer.Center()
    app.MainLoop()