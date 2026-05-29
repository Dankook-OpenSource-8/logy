from pathlib import Path


CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
DATASET_DIR = Path("data/study_classifier")
OUTPUT_PATH = Path("models/study_classifier.pt")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
LABELS = {"non_study": 0, "study": 1}


def main() -> None:
    import torch
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset
    from transformers import CLIPModel, CLIPProcessor

    train_samples = collect_samples(DATASET_DIR / "train")
    val_samples = collect_samples(DATASET_DIR / "val")
    if not train_samples:
        raise SystemExit("train 폴더에 학습 이미지가 없습니다.")
    if not val_samples:
        raise SystemExit("val 폴더에 검증 이미지가 없습니다.")

    processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME, local_files_only=True)
    clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME, local_files_only=True)
    clip_model.eval()
    for parameter in clip_model.parameters():
        parameter.requires_grad = False

    train_dataset = StudyImageDataset(train_samples, processor)
    val_dataset = StudyImageDataset(val_samples, processor)
    train_loader = DataLoader(train_dataset, batch_size=8, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=8)

    input_dim = clip_model.config.projection_dim
    classifier_head = torch.nn.Linear(input_dim, 2)
    optimizer = torch.optim.AdamW(classifier_head.parameters(), lr=1e-3)
    loss_fn = torch.nn.CrossEntropyLoss()

    for epoch in range(1, 11):
        train_loss = train_one_epoch(
            clip_model,
            classifier_head,
            train_loader,
            optimizer,
            loss_fn,
            torch,
        )
        val_accuracy = evaluate(clip_model, classifier_head, val_loader, torch)
        print(
            f"epoch={epoch} train_loss={train_loss:.4f} "
            f"val_accuracy={val_accuracy:.3f}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "clip_model_name": CLIP_MODEL_NAME,
            "input_dim": input_dim,
            "label_names": ["non_study", "study"],
            "classifier_state_dict": classifier_head.state_dict(),
        },
        OUTPUT_PATH,
    )
    print(f"saved: {OUTPUT_PATH}")


class StudyImageDataset:
    def __init__(self, samples: list[tuple[Path, int]], processor):
        self.samples = samples
        self.processor = processor

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        import torch
        from PIL import Image

        image_path, label = self.samples[index]
        image = Image.open(image_path).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].squeeze(0)
        return pixel_values, torch.tensor(label, dtype=torch.long)


def collect_samples(split_dir: Path) -> list[tuple[Path, int]]:
    samples: list[tuple[Path, int]] = []
    for label_name, label_id in LABELS.items():
        label_dir = split_dir / label_name
        for image_path in sorted(label_dir.glob("*")):
            if image_path.suffix.lower() in IMAGE_EXTENSIONS:
                samples.append((image_path, label_id))
    return samples


def train_one_epoch(
    clip_model,
    classifier_head,
    loader,
    optimizer,
    loss_fn,
    torch,
) -> float:
    classifier_head.train()
    total_loss = 0.0
    for pixel_values, labels in loader:
        with torch.no_grad():
            image_features = clip_model.get_image_features(pixel_values=pixel_values)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        logits = classifier_head(image_features)
        loss = loss_fn(logits, labels)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        total_loss += float(loss)

    return total_loss / max(1, len(loader))


def evaluate(clip_model, classifier_head, loader, torch) -> float:
    classifier_head.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for pixel_values, labels in loader:
            image_features = clip_model.get_image_features(pixel_values=pixel_values)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            predictions = classifier_head(image_features).argmax(dim=1)
            correct += int((predictions == labels).sum())
            total += int(labels.numel())

    return correct / total if total else 0.0


if __name__ == "__main__":
    main()
