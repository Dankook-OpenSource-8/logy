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

1. 촬영한 이미지를 위 폴더에 라벨별로 넣습니다.
2. `train`과 `val`은 직접 나눕니다. 처음에는 8:2 정도가 무난합니다.
3. 아래 명령으로 classifier head를 학습합니다.

```bash
.venv/bin/python scripts/train_study_classifier.py
```

학습이 끝나면 `models/study_classifier.pt`가 생성되고, 백엔드 AI 검증은 이 모델을 자동으로 함께 사용합니다.
