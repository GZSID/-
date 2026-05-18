"""
桌面宠物程序 - PyQt6 + OpenCV透明置顶窗口宠物
视频文件:
  - pet_idle.mp4（默认状态）
  - pet_happy.mp4（开心状态-点击触发）
音频文件:
  - pet_happy.mp3（仅在happy状态播放）
"""

import sys
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QMenu, QSystemTrayIcon
from PyQt6.QtGui import QImage, QPixmap, QAction, QIcon, QPainter, QColor
from PyQt6.QtCore import Qt, QTimer, QPoint, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


class DesktopPet(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_window()       # 窗口初始化
        self.init_tray()         # 托盘图标
        self.init_video_player() # 视频播放器
        self.init_behavior()     # 行为控制

    # ========== 基本组件 ==========

    def init_window(self):
        # 窗口设置：无边框、置顶、透明背景
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                           Qt.WindowType.WindowStaysOnTopHint |
                           Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("QMainWindow { background: transparent; } QLabel { background: transparent; }")

        # 创建标签并设置透明背景
        self.label = QLabel(self)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setStyleSheet("background: transparent;")
        self.setCentralWidget(self.label)

        self.dragging = False
        self.drag_pos = QPoint()

    def init_tray(self):
        self.tray = QSystemTrayIcon(self.create_pet_icon(), self)
        self.tray.setToolTip("Desktop Pet")

        menu = QMenu()
        menu.addAction("显示宠物", self.show)
        menu.addSeparator()
        menu.addAction("退出", self.close)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_click)
        self.tray.show()

    def create_pet_icon(self):
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setBrush(QColor(255, 165, 0)); p.setPen(Qt.GlobalColor.transparent)
        p.drawEllipse(8, 12, 16, 16)
        p.setBrush(QColor(255, 140, 0)); p.drawEllipse(10, 4, 12, 12)
        p.setBrush(Qt.GlobalColor.black); p.drawEllipse(12, 7, 2, 2); p.drawEllipse(18, 7, 2, 2)
        p.setBrush(QColor(255, 182, 193)); p.drawEllipse(15, 10, 2, 2)

        p.end()
        return QIcon(pix)

    # ========== 视频播放控制 ==========

    def init_video_player(self):
        self.video_paths = {
            'idle': 'pet_idle.mp4',
            'happy': 'pet_happy.mp4',
            'look': 'pet_look.mp4',
        }
        self.cap = None
        self.timer = QTimer(self, timeout=self.update_frame)

        # 初始化音频播放器
        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)

    def load_video(self, behavior):
        if self.current_behavior == behavior and self.cap:
            return
        if self.cap:
            self.cap.release()
            self.timer.stop()

        # 如果不是happy状态，停止音频
        if behavior != 'happy':
            try:
                self.media_player.stop()
            except Exception:
                pass

        path = self.video_paths.get(behavior)
        if not path or not os.path.exists(path):
            print(f"视频不存在: {path}")
            return

        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            print(f"无法打开: {path}")
            return

        # 切换到happy或idle状态时，重置look状态标志
        if behavior in ['happy', 'idle']:
            self.is_looking = False
            self.look_phase = 0

        self.current_behavior = behavior
        self.timer.start(30)

        # 如果是happy状态，播放音频
        if behavior == 'happy':
            self.play_happy_audio()

    def play_happy_audio(self):
        try:
            audio_path = 'pet_happy.mp3'
            if os.path.exists(audio_path):
                print(f"播放音频: {audio_path}")
                audio_url = QUrl.fromLocalFile(os.path.abspath(audio_path))
                self.media_player.setSource(audio_url)
                self.audio_output.setVolume(1.0)
                self.media_player.play()
                print(f"音频播放中")
            else:
                print(f"音频文件不存在: {audio_path}")
        except Exception as e:
            print(f"音频播放失败: {e}")

    def update_frame(self):
        if not self.cap:
            return

        # 读取视频帧
        if self.look_phase == 2:
            ret, frame = self.cap.read()
            if not ret:
                self.end_look()
                return
            current_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
            if current_frame > 1:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame - 2)
        else:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if not ret:
                    return

        # 去除白色背景（优化边缘减少锯齿）
        frame = self.remove_white_background(frame)

        # BGR转RGB再转RGBA
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)
        h, w, ch = frame.shape

        # 创建QImage并复制数据（避免数据引用问题导致闪烁）
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGBA8888).copy()

        # 高质量缩放
        screen = QApplication.primaryScreen().geometry()
        pix = QPixmap.fromImage(qimg).scaled(
            screen.width() // 3, screen.height() // 3,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # 只在首次显示或尺寸变化时调整窗口大小
        if not hasattr(self, '_prev_size') or self._prev_size != pix.size():
            self.resize(pix.size())
            self._prev_size = pix.size()

        self.label.setPixmap(pix)

    def remove_white_background(self, frame):
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 白色范围（适度检测）
        lower_white = np.array([0, 0, 220])
        upper_white = np.array([180, 30, 255])

        mask = cv2.inRange(hsv, lower_white, upper_white)

        # 形态学操作去除噪点
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 高斯模糊平滑边缘
        mask = cv2.GaussianBlur(mask, (5, 5), 0)

        # 创建alpha通道
        alpha = cv2.bitwise_not(mask)
        
        b, g, r = cv2.split(frame)
        return cv2.merge([b, g, r, alpha])

    # ========== 行为控制 ==========

    def init_behavior(self):
        self.current_behavior = 'idle'
        self.is_looking = False
        self.look_phase = 0

        QTimer(self, timeout=self.trigger_look, interval=6000).start()

    def trigger_look(self):
        if self.current_behavior == 'idle' and not self.is_looking:
            self.is_looking = True
            self.look_phase = 1
            self.load_video('look')

            if self.cap:
                fps = self.cap.get(cv2.CAP_PROP_FPS)
                frame_count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
                duration_ms = int((frame_count / fps) * 1000) if fps > 0 else 3000
                QTimer.singleShot(duration_ms, self.start_look_back)

    def start_look_back(self):
        if not self.is_looking:
            return

        # 如果当前是happy状态，不执行look的第二段
        if self.current_behavior == 'happy':
            print("happy状态中，跳过look第二段")
            return

        self.look_phase = 2

        path = self.video_paths.get('look')
        if path and os.path.exists(path):
            self.cap = cv2.VideoCapture(path)
            if self.cap.isOpened():
                total_frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)

                self.current_behavior = 'look'
                self.timer.start(30)

                fps = self.cap.get(cv2.CAP_PROP_FPS)
                duration_ms = int((total_frames / fps) * 1000) if fps > 0 else 3000
                QTimer.singleShot(duration_ms, self.end_look)

    def end_look(self):
        self.is_looking = False
        self.look_phase = 0
        self.load_video('idle')

    # ========== 事件处理 ==========

    def on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show() if not self.isVisible() else self.hide()

    def enterEvent(self, e):
        # 鼠标进入时触发一次look
        if self.current_behavior == 'idle' and not self.is_looking:
            self.trigger_look()

    def leaveEvent(self, e):
        pass

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.load_video('happy')

    def mouseMoveEvent(self, e):
        if self.dragging:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.load_video('idle')

    def closeEvent(self, e):
        if self.cap:
            self.cap.release()
        self.media_player.stop()
        self.tray.hide()
        e.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    pet = DesktopPet()
    pet.load_video('idle')
    pet.show()

    sys.exit(app.exec())