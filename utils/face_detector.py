import cv2
import os
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class FaceDetector:
    def __init__(self, min_confidence=0.7):
        # Explicit absolute path
        model_path = r"D:\face_recognition_project\models\blaze_face_short_range.tflite"
        
        if not os.path.exists(model_path):
            print(f"ERROR: Model not found at {model_path}")
            return

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=min_confidence
        )
        
        # This is where the crash happens if protobuf is wrong
        self.detector = vision.FaceDetector.create_from_options(options)

    def detect(self, image):
        # Convert to RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Convert to MediaPipe Image format
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # Run detection
        result = self.detector.detect(mp_image)

        if not result or not result.detections:
            return None

        h, w, _ = image.shape
        boxes = []

        for det in result.detections:
            box = det.bounding_box
            x1 = int(box.origin_x)
            y1 = int(box.origin_y)
            x2 = int(box.origin_x + box.width)
            y2 = int(box.origin_y + box.height)
            boxes.append((x1, y1, x2, y2))

        return boxes