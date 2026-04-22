import insightface
import numpy as np

class FaceEmbedder:
    def __init__(self):
        self.model = insightface.app.FaceAnalysis()
        self.model.prepare(ctx_id=0)

    def get_embedding(self, image):
        faces = self.model.get(image)
        if len(faces) == 0:
            return None

        return faces[0].embedding