from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from util.camera import Camera, CameraError, cv2
from util.io_tools import DATA_DIR, load_json_file, save_json_file


FaceBox = Tuple[int, int, int, int]
FACE_SIZE = (160, 160)
FACE_DIR = DATA_DIR / "faces"
FACE_MODEL_FILE = DATA_DIR / "face_model.yml"
FACE_LABEL_FILE = DATA_DIR / "face_labels.json"
FACE_CONFIDENCE_THRESHOLD = 78.0


class RecognizeService:
    """
    人脸识别服务入口。

    - 未训练模型时：只做人脸检测并画框。
    - 采集样本并训练后：使用 OpenCV LBPH 识别人员编号。
    """

    def __init__(self) -> None:
        self.face_cascade = None
        self.recognizer = None
        self.labels: Dict[str, str] = {}
        if cv2 is not None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(cascade_path)
            if not cascade.empty():
                self.face_cascade = cascade
            self._load_model()

    @property
    def face_detection_available(self) -> bool:
        return self.face_cascade is not None

    @property
    def face_recognition_available(self) -> bool:
        return self.recognizer is not None and bool(self.labels)

    def _new_recognizer(self) -> Any:
        if cv2 is None or not hasattr(cv2, "face"):
            return None
        creator = getattr(cv2.face, "LBPHFaceRecognizer_create", None)
        if creator is None:
            return None
        return creator(radius=1, neighbors=8, grid_x=8, grid_y=8)

    def _load_model(self) -> None:
        recognizer = self._new_recognizer()
        if recognizer is None or not FACE_MODEL_FILE.exists() or not FACE_LABEL_FILE.exists():
            return
        try:
            recognizer.read(str(FACE_MODEL_FILE))
            labels = load_json_file(FACE_LABEL_FILE, {})
        except Exception:
            return
        if isinstance(labels, dict):
            self.recognizer = recognizer
            self.labels = {str(key): str(value) for key, value in labels.items()}

    def detect_faces(self, frame: object) -> List[FaceBox]:
        if cv2 is None or self.face_cascade is None:
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(60, 60),
        )
        return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]

    def _prepare_face(self, frame: object, face: FaceBox) -> np.ndarray:
        x, y, w, h = face
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_img = gray[y : y + h, x : x + w]
        face_img = cv2.resize(face_img, FACE_SIZE)
        face_img = cv2.equalizeHist(face_img)
        return face_img

    def _largest_face(self, frame: object) -> Optional[FaceBox]:
        faces = self.detect_faces(frame)
        if not faces:
            return None
        return max(faces, key=lambda item: item[2] * item[3])

    def save_face_sample(self, person_id: str, frame: object) -> Dict[str, Any]:
        person_id = person_id.strip()
        if not person_id:
            raise ValueError("人员编号不能为空。")
        if cv2 is None:
            raise ValueError("未安装 OpenCV。")

        face = self._largest_face(frame)
        if face is None:
            raise ValueError("当前画面没有检测到人脸，请正对摄像头后再采集。")

        face_img = self._prepare_face(frame, face)
        person_dir = FACE_DIR / person_id
        person_dir.mkdir(parents=True, exist_ok=True)
        sample_path = person_dir / f"{int(time.time() * 1000)}.jpg"
        cv2.imwrite(str(sample_path), face_img)
        sample_count = len(list(person_dir.glob("*.jpg")))
        return {
            "person_id": person_id,
            "sample_count": sample_count,
            "path": str(sample_path),
        }

    def train_model(self) -> Dict[str, Any]:
        if cv2 is None:
            raise ValueError("未安装 OpenCV。")
        recognizer = self._new_recognizer()
        if recognizer is None:
            raise ValueError("当前 OpenCV 缺少 cv2.face，请安装 opencv-contrib-python。")

        images: List[np.ndarray] = []
        labels: List[int] = []
        label_map: Dict[str, str] = {}
        next_label = 1

        FACE_DIR.mkdir(parents=True, exist_ok=True)
        for person_dir in sorted(path for path in FACE_DIR.iterdir() if path.is_dir()):
            person_images = sorted(person_dir.glob("*.jpg"))
            if not person_images:
                continue
            label = next_label
            next_label += 1
            label_map[str(label)] = person_dir.name
            for image_path in person_images:
                image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                if image is None:
                    continue
                images.append(image)
                labels.append(label)

        if not images:
            raise ValueError("还没有可训练的人脸样本。请先采集人脸。")

        recognizer.train(images, np.array(labels, dtype=np.int32))
        FACE_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        recognizer.write(str(FACE_MODEL_FILE))
        save_json_file(FACE_LABEL_FILE, label_map)
        self.recognizer = recognizer
        self.labels = label_map
        return {
            "person_count": len(label_map),
            "sample_count": len(images),
            "model_path": str(FACE_MODEL_FILE),
        }

    def recognize_faces(self, frame: object) -> List[Dict[str, Any]]:
        faces = self.detect_faces(frame)
        results: List[Dict[str, Any]] = []
        for face in faces:
            result: Dict[str, Any] = {
                "box": face,
                "person_id": None,
                "confidence": None,
                "recognized": False,
            }
            if self.face_recognition_available:
                face_img = self._prepare_face(frame, face)
                label, confidence = self.recognizer.predict(face_img)
                person_id = self.labels.get(str(label))
                result["person_id"] = person_id
                result["confidence"] = round(float(confidence), 2)
                result["recognized"] = bool(person_id and confidence <= FACE_CONFIDENCE_THRESHOLD)
            results.append(result)
        return results

    def recognize_from_frame(self, frame: object) -> Optional[Tuple[str, str]]:
        for result in self.recognize_faces(frame):
            if result["recognized"] and result["person_id"]:
                person_id = str(result["person_id"])
                return person_id, person_id
        return None

    def best_recognition(self, frame: object) -> Dict[str, Any]:
        results = self.recognize_faces(frame)
        recognized = [item for item in results if item["recognized"] and item.get("person_id")]
        if recognized:
            recognized.sort(key=lambda item: float(item.get("confidence") or 9999))
            best = recognized[0]
            return {
                "recognized": True,
                "person_id": best["person_id"],
                "confidence": best["confidence"],
                "face_count": len(results),
            }
        return {
            "recognized": False,
            "person_id": None,
            "confidence": None,
            "face_count": len(results),
        }

    def annotate_frame(self, frame: object) -> Tuple[object, int, Optional[Dict[str, Any]]]:
        results = self.recognize_faces(frame)
        best: Optional[Dict[str, Any]] = None
        if cv2 is None:
            return frame, 0, None
        for result in results:
            x, y, w, h = result["box"]
            color = (35, 211, 166) if result["recognized"] else (31, 182, 255)
            label = "FACE"
            if result["recognized"] and result.get("person_id"):
                label = str(result["person_id"])
                if best is None:
                    best = result
            elif result.get("confidence") is not None:
                label = "UNKNOWN"
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame,
                label,
                (x, max(24, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
                cv2.LINE_AA,
            )
        return frame, len(results), best

    def recognize_from_camera(self, camera_index: int = 0) -> Optional[Tuple[str, str]]:
        try:
            with Camera(camera_index) as camera:
                frame = camera.read_frame()
        except CameraError as exc:
            print(exc)
            return None
        return self.recognize_from_frame(frame)

    def manual_fallback(self) -> Tuple[str, str]:
        person_id = input("人员编号: ").strip()
        person_name = input("人员姓名（可直接回车使用编号）: ").strip() or person_id
        return person_id, person_name
