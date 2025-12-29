# 修复PDF导出问题的脚本

# 读取view.py文件内容
with open('beeref/view.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改on_action_save_as方法，添加PDF支持
old_save_as = '''    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, f = QFileDialog.getSaveFileName(
            parent=self, caption='Save file', directory=directory, filter=f'{constants.APPNAME} File (*.bee)')
        if filename:
            self.do_save(filename, create_new=True)'''

new_save_as = '''    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QFileDialog.getSaveFileName(
            parent=self, caption='Save file', directory=directory, filter=";;".join((f"{constants.APPNAME} File (*.bee)", "PDF (*.pdf)")))
        if filename:
            name, ext = os.path.splitext(filename)
            if not ext:
                ext = get_file_extension_from_format(formatstr)
                filename = f"{filename}.{ext}"
            if ext.lower() == ".pdf":
                self.on_action_export_scene(filename=filename)
                return
            self.do_save(filename, create_new=True)'''

# 2. 修改on_action_export_scene方法，支持直接接收文件名
old_export_scene = '''    def on_action_export_scene(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QFileDialog.getSaveFileName(
            parent=self, caption='Export Scene to Image', directory=directory,
            filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg)', 'PNG (*.png)', 'JPEG (*.jpg *.jpeg)', 'SVG (*.svg)')))'''

new_export_scene = '''    def on_action_export_scene(self, filename=None):
        directory = os.path.dirname(self.filename) if self.filename else None
        if not filename:
            filename, formatstr = QFileDialog.getSaveFileName(
                parent=self, caption='Export Scene to Image', directory=directory,
                filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg *.pdf)', 'PNG (*.png)', 'JPEG (*.jpg *.jpeg)', 'SVG (*.svg)', 'PDF (*.pdf)')))'''

# 3. 修改exporter_registry的访问方式，移除点号
old_exporter_access = '        exporter_cls = exporter_registry[ext]'
new_exporter_access = '        exporter_cls = exporter_registry[ext.lstrip(".")]'

# 应用修改
content = content.replace(old_save_as, new_save_as)
content = content.replace(old_export_scene, new_export_scene)
content = content.replace(old_exporter_access, new_exporter_access)

# 保存修改后的文件
with open('beeref/view.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("PDF export fix applied successfully!")