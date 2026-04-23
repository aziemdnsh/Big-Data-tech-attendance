import cv2
import numpy as np

class AntiSpoof:
    def check(self, face_img):
        # 1. Convert to different color spaces for analysis
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        ycrcb = cv2.cvtColor(face_img, cv2.COLOR_BGR2YCrCb)
        _, cr, cb = cv2.split(ycrcb)

        # 2. Laplacian Variance (Detects blur from paper prints)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # 3. Color Variance (Detects color banding/flatness from screens and paper)
        cr_var = np.var(cr)
        cb_var = np.var(cb)

        # 4. Moiré Pattern Check via Edge Density (Detects digital screen pixels)
        edges = cv2.Canny(gray, 50, 150)
        edge_ratio = np.count_nonzero(edges) / edges.size

        print("\n--- Anti-Spoofing Diagnostics ---")
        print(f"Blur Score (Laplacian): {laplacian_var:.2f}")
        print(f"Skin Color Variance (Cr, Cb): {cr_var:.2f}, {cb_var:.2f}")
        print(f"Screen Noise (Edge Ratio): {edge_ratio:.4f}")
        print("---------------------------------")

        # Condition 1: Low quality / Blurry (Often a paper print)
        if laplacian_var < 40:
            print("❌ Spoof detected: Image too blurry (Possible Paper Print)")
            return False
            
        # Condition 2: High frequency noise / Moiré pattern (Often a screen)
        # High edge ratio or excessively high Laplacian means screen pixels are visible
        if laplacian_var > 800 or edge_ratio > 0.15:
            print("❌ Spoof detected: High-frequency digital screen texture detected")
            return False

        # Condition 3: Unnatural color reproduction (Paper / Screen color gamut limits)
        # Real human faces have variations in skin tone, fakes are flatter
        if cr_var < 15 or cb_var < 15:
            print("❌ Spoof detected: Unnatural skin color variance")
            return False

        print("✅ Anti-Spoof Passed: Real human face characteristics detected.")
        return True