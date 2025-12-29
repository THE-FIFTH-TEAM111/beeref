#!/usr/bin/env python3
"""Script to update view.py to support PDF saving and exporting."""

import os
import re


def update_view_py():
    """Update view.py file with PDF support."""
    file_path = "d:/BeeRef/beeref/view.py"
    
    # Read the file content
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Update on_action_save_as method
    save_as_pattern = r'def on_action_save_as\(self\):.*?def on_action_save\(self\):'
    save_as_replacement = '''def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QFileDialog.getSaveFileName(
            parent=self, caption="Save file", directory=directory, filter=";;".join((f"{constants.APPNAME} File (*.bee)", "PDF (*.pdf)")))
        if filename:
            name, ext = os.path.splitext(filename)
            if not ext:
                ext = get_file_extension_from_format(formatstr)
                filename = f"{filename}.{ext}"
            if ext.lower() == ".pdf":
                self.on_action_export_scene()
                return
            self.do_save(filename, create_new=True)

    def on_action_save(self):'''    
    content = re.sub(save_as_pattern, save_as_replacement, content, flags=re.DOTALL)
    
    # 2. Update on_action_export_scene filter
    export_filter_pattern = r'filter=\";;\".join\((.*?)\)'
    export_filter_replacement = r'filter=";;".join(("Image Files (*.png *.jpg *.jpeg *.svg *.pdf)", "PNG (*.png)", "JPEG (*.jpg *.jpeg)", "SVG (*.svg)", "PDF (*.pdf)"))'
    content = re.sub(export_filter_pattern, export_filter_replacement, content)
    
    # Write the updated content back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully updated view.py with PDF support")


if __name__ == "__main__":
    update_view_py()