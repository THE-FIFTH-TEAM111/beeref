#!/usr/bin/env python3
"""
更新view.py中的导出筛选器，添加独立的PDF选项
"""

import re

def update_export_filter():
    """更新导出筛选器，添加独立的PDF选项"""
    with open('d:/BeeRef/beeref/view.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 更新导出场景的文件筛选器，添加独立的PDF选项
    content = re.sub(
        r"filter=';;'.join\(\('Image Files \(\*\.png \*\.jpg \*\.jpeg \*\.svg \*\.pdf\)', 'PNG \(\*\.png\)', 'JPEG \(\*\.jpg \*\.jpeg\)', 'SVG \(\*\.svg\)'\)\)",
        "filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg *.pdf)', 'PNG (*.png)', 'JPEG (*.jpg *.jpeg)', 'SVG (*.svg)', 'PDF (*.pdf)'))",
        content
    )
    
    with open('d:/BeeRef/beeref/view.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully updated export filter to include PDF option")

if __name__ == "__main__":
    update_export_filter()