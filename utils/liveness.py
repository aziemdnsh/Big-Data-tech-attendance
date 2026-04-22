import cv2
import numpy as np
import mediapipe as mp

class LivenessDetector:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )

    def check(self, face_img):
        rgb_image = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_image)

        if not results.multi_face_landmarks:
            return False

        # Get landmarks for the first face detected
        landmarks = results.multi_face_landmarks[0].landmark
        
        # 1. DEPTH DIFFERENTIAL CHECK
        # Index 1: Nose tip | Index 234: Left Ear | Index 454: Right Ear
        nose_z = landmarks[1].z
        left_ear_z = landmarks[234].z
        right_ear_z = landmarks[454].z
        
        # Average depth of the sides of the face
        avg_side_z = (left_ear_z + right_ear_z) / 2
        
        # The 'Protrusion' value: How much the nose sticks out compared to the ears
        # On a flat screen, this value will be extremely small (close to 0)
        depth_diff = abs(nose_z - avg_side_z)

        # 2. CALIBRATION PRINT
        # Look at your terminal while showing the phone vs your real face
        print(f"DEBUG -> Depth Diff: {depth_diff:.5f}")

        # 3. STRICT THRESHOLD
        # Increase this value if the phone is still passing. 
        # Real faces usually score > 0.05. Screens/Photos usually score < 0.02.
        if depth_diff < 0.02: 
            print("Liveness Failed: Flat surface detected.")
            return False

        print("Liveness Passed: 3D Geometry confirmed.")
        return True