# Study Classifier Dataset

팀이 직접 촬영한 이미지로 AI 인증 분류기를 학습하기 위한 폴더입니다.

## 폴더 구조

```text
data/study_classifier/
  train/
    study/
    non_study/
  val/
    study/
    non_study/
```

## 라벨 기준

- `study`: 책, 노트, 문제 풀이, 강의 화면, 코딩 공부, 태블릿 필기처럼 실제 공부 맥락이 보이는 이미지
- `non_study`: 게임, SNS, 메신저, 쇼핑, 엔터테인먼트 영상, 단순 빈 책상처럼 공부 인증으로 보기 어려운 이미지

## 사용 방법

1. 촬영한 이미지를 `study`, `non` 폴더에 라벨별로 모읍니다.
2. 아래 명령으로 이미지를 `train`과 `val`에 8:2 비율로 나눕니다.

```bash
.venv/bin/python scripts/prepare_study_classifier_dataset.py
```

3. 아래 명령으로 classifier head를 학습합니다.

```bash
.venv/bin/python scripts/train_study_classifier.py
```

학습이 끝나면 `models/study_classifier.pt`가 생성되고, 백엔드 AI 검증은 이 모델을 자동으로 함께 사용합니다.

이미지 원본은 용량이 커서 Git에는 올리지 않습니다. 재학습이 필요하면 로컬 이미지 폴더에서 다시 준비 스크립트를 실행합니다.
