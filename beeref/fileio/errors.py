# This file is part of BeeRef.                                                  # 此文件是 BeeRef 项目的一部分
#
# BeeRef is free software: you can redistribute it and/or modify                # BeeRef 是自由软件：您可以重新分发和/或修改它
# it under the terms of the GNU General Public License as published by          # 根据 GNU 通用公共许可证的条款，由 Free Software Foundation 发布，     
# the Free Software Foundation, either version 3 of the License, or             # 无论是版本 3 的许可证，还是（在您选择的情况下）任何更高版本。
#
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,                     # BeeRef 是分发在希望它会有用的基础上 
# but WITHOUT ANY WARRANTY; without even the implied warranty of                # 但没有任何保修；甚至没有对适销性或特定用途适用性的暗示保证。    
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                 # 有关更多详细信息，请参阅 GNU 通用公共许可证
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License             # 您应该已经收到了 GNU 通用公共许可证的副本
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.              # 如果没有，请参阅 <https://www.gnu.org/licenses/>   


# 图片加载错误的提示消息，当图片格式未知或过大时显示
IMG_LOADING_ERROR_MSG = (
    'Unknown format or too big?\n'  # 未知格式或文件太大？
    'Check Settings -> Images & Items -> Maximum Image Size')  # 请检查设置 -> 图像和项目 -> 最大图像大小


# 自定义的文件IO错误类，继承自Python内置的Exception类
class BeeFileIOError(Exception):
     # 构造函数，初始化错误消息和文件名
    def __init__(self, msg, filename):
        self.msg = msg # 保存错误消息
        self.filename = filename # 保存发生错误的文件名

