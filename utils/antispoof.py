import cv2
import numpy as np
import os
import sys
import logging

# Set up logging for easier maintenance
logger = logging.getLogger(__name__)

# Define CURRENT_DIR before utilizing it
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Dynamically resolve the path to the MiniVision repository
MINIVISION_PATH = os.path.join(CURRENT_DIR, "Silent-Face-Anti-Spoofing")
if MINIVISION_PATH not in sys.path:
    sys.path.insert(0, MINIVISION_PATH)

try:
    from src.anti_spoof_predict import AntiSpoofPredict  
    from src.generate_patches import CropImage  
    from src.utility import parse_model_name  
    HAS_MINIVISION = True
except ImportError as e:
    print(f"⚠️ MiniVision import failed: {e}")
    HAS_MINIVISION = False


class AntiSpoof:
    def __init__(self, use_gpu: bool = True):
        self.model_dir = os.path.join(MINIVISION_PATH, "resources", "anti_spoof_models")
        self.predictor = None
        self.image_cropper = None
        self.active_mode = "Heuristic"

        logger.debug(f"Looking for MiniVision models in -> {self.model_dir}")
        
        if HAS_MINIVISION and os.path.exists(self.model_dir):
            original_dir = os.getcwd()  # ✅ Save current dir
            try:
                import torch
                device_id = 0 if use_gpu and torch.cuda.is_available() else -1
                
                os.chdir(MINIVISION_PATH)  # ✅ Switch to MiniVision dir
                self.predictor = AntiSpoofPredict(device_id=device_id)
                self.image_cropper = CropImage()
                self.active_mode = "MiniVision"
                logger.info(f"MiniVision AntiSpoof initialized successfully on {'GPU' if device_id == 0 else 'CPU'}.")
            except Exception as e:
                logger.error(f"Failed to initialize MiniVision models: {e}. Falling back to heuristics.")
            finally:
                os.chdir(original_dir)  # ✅ Always restore
        else:
            logger.warning("MiniVision not loaded or models missing! Falling back to heuristic checks.")

    def check(self, image: np.ndarray, bbox: tuple) -> bool:
        if self.active_mode == "MiniVision" and self.predictor and self.image_cropper:
            try:
                return self._minivision_check(image, bbox)
            except Exception as e:
                logger.error(f"MiniVision check failed during runtime: {e}. Falling back to heuristic.")
                
        x1, y1, x2, y2 = bbox
        face_img = image[max(0, y1):y2, max(0, x1):x2]
        return self._heuristic_check(face_img)

    def _minivision_check(self, image: np.ndarray, bbox: tuple) -> bool:
        original_dir = os.getcwd()  # ✅ Save current dir
        os.chdir(MINIVISION_PATH)   # ✅ Switch to MiniVision dir
        try:
            x1, y1, x2, y2 = bbox
            w, h = x2 - x1, y2 - y1
            minivision_bbox = [x1, y1, w, h]

            prediction = np.zeros((1, 3))
            model_count = 0

            model_files = [f for f in os.listdir(self.model_dir) if f.endswith('.pth')]
            
            if not model_files:
                logger.warning("No valid MiniVision models (.pth) found! Falling back to heuristic.")
                return self._heuristic_check(image[max(0, y1):y2, max(0, x1):x2])

            for model_name in model_files:
                h_input, w_input, model_type, scale = parse_model_name(model_name)
                param = {
                    "org_img": image,
                    "bbox": minivision_bbox,
                    "scale": scale,
                    "out_w": w_input,
                    "out_h": h_input,
                    "crop": scale is not None,
                }

                img = self.image_cropper.crop(**param)
                model_path = os.path.join(self.model_dir, model_name)
                prediction += self.predictor.predict(img, model_path)
                model_count += 1

            label = np.argmax(prediction)
            value = prediction[0][label] / model_count

            if label == 1 and value > 0.85:
                logger.info(f"Anti-Spoof Passed: Real human face (MiniVision Conf: {value:.2f}).")
                return True
                
            logger.info(f"Spoof detected: Confidence {value:.2f} for class {label}")
            return False

        finally:
            os.chdir(original_dir)  # ✅ Always restore

    def _heuristic_check(self, face_img: np.ndarray) -> bool:
        if face_img is None or face_img.size == 0:
            logger.warning("Empty face image passed to heuristic check.")
            return False

        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        ycrcb = cv2.cvtColor(face_img, cv2.COLOR_BGR2YCrCb)
        _, cr, cb = cv2.split(ycrcb)

        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        cr_var = np.var(cr)
        cb_var = np.var(cb)
        
        edges = cv2.Canny(gray, 50, 150)
        edge_ratio = np.count_nonzero(edges) / edges.size if edges.size > 0 else 0

        print("\n--- Anti-Spoofing Heuristic Diagnostics ---")
        print(f"Blur Score (Laplacian): {laplacian_var:.2f}")
        print(f"Skin Color Variance (Cr, Cb): {cr_var:.2f}, {cb_var:.2f}")
        print(f"Screen Noise (Edge Ratio): {edge_ratio:.4f}")
        print("-----------------------------------------")

        if laplacian_var < 40:
            print("❌ Spoof detected: Image too blurry (Possible Paper Print)")
            return False
            
        if laplacian_var > 800 or edge_ratio > 0.15:
            print("❌ Spoof detected: High-frequency digital screen texture detected")
            return False

        if cr_var < 15 or cb_var < 15:
            print("❌ Spoof detected: Unnatural skin color variance")
            return False

        print("✅ Anti-Spoof Passed: Real human face characteristics detected.")
        return True