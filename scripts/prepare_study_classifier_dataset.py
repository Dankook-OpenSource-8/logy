from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


DEFAULT_STUDY_DIR = Path("/Users/jang-yeon-woo/Desktop/study")
DEFAULT_NON_STUDY_DIR = Path("/Users/jang-yeon-woo/Desktop/non")
OUTPUT_DIR = Path("data/study_classifier")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
RANDOM_SEED = 42


def main() -> None:
    parser = argparse.ArgumentParser(
        description="촬영한 study/non 이미지를 학습용 train/val 폴더로 나눕니다."
    )
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--non-study-dir", type=Path, default=DEFAULT_NON_STUDY_DIR)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    args = parser.parse_args()

    if not 0.0 <= args.val_ratio < 1.0:
        raise SystemExit("val-ratio는 0 이상 1 미만 값이어야 합니다.")

    reset_split_dirs()
    study_counts = copy_split(args.study_dir, "study", args.val_ratio)
    non_study_counts = copy_split(args.non_study_dir, "non_study", args.val_ratio)

    print(
        "prepared dataset: "
        f"study train={study_counts[0]} val={study_counts[1]}, "
        f"non_study train={non_study_counts[0]} val={non_study_counts[1]}"
    )


def reset_split_dirs() -> None:
    for split in ("train", "val"):
        for label in ("study", "non_study"):
            label_dir = OUTPUT_DIR / split / label
            label_dir.mkdir(parents=True, exist_ok=True)
            for image_path in label_dir.iterdir():
                if image_path.name == ".gitkeep":
                    continue
                if image_path.is_file():
                    image_path.unlink()


def copy_split(source_dir: Path, label: str, val_ratio: float) -> tuple[int, int]:
    images = collect_images(source_dir)
    if not images:
        raise SystemExit(f"{source_dir} 폴더에 이미지가 없습니다.")

    shuffled_images = images[:]
    random.Random(RANDOM_SEED).shuffle(shuffled_images)
    val_count = round(len(shuffled_images) * val_ratio)
    val_images = set(shuffled_images[:val_count])

    train_total = 0
    val_total = 0
    for index, image_path in enumerate(shuffled_images, start=1):
        split = "val" if image_path in val_images else "train"
        target_name = f"{label}_{index:04d}{image_path.suffix.lower()}"
        target_path = OUTPUT_DIR / split / label / target_name
        shutil.copy2(image_path, target_path)
        if split == "val":
            val_total += 1
        else:
            train_total += 1

    return train_total, val_total


def collect_images(source_dir: Path) -> list[Path]:
    return sorted(
        image_path
        for image_path in source_dir.iterdir()
        if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
    )


if __name__ == "__main__":
    main()
