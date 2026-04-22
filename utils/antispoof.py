import cv2
import numpy as np

class AntiSpoof:
    def check(self, face_img):
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        print(f"--- AntiSpoof Debug: Variance = {laplacian_var:.2f} ---")

        # 1. Check for low-quality prints (Blurry)
        if laplacian_var < 35:
            print("Spoof detected: Image too blurry (Possible Print)")
            return False
            
        # 2. Check for digital screen 'noise' 
        # High-res screens often produce variance > 800 in small crops
        if laplacian_var > 700:
            print("Spoof detected: Digital screen texture detected")
            return False

        return True