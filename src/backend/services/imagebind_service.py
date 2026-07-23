import logging
import os
import tempfile
from pathlib import Path

import torch

from .base_embedding_service import BaseEmbeddingService

logger = logging.getLogger(__name__)

# ImageBind has no native video loader: we sample this many frames per clip,
# embed each through the vision path, then mean-pool into one clip vector
VIDEO_FRAME_SAMPLES = 5


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


class ImageBindService(BaseEmbeddingService):
    def get_model_type(self) -> str:
        return "imagebind"

    def load_model(self):
        logger.info("Loading ImageBind model (imagebind_huge)")
        try:
            from imagebind import data as imagebind_data
            from imagebind.models import imagebind_model
            from imagebind.models.imagebind_model import ModalityType

            self._data = imagebind_data
            self._ModalityType = ModalityType
            self.model = imagebind_model.imagebind_huge(pretrained=True)
            self.model.eval()
            self.model.to(self.device)
            # Kept for interface parity; ImageBind has no separate processor.
            self.processor = imagebind_data
            logger.info(f"ImageBind model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading ImageBind model: {str(e)}")
            raise

    def _embed(self, modality, inputs) -> torch.Tensor:
        with torch.no_grad():
            embeddings = self.model({modality: inputs})[modality]
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
        return embeddings.cpu()

    def encode_text(self, texts) -> torch.Tensor:
        if isinstance(texts, str):
            texts = [texts]
        inputs = self._data.load_and_transform_text(list(texts), self.device)
        return self._embed(self._ModalityType.TEXT, inputs)

    def encode_image(self, image) -> torch.Tensor:
        paths, cleanup = self._as_image_paths(image)
        try:
            inputs = self._data.load_and_transform_vision_data(paths, self.device)
            return self._embed(self._ModalityType.VISION, inputs)
        finally:
            for p in cleanup:
                _safe_unlink(p)

    def encode_audio(self, audio) -> torch.Tensor:
        paths = self._as_str_paths(audio)
        inputs = self._data.load_and_transform_audio_data(paths, self.device)
        return self._embed(self._ModalityType.AUDIO, inputs)

    def encode_video(self, video) -> torch.Tensor:
        paths = self._as_str_paths(video)
        vectors = []
        for path in paths:
            frame_paths = self._sample_video_frames(path, VIDEO_FRAME_SAMPLES)
            try:
                frame_inputs = self._data.load_and_transform_vision_data(
                    frame_paths, self.device
                )
                frame_embs = self._embed(self._ModalityType.VISION, frame_inputs)
                pooled = frame_embs.mean(dim=0)
                pooled = pooled / pooled.norm(dim=-1, keepdim=True)
                vectors.append(pooled)
            finally:
                for fp in frame_paths:
                    _safe_unlink(fp)
        return torch.stack(vectors, dim=0)

    def transform_score(self, similarities: torch.Tensor) -> torch.Tensor:
        """
        ImageBind embeddings are unit-normalized, so the raw dot product is
        already cosine similarity — the correct ranking metric. Unlike CLIP /
        SigLIP there is no logit_scale/logit_bias, so we return scores as-is.
        """
        return similarities

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _as_str_paths(value) -> list:
        """Normalize a path or iterable of paths to a list of strings."""
        if isinstance(value, (str, Path)):
            return [str(value)]
        return [str(v) for v in value]

    @staticmethod
    def _as_image_paths(image):
        """
        Return (paths, cleanup) where PIL images are written to temp files.

        ImageBind's ``load_and_transform_vision_data`` opens paths from disk,
        but the image-upload search path passes an in-memory PIL image, so we
        materialize those to temporary JPEGs and report them for cleanup.
        """
        from PIL import Image as PILImage

        items = image if isinstance(image, (list, tuple)) else [image]
        paths = []
        cleanup = []
        for item in items:
            if isinstance(item, (str, Path)):
                paths.append(str(item))
            elif isinstance(item, PILImage.Image):
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                item.convert("RGB").save(tmp.name, "JPEG")
                tmp.close()
                paths.append(tmp.name)
                cleanup.append(tmp.name)
            else:
                raise TypeError(f"Unsupported image input type: {type(item)}")
        return paths, cleanup

    @staticmethod
    def _sample_video_frames(path: str, n: int) -> list:
        """Extract up to ``n`` evenly spaced frames, saved as temp JPEGs"""
        import imageio
        from PIL import Image as PILImage

        frame_paths = []
        reader = imageio.get_reader(path)
        try:
            try:
                total = reader.count_frames()
            except Exception:
                total = 0

            if not total or total == float("inf") or total <= 0:
                meta = reader.get_meta_data()
                fps = meta.get("fps") or 25
                duration = meta.get("duration") or 0
                total = int(fps * duration) if duration else 0

            if total and total > 0:
                step = max(total // (n + 1), 1)
                indices = [min((i + 1) * step, total - 1) for i in range(n)]
            else:
                # Unknown length: fall back to the first n frames sequentially.
                indices = list(range(n))

            for idx in indices:
                try:
                    frame = reader.get_data(idx)
                except Exception:
                    break
                img = PILImage.fromarray(frame).convert("RGB")
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                img.save(tmp.name, "JPEG")
                tmp.close()
                frame_paths.append(tmp.name)
        finally:
            reader.close()

        if not frame_paths:
            raise RuntimeError(f"Could not extract frames from video: {path}")
        return frame_paths
