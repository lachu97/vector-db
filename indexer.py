# indexer.py
import hnswlib
import numpy as np
import threading
import os

class HNSWIndexer:
    def __init__(self, dim=384, space='cosine', max_elements=10000, index_path='index.bin'):
        self.dim = dim
        self.space = space
        self.index_path = index_path
        self.lock = threading.Lock()
        self.index = hnswlib.Index(space=self.space, dim=self.dim)
        # load if exists, else init
        if os.path.exists(self.index_path):
            self.index.load_index(self.index_path)
            # optionally resize if your expected max > saved max; you can call resize_index()
        else:
            self.index.init_index(max_elements=max_elements, ef_construction=200, M=16)
        self.index.set_ef(50)  # query-time tradeoff (increase for recall)

    def add_item(self, vector: np.ndarray, internal_id: int):
        v = vector.astype(np.float32).reshape(1, -1)
        with self.lock:
            try:
                self.index.add_items(v, np.array([internal_id], dtype=np.int32))
            except RuntimeError:
                # resize if needed
                curr = self.index.get_max_elements()
                new_max = max(curr * 2, curr + 1)
                self.index.resize_index(new_max)
                self.index.add_items(v, np.array([internal_id], dtype=np.int32))

    def add_items(self, vectors: np.ndarray, ids: np.ndarray):
        vectors = vectors.astype(np.float32)
        ids = ids.astype(np.int32)
        with self.lock:
            needed = self.index.get_current_count() + len(ids) - self.index.get_max_elements()
            if needed > 0:
                new_max = max(self.index.get_max_elements() * 2, self.index.get_current_count() + len(ids))
                self.index.resize_index(new_max)
            self.index.add_items(vectors, ids)

    def knn_query(self, vector: np.ndarray, k: int = 10):
        q = vector.astype(np.float32).reshape(1, -1)
        with self.lock:
            labels, distances = self.index.knn_query(q, k=k)
        return labels[0].tolist(), distances[0].tolist()

    def mark_deleted(self, internal_id: int):
        with self.lock:
            # hnswlib supports mark_deleted for labels
            self.index.mark_deleted(int(internal_id))

    def save(self):
        with self.lock:
            self.index.save_index(self.index_path)

    def get_current_count(self):
        return self.index.get_current_count()


    def load(self):
        if os.path.exists(self.index_path):
            self.index.load_index(self.index_path)