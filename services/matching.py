from difflib import SequenceMatcher
from pathlib import Path

import imagehash
from PIL import Image
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def text_similarity(a, b):
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2)).fit_transform([a, b])
        tfidf_score = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except ValueError:
        tfidf_score = 0.0
    return max(tfidf_score, SequenceMatcher(None, a, b).ratio() * 0.45)


def image_similarity(path_a, path_b):
    """Perceptual image similarity. This is a baseline, not semantic AI."""
    if not path_a or not path_b:
        return None
    try:
        with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
            hash_a = imagehash.phash(img_a.convert("RGB"))
            hash_b = imagehash.phash(img_b.convert("RGB"))
        distance = hash_a - hash_b
        max_distance = len(hash_a.hash)  # usually 64 bits
        return max(0.0, 1.0 - distance / max_distance)
    except (OSError, ValueError):
        return None


def score_items(lost, found, upload_dir):
    parts = []
    weights = []

    # Compare combined descriptive fields.
    lost_text = " ".join([lost.title, lost.category, lost.color, lost.location, lost.description or ""])
    found_text = " ".join([found.title, found.category, found.color, found.location, found.description or ""])
    parts.append(text_similarity(lost_text, found_text))
    weights.append(0.55)

    if lost.category and found.category:
        parts.append(1.0 if lost.category.lower() == found.category.lower() else 0.0)
        weights.append(0.15)
    if lost.color and found.color:
        parts.append(1.0 if lost.color.lower() == found.color.lower() else 0.0)
        weights.append(0.10)

    if lost.image_filename and found.image_filename:
        p1 = Path(upload_dir) / lost.image_filename
        p2 = Path(upload_dir) / found.image_filename
        visual = image_similarity(p1, p2)
        if visual is not None:
            parts.append(visual)
            weights.append(0.20)

    total_weight = sum(weights)
    return round(100 * sum(s * w for s, w in zip(parts, weights)) / total_weight)
