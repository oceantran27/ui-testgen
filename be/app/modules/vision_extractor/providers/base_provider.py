from abc import ABC, abstractmethod


class BaseVisionProvider(ABC):
    @abstractmethod
    def analyze_image(self, image_path: str) -> str:
        raise NotImplementedError
