from __future__ import annotations

from typing import Any, Optional


try:
    import cv2
except ImportError:  # OpenCV is optional until camera functions are used.
    cv2 = None


class CameraError(RuntimeError):
    pass


class Camera:
    """OpenCV 摄像头封装，供识别服务调用。"""

    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.capture: Optional[Any] = None

    def open(self) -> "Camera":
        if cv2 is None:
            raise CameraError("未安装 OpenCV，请先执行 pip install opencv-python。")

        self.capture = cv2.VideoCapture(self.index)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            raise CameraError(f"无法打开摄像头：{self.index}")
        return self

    def read_frame(self) -> Any:
        if self.capture is None:
            self.open()
        ok, frame = self.capture.read()
        if not ok:
            raise CameraError("摄像头读取画面失败。")
        return frame

    def release(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def __enter__(self) -> "Camera":
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def capture_one_frame(index: int = 0) -> Any:
    with Camera(index) as camera:
        return camera.read_frame()
