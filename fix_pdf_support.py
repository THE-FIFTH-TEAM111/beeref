#!/usr/bin/env python3
"""Fix PDF support in BeeRef by updating view.py."""

import os


def main():
    """Update view.py to support PDF saving and exporting."""
    file_path = "d:/BeeRef/beeref/view.py"
    
    # Read the entire file
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Update on_action_save_as method
    in_save_as = False
    save_as_start = 0
    save_as_end = 0
    
    for i, line in enumerate(lines):
        if 'def on_action_save_as(self):' in line:
            in_save_as = True
            save_as_start = i
        elif in_save_as and 'def on_action_save(self):' in line:
            save_as_end = i - 1
            break
    
    if in_save_as and save_as_start < save_as_end:
        # Replace the on_action_save_as method
        new_save_as = [
            '    def on_action_save_as(self):\n',
            '        self.cancel_active_modes()\n',
            '        directory = os.path.dirname(self.filename) if self.filename else None\n',
            '        filename, formatstr = QFileDialog.getSaveFileName(\n',
            '            parent=self, caption="Save file", directory=directory, filter=";;".join((f"{constants.APPNAME} File (*.bee)", "PDF (*.pdf)")))\n',
            '        if filename:\n',
            '            name, ext = os.path.splitext(filename)\n',
            '            if not ext:\n',
            '                ext = get_file_extension_from_format(formatstr)\n',
            '                filename = f"{filename}.{ext}"\n',
            '            if ext.lower() == ".pdf":\n',
            '                self.on_action_export_scene()\n',
            '                return\n',
            '            self.do_save(filename, create_new=True)\n',
            '\n'
        ]
        
        # Replace the old method with the new one
        lines = lines[:save_as_start] + new_save_as + lines[save_as_end+1:]
    
    # Update on_action_export_scene method's filter
    in_export_scene = False
    
    for i, line in enumerate(lines):
        if 'def on_action_export_scene(self):' in line:
            in_export_scene = True
        elif in_export_scene and 'filter=' in line:
            # Update the filter line
            old_filter = line.strip()
            new_filter = "filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg *.pdf)', 'PNG (*.png)', 'JPEG (*.jpg *.jpeg)', 'SVG (*.svg)', 'PDF (*.pdf)'))\n"
            lines[i] = line.replace(old_filter, new_filter)
            break
    
    # Write the changes back to the file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("Successfully updated view.py with PDF support!")


if __name__ == "__main__":
    main()