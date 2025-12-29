#!/usr/bin/env python3
"""Simple script to add PDF support to BeeRef."""

import os


def main():
    """Modify view.py to support PDF saving and exporting."""
    file_path = "d:/BeeRef/beeref/view.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    in_save_as = False
    save_as_lines = []
    
    for line in lines:
        if not in_save_as:
            if 'def on_action_save_as(self):' in line:
                in_save_as = True
                # Add the modified on_action_save_as method
                new_lines.extend([
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
                ])
                # Skip the original lines
                save_as_lines = []
            elif 'def on_action_save(self):' in line and save_as_lines:
                # We've found the next method, so stop skipping
                in_save_as = False
                new_lines.append(line)
            elif 'filter=";;".join((' in line and 'Image Files' in line:
                # Update the export filter to include PDF
                new_line = line.replace('Image Files (*.png *.jpg *.jpeg *.svg)', 
                                     'Image Files (*.png *.jpg *.jpeg *.svg *.pdf)')
                new_line = new_line.replace(')', ', "PDF (*.pdf)")')
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            # Skip the original save_as method lines
            save_as_lines.append(line)
            if 'def on_action_save(self):' in line:
                in_save_as = False
                new_lines.append(line)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("Successfully added PDF support to BeeRef!")


if __name__ == "__main__":
    main()