import shutil
import subprocess
import tempfile
import time
import urllib.request
import uuid
import os
import multiprocessing as mp
import re
from dataclasses import dataclass
from pathlib import Path

from core.study_image_classifier import score_with_study_classifier


FRAME_TIMESTAMPS = (1.5, 3.5)
OCR_MAX_DIMENSION = 960
OCR_TIMEOUT_SECONDS = 40
OCR_SERVER_TIMEOUT_SECONDS = 45
VERIFICATION_TIMEOUT_SECONDS = 60
APPROVAL_THRESHOLD = 65
RETAKE_THRESHOLD = 50
SCENE_SCORE_MAX = 60
TEXT_SCORE_MAX = 40
DEFAULT_TEXT_SCORE = 0
STRONG_TEXT_SCORE = 36
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

STUDY_PROMPTS = (
    "a person studying with books and notes",
    "a person studying on a laptop",
    "a person studying on a tablet",
    "a laptop screen showing handwritten study notes",
    "a digital notebook with math equations and diagrams",
    "a person reading a textbook",
    "a person solving problems on paper",
    "a person solving math equations",
    "a desk with study materials and handwritten notes",
    "an online lecture or educational document on a screen",
    "a code editor or programming lecture used for studying",
    "a laptop screen showing charts, graphs, or analytical data for studying",
    "a person studying finance, economics, or market analysis on a laptop",
    "educational charts and graphs on a computer screen",
)

FORBIDDEN_PROMPTS = (
    "a person playing a video game",
    "a social media feed on a phone or computer",
    "an entertainment video or movie on a screen",
    "an online shopping website",
    "a chat messenger conversation",
    "a music video or streaming platform for entertainment",
    "a stock trading app used for buying and selling stocks",
)

SUBJECT_ALIASES = {
    # OCR은 한국어 과목명보다 화면 속 영문 약어를 더 잘 잡는 경우가 많아 보조 키워드만 가볍게 붙입니다.
    "컴퓨터구조": "computer architecture cpu cache memory pipeline branch instruction datapath register alu if id ex mem store load hazard control",
    "자료구조": "data structure hash bucket collision graph tree stack queue heap dfs bfs connected component",
    "알고리즘": "algorithm dynamic programming greedy graph shortest path minimum spanning tree prim kruskal connected component",
    "데이터베이스": "database sql erd entity relation table customer primary key foreign key query ddl dml schema",
    "선형대수": "linear algebra vector matrix scalar basis span transformation eigenvalue determinant multiplication",
    "운영체제": "operating system process thread scheduler scheduling deadlock semaphore mutex memory paging virtual memory kernel file system",
    "컴퓨터네트워크": "computer network tcp ip udp http dns packet routing router switch subnet osi congestion socket",
    "네트워크": "network tcp ip udp http dns packet routing router switch subnet osi congestion socket",
    "소프트웨어공학": "software engineering requirement design pattern uml use case testing agile scrum architecture refactoring",
    "웹프로그래밍": "web programming html css javascript typescript react node api request response dom component state",
    "프로그래밍": "programming code function variable class object loop array list python java c javascript typescript",
    "자바프로그래밍": "java programming object oriented oop class interface inheritance extends implements method constructor override polymorphism abstract collection exception package",
    "파이썬프로그래밍": "python programming function class list dictionary tuple module package pandas numpy exception file input output",
    "C프로그래밍": "c programming pointer array struct function malloc printf scanf header compiler memory address",
    "객체지향프로그래밍": "object oriented programming oop class object interface inheritance polymorphism encapsulation abstraction method constructor override",
    "모바일프로그래밍": "mobile programming android ios kotlin swift activity view lifecycle intent layout app",
    "앱프로그래밍": "app programming android ios kotlin swift activity view lifecycle intent layout mobile",
    "인공지능": "artificial intelligence machine learning deep learning neural network model training inference classification regression",
    "머신러닝": "machine learning dataset feature label train validation test accuracy loss classifier regression clustering",
    "딥러닝": "deep learning neural network cnn rnn transformer backpropagation gradient loss optimizer pytorch tensorflow",
    "컴퓨터그래픽스": "computer graphics rendering shader texture mesh vertex fragment ray tracing transformation projection opengl",
    "영상처리": "image processing pixel filter convolution edge histogram segmentation threshold fourier opencv",
    "컴파일러": "compiler lexer parser grammar syntax semantic token ast code generation optimization",
    "정보보호": "information security cryptography encryption decryption hash signature authentication attack vulnerability",
    "암호학": "cryptography encryption decryption rsa aes key hash signature public private modular",
    "이산수학": "discrete mathematics logic proposition set relation function graph tree proof induction combinatorics recurrence",
    "오토마타": "automata formal language regular expression dfa nfa grammar turing machine state transition",
    "시스템프로그래밍": "system programming linux unix process thread system call file descriptor memory shell gcc make",
    "임베디드시스템": "embedded system microcontroller firmware sensor actuator interrupt timer gpio uart i2c spi",
    "마이크로프로세서": "microprocessor microcontroller cpu register assembly instruction interrupt bus memory arm avr",
    "자료통신": "data communication signal modulation encoding bandwidth channel noise transmission protocol",
    "분산시스템": "distributed system consensus replication fault tolerance cluster node rpc message queue consistency",
    "클라우드컴퓨팅": "cloud computing virtualization container docker kubernetes aws serverless deployment scaling",
    "데이터마이닝": "data mining association rule clustering classification decision tree frequent pattern preprocessing",
    "빅데이터": "big data hadoop spark mapreduce distributed storage dataframe etl pipeline",
    "인간컴퓨터상호작용": "human computer interaction hci usability user experience ux interface prototype evaluation affordance",
    "통계": "statistics probability distribution mean variance standard deviation hypothesis p value regression correlation sample",
    "확률": "probability random variable distribution expectation variance bayes conditional probability sample event",
    "미적분": "calculus limit derivative integral differentiation integration series partial derivative gradient",
    "공업수학": "engineering mathematics differential equation laplace fourier matrix vector eigenvalue series transform",
    "미분방정식": "differential equation ode pde laplace solution initial value boundary condition homogeneous",
    "수치해석": "numerical analysis interpolation approximation error root finding newton method matrix iteration",
    "회계": "accounting asset liability equity revenue expense debit credit balance sheet income statement journal",
    "재무회계": "financial accounting asset liability equity revenue expense debit credit balance sheet income statement journal",
    "관리회계": "managerial accounting cost budget variance break even contribution margin cvp standard costing",
    "경제": "economics demand supply elasticity market price cost revenue monopoly inflation gdp interest rate",
    "미시경제": "microeconomics demand supply elasticity utility consumer producer market monopoly cost marginal",
    "거시경제": "macroeconomics gdp inflation unemployment interest rate monetary fiscal aggregate demand supply",
    "경영": "management strategy organization operation finance marketing leadership swot kpi performance decision",
    "마케팅": "marketing segmentation targeting positioning brand customer promotion price product place campaign conversion",
    "재무관리": "finance present value future value cash flow interest rate npv irr portfolio risk return",
    "생산운영관리": "operations management production inventory queue capacity scheduling process quality supply chain lead time",
    "조직행동론": "organizational behavior motivation leadership team culture communication decision conflict performance",
    "물리": "physics force energy momentum velocity acceleration wave electric magnetic quantum equation",
    "화학": "chemistry molecule atom reaction bond acid base equilibrium concentration molar electron",
    "생명과학": "biology cell dna rna protein enzyme gene chromosome metabolism organism evolution",
    "전자회로": "electronic circuit voltage current resistance capacitor transistor diode op amp frequency signal",
    "디지털논리": "digital logic boolean gate flip flop latch mux decoder encoder truth table karnaugh",
    "제어공학": "control engineering feedback transfer function stability pid laplace bode root locus system response",
    "신호및시스템": "signals systems signal convolution fourier laplace frequency impulse response sampling filter",
}

SUBJECT_CORE_KEYWORDS = {
    "컴퓨터구조": {
        "alu",
        "cache",
        "cpu",
        "datapath",
        "instruction",
        "memory hierarchy",
        "pipeline",
        "register",
        "명령어",
        "메모리 계층",
        "레지스터",
        "캐시",
        "파이프라인",
    },
    "자료구조": {
        "array",
        "bfs",
        "dfs",
        "graph",
        "hash",
        "heap",
        "queue",
        "stack",
        "tree",
        "그래프",
        "스택",
        "자료구조",
        "큐",
        "트리",
        "해시",
        "힙",
    },
    "알고리즘": {
        "algorithm",
        "dynamic programming",
        "greedy",
        "kruskal",
        "mst",
        "prim",
        "shortest path",
        "그리디",
        "동적계획",
        "알고리즘",
        "최단경로",
    },
    "데이터베이스": {
        "database",
        "dbms",
        "dml",
        "ddl",
        "erd",
        "foreign key",
        "index",
        "primary key",
        "query",
        "relation",
        "schema",
        "sql",
        "transaction",
        "관계",
        "데이터베이스",
        "릴레이션",
        "스키마",
        "인덱스",
        "정규화",
        "질의",
        "트랜잭션",
    },
    "선형대수": {
        "basis",
        "determinant",
        "eigenvalue",
        "linear",
        "matrix",
        "scalar",
        "span",
        "vector",
        "기저",
        "벡터",
        "선형",
        "스칼라",
        "행렬",
    },
    "운영체제": {
        "deadlock",
        "kernel",
        "mutex",
        "paging",
        "process",
        "scheduler",
        "semaphore",
        "thread",
        "virtual memory",
        "가상메모리",
        "교착",
        "스레드",
        "스케줄링",
        "운영체제",
        "커널",
        "프로세스",
        "페이징",
    },
    "컴퓨터네트워크": {
        "dns",
        "http",
        "ip",
        "network",
        "packet",
        "routing",
        "socket",
        "tcp",
        "udp",
        "네트워크",
        "라우팅",
        "소켓",
        "패킷",
    },
    "네트워크": {
        "dns",
        "http",
        "ip",
        "network",
        "packet",
        "routing",
        "socket",
        "tcp",
        "udp",
        "네트워크",
        "라우팅",
        "소켓",
        "패킷",
    },
    "소프트웨어공학": {
        "agile",
        "architecture",
        "requirement",
        "scrum",
        "software engineering",
        "testing",
        "uml",
        "use case",
        "소프트웨어공학",
        "요구사항",
        "테스트",
    },
    "웹프로그래밍": {
        "api",
        "css",
        "dom",
        "html",
        "javascript",
        "node",
        "react",
        "typescript",
        "웹",
        "컴포넌트",
    },
    "프로그래밍": {
        "array",
        "class",
        "code",
        "function",
        "java",
        "javascript",
        "python",
        "variable",
        "객체",
        "배열",
        "변수",
        "클래스",
        "함수",
    },
    "자바프로그래밍": {
        "abstract",
        "class",
        "completecalc",
        "constructor",
        "extends",
        "implements",
        "interface",
        "java",
        "method",
        "object",
        "override",
        "polymorphism",
        "객체",
        "객체지향",
        "구현",
        "메서드",
        "상속",
        "생성자",
        "오버라이드",
        "인터페이스",
        "자바",
        "클래스",
    },
    "파이썬프로그래밍": {
        "class",
        "dataframe",
        "dictionary",
        "function",
        "list",
        "module",
        "numpy",
        "pandas",
        "python",
        "tuple",
        "딕셔너리",
        "리스트",
        "모듈",
        "클래스",
        "파이썬",
        "함수",
    },
    "C프로그래밍": {
        "array",
        "compiler",
        "function",
        "malloc",
        "pointer",
        "printf",
        "scanf",
        "struct",
        "구조체",
        "배열",
        "포인터",
        "함수",
    },
    "객체지향프로그래밍": {
        "abstraction",
        "class",
        "encapsulation",
        "extends",
        "implements",
        "inheritance",
        "interface",
        "method",
        "object",
        "polymorphism",
        "객체",
        "객체지향",
        "다형성",
        "상속",
        "인터페이스",
        "캡슐화",
        "클래스",
    },
    "모바일프로그래밍": {
        "activity",
        "android",
        "app",
        "intent",
        "ios",
        "kotlin",
        "layout",
        "mobile",
        "swift",
        "view",
        "안드로이드",
        "액티비티",
        "앱",
        "인텐트",
        "코틀린",
    },
    "앱프로그래밍": {
        "activity",
        "android",
        "app",
        "intent",
        "ios",
        "kotlin",
        "layout",
        "mobile",
        "swift",
        "view",
        "안드로이드",
        "액티비티",
        "앱",
        "인텐트",
        "코틀린",
    },
    "인공지능": {
        "artificial intelligence",
        "classification",
        "deep learning",
        "inference",
        "machine learning",
        "model",
        "neural network",
        "training",
        "딥러닝",
        "모델",
        "분류",
        "인공지능",
        "추론",
        "학습",
    },
    "머신러닝": {
        "accuracy",
        "classifier",
        "dataset",
        "feature",
        "label",
        "loss",
        "machine learning",
        "train",
        "validation",
        "검증",
        "데이터셋",
        "분류기",
        "손실",
        "정확도",
        "특징",
    },
    "딥러닝": {
        "backpropagation",
        "cnn",
        "deep learning",
        "gradient",
        "loss",
        "neural network",
        "optimizer",
        "pytorch",
        "rnn",
        "tensorflow",
        "transformer",
        "경사",
        "딥러닝",
        "손실",
        "신경망",
        "역전파",
        "합성곱",
    },
    "컴퓨터그래픽스": {
        "fragment",
        "mesh",
        "opengl",
        "projection",
        "rendering",
        "shader",
        "texture",
        "vertex",
        "그래픽스",
        "렌더링",
        "메시",
        "셰이더",
        "정점",
        "텍스처",
        "투영",
    },
    "영상처리": {
        "convolution",
        "edge",
        "filter",
        "histogram",
        "image processing",
        "opencv",
        "pixel",
        "segmentation",
        "threshold",
        "분할",
        "영상처리",
        "임계값",
        "컨볼루션",
        "필터",
        "히스토그램",
    },
    "컴파일러": {
        "ast",
        "code generation",
        "compiler",
        "grammar",
        "lexer",
        "parser",
        "semantic",
        "syntax",
        "token",
        "구문",
        "문법",
        "어휘",
        "컴파일러",
        "토큰",
        "파서",
    },
    "정보보호": {
        "attack",
        "authentication",
        "cryptography",
        "encryption",
        "hash",
        "security",
        "signature",
        "vulnerability",
        "공격",
        "보안",
        "암호",
        "인증",
        "취약점",
        "해시",
    },
    "암호학": {
        "aes",
        "cryptography",
        "decryption",
        "encryption",
        "hash",
        "key",
        "rsa",
        "signature",
        "공개키",
        "복호화",
        "서명",
        "암호",
        "암호화",
        "키",
        "해시",
    },
    "이산수학": {
        "combinatorics",
        "discrete",
        "graph",
        "induction",
        "logic",
        "proposition",
        "recurrence",
        "relation",
        "set",
        "tree",
        "그래프",
        "귀납법",
        "논리",
        "명제",
        "순열",
        "이산수학",
        "재귀",
        "조합",
        "집합",
    },
    "오토마타": {
        "automata",
        "dfa",
        "formal language",
        "grammar",
        "nfa",
        "regular expression",
        "state",
        "transition",
        "turing",
        "문법",
        "상태",
        "오토마타",
        "전이",
        "정규표현식",
        "튜링",
    },
    "시스템프로그래밍": {
        "file descriptor",
        "gcc",
        "linux",
        "make",
        "process",
        "shell",
        "system call",
        "unix",
        "리눅스",
        "쉘",
        "시스템콜",
        "시스템프로그래밍",
        "파일디스크립터",
        "프로세스",
    },
    "임베디드시스템": {
        "actuator",
        "embedded",
        "firmware",
        "gpio",
        "i2c",
        "interrupt",
        "microcontroller",
        "sensor",
        "spi",
        "uart",
        "마이크로컨트롤러",
        "센서",
        "임베디드",
        "인터럽트",
        "펌웨어",
    },
    "마이크로프로세서": {
        "arm",
        "assembly",
        "bus",
        "instruction",
        "interrupt",
        "microprocessor",
        "register",
        "레지스터",
        "마이크로프로세서",
        "명령어",
        "버스",
        "어셈블리",
        "인터럽트",
    },
    "자료통신": {
        "bandwidth",
        "channel",
        "encoding",
        "modulation",
        "noise",
        "signal",
        "transmission",
        "대역폭",
        "변조",
        "부호화",
        "신호",
        "잡음",
        "전송",
        "채널",
    },
    "분산시스템": {
        "cluster",
        "consensus",
        "consistency",
        "distributed",
        "fault tolerance",
        "message queue",
        "replication",
        "rpc",
        "노드",
        "분산",
        "복제",
        "일관성",
        "장애허용",
        "합의",
    },
    "클라우드컴퓨팅": {
        "aws",
        "cloud",
        "container",
        "deployment",
        "docker",
        "kubernetes",
        "serverless",
        "virtualization",
        "가상화",
        "도커",
        "배포",
        "서버리스",
        "컨테이너",
        "클라우드",
        "쿠버네티스",
    },
    "데이터마이닝": {
        "association rule",
        "classification",
        "clustering",
        "data mining",
        "decision tree",
        "frequent pattern",
        "preprocessing",
        "군집",
        "데이터마이닝",
        "분류",
        "연관규칙",
        "전처리",
    },
    "빅데이터": {
        "big data",
        "dataframe",
        "etl",
        "hadoop",
        "mapreduce",
        "pipeline",
        "spark",
        "데이터프레임",
        "맵리듀스",
        "빅데이터",
        "스파크",
        "하둡",
    },
    "인간컴퓨터상호작용": {
        "affordance",
        "hci",
        "human computer interaction",
        "prototype",
        "usability",
        "user experience",
        "ux",
        "사용성",
        "상호작용",
        "인터페이스",
        "프로토타입",
    },
    "미적분": {
        "calculus",
        "derivative",
        "differentiation",
        "dx",
        "integral",
        "limit",
        "series",
        "극한",
        "급수",
        "도함수",
        "미분",
        "미적분",
        "적분",
    },
    "공업수학": {
        "differential equation",
        "fourier",
        "laplace",
        "matrix",
        "series",
        "transform",
        "vector",
        "공업수학",
        "라플라스",
        "미분방정식",
        "벡터",
        "변환",
        "푸리에",
        "행렬",
    },
    "미분방정식": {
        "boundary condition",
        "differential equation",
        "homogeneous",
        "initial value",
        "laplace",
        "ode",
        "pde",
        "경계조건",
        "라플라스",
        "미분방정식",
        "초기값",
        "해",
    },
    "수치해석": {
        "approximation",
        "error",
        "interpolation",
        "iteration",
        "newton",
        "numerical",
        "root finding",
        "근",
        "뉴턴",
        "반복법",
        "보간",
        "수치해석",
        "오차",
    },
    "통계": {
        "correlation",
        "distribution",
        "hypothesis",
        "mean",
        "regression",
        "sample",
        "standard deviation",
        "variance",
        "가설",
        "분산",
        "상관",
        "표본",
        "표준편차",
        "회귀",
    },
    "확률": {
        "bayes",
        "conditional probability",
        "distribution",
        "event",
        "expectation",
        "probability",
        "random variable",
        "기댓값",
        "분포",
        "사건",
        "조건부",
        "확률",
    },
    "경영": {
        "kpi",
        "leadership",
        "management",
        "organization",
        "strategy",
        "swot",
        "경영",
        "리더십",
        "전략",
        "조직",
    },
    "마케팅": {
        "brand",
        "campaign",
        "customer",
        "marketing",
        "positioning",
        "segmentation",
        "targeting",
        "고객",
        "마케팅",
        "브랜드",
        "세분화",
    },
    "재무관리": {
        "cash flow",
        "finance",
        "irr",
        "npv",
        "portfolio",
        "return",
        "risk",
        "현금흐름",
        "위험",
        "재무",
        "포트폴리오",
    },
    "회계": {
        "accounting",
        "asset",
        "balance sheet",
        "debit",
        "expense",
        "income statement",
        "liability",
        "revenue",
        "비용",
        "부채",
        "수익",
        "자산",
        "회계",
    },
    "재무회계": {
        "accounting",
        "asset",
        "balance sheet",
        "debit",
        "equity",
        "expense",
        "financial statement",
        "income statement",
        "liability",
        "revenue",
        "비용",
        "손익계산서",
        "자본",
        "자산",
        "재무상태표",
        "재무제표",
        "회계",
    },
    "관리회계": {
        "break even",
        "budget",
        "contribution margin",
        "cost",
        "cvp",
        "managerial accounting",
        "standard costing",
        "variance",
        "관리회계",
        "공헌이익",
        "손익분기점",
        "예산",
        "원가",
        "차이분석",
    },
    "미시경제": {
        "consumer",
        "cost",
        "demand",
        "elasticity",
        "marginal",
        "market",
        "microeconomics",
        "monopoly",
        "producer",
        "supply",
        "공급",
        "독점",
        "미시경제",
        "수요",
        "시장",
        "한계",
        "효용",
    },
    "거시경제": {
        "aggregate demand",
        "aggregate supply",
        "fiscal",
        "gdp",
        "inflation",
        "interest rate",
        "macroeconomics",
        "monetary",
        "unemployment",
        "거시경제",
        "물가",
        "실업",
        "이자율",
        "재정",
        "통화",
    },
    "생산운영관리": {
        "capacity",
        "inventory",
        "lead time",
        "operations",
        "process",
        "production",
        "quality",
        "queue",
        "scheduling",
        "공급망",
        "대기행렬",
        "생산",
        "운영",
        "재고",
        "품질",
    },
    "조직행동론": {
        "communication",
        "conflict",
        "culture",
        "leadership",
        "motivation",
        "organization",
        "performance",
        "team",
        "갈등",
        "동기부여",
        "리더십",
        "조직",
        "조직행동",
        "팀",
    },
    "물리": {
        "acceleration",
        "energy",
        "force",
        "momentum",
        "physics",
        "quantum",
        "velocity",
        "wave",
        "가속도",
        "물리",
        "에너지",
        "운동량",
        "힘",
    },
    "화학": {
        "acid",
        "atom",
        "base",
        "bond",
        "chemistry",
        "concentration",
        "molecule",
        "reaction",
        "농도",
        "분자",
        "원자",
        "화학",
    },
    "생명과학": {
        "biology",
        "cell",
        "chromosome",
        "dna",
        "enzyme",
        "gene",
        "protein",
        "rna",
        "단백질",
        "생명",
        "세포",
        "유전자",
    },
    "전자회로": {
        "capacitor",
        "circuit",
        "current",
        "diode",
        "op amp",
        "resistance",
        "signal",
        "transistor",
        "voltage",
        "신호",
        "전류",
        "전압",
        "전자회로",
        "저항",
    },
    "디지털논리": {
        "boolean",
        "decoder",
        "digital logic",
        "encoder",
        "flip flop",
        "gate",
        "karnaugh",
        "truth table",
        "논리",
        "디지털논리",
        "진리표",
        "카르노",
        "플립플롭",
    },
    "제어공학": {
        "bode",
        "control",
        "feedback",
        "laplace",
        "pid",
        "root locus",
        "stability",
        "transfer function",
        "근궤적",
        "라플라스",
        "안정도",
        "전달함수",
        "제어",
        "피드백",
    },
    "신호및시스템": {
        "convolution",
        "filter",
        "fourier",
        "frequency",
        "impulse",
        "laplace",
        "sampling",
        "signal",
        "system",
        "라플라스",
        "샘플링",
        "신호",
        "시스템",
        "임펄스",
        "주파수",
        "푸리에",
    },
}

ACADEMIC_TEXT_HINTS = {
    "algorithm",
    "architecture",
    "asset",
    "alu",
    "api",
    "atom",
    "bayes",
    "biology",
    "bond",
    "brand",
    "branch",
    "boolean",
    "cache",
    "campaign",
    "capacitor",
    "cash",
    "cell",
    "chart",
    "chapter",
    "chemistry",
    "chromosome",
    "class",
    "collision",
    "component",
    "concentration",
    "congestion",
    "control",
    "correlation",
    "cost",
    "cpu",
    "credit",
    "css",
    "customer",
    "database",
    "datapath",
    "deadlock",
    "debit",
    "decoder",
    "deep",
    "demand",
    "determinant",
    "diode",
    "distribution",
    "dna",
    "dns",
    "dom",
    "dfs",
    "dml",
    "ddl",
    "erd",
    "elasticity",
    "electric",
    "electron",
    "encoder",
    "energy",
    "enzyme",
    "equation",
    "equilibrium",
    "entity",
    "equity",
    "expectation",
    "expense",
    "execution",
    "feature",
    "finance",
    "flow",
    "force",
    "foreign",
    "frequency",
    "function",
    "gate",
    "gdp",
    "gene",
    "greedy",
    "graph",
    "hash",
    "heap",
    "html",
    "http",
    "hypothesis",
    "income",
    "inflation",
    "inference",
    "instruction",
    "interest",
    "java",
    "javascript",
    "journal",
    "kernel",
    "key",
    "label",
    "latch",
    "lecture",
    "liability",
    "logic",
    "loss",
    "linear",
    "load",
    "magnetic",
    "market",
    "marketing",
    "matrix",
    "mean",
    "memory",
    "mem",
    "model",
    "molecule",
    "momentum",
    "monopoly",
    "mutex",
    "multiplication",
    "neural",
    "network",
    "npv",
    "object",
    "organism",
    "packet",
    "paging",
    "portfolio",
    "probability",
    "process",
    "pipeline",
    "processor",
    "protein",
    "python",
    "quantum",
    "query",
    "random",
    "react",
    "regression",
    "relation",
    "register",
    "requirement",
    "resistance",
    "return",
    "revenue",
    "risk",
    "rna",
    "router",
    "routing",
    "sample",
    "scalar",
    "scheduler",
    "scrum",
    "segmentation",
    "semaphore",
    "schema",
    "signal",
    "socket",
    "software",
    "sql",
    "stack",
    "state",
    "statistics",
    "store",
    "strategy",
    "subnet",
    "supply",
    "switch",
    "table",
    "tcp",
    "testing",
    "theorem",
    "thread",
    "training",
    "transformation",
    "transistor",
    "typescript",
    "udp",
    "uml",
    "variance",
    "vector",
    "velocity",
    "voltage",
    "volume",
    "wave",
    "회계",
    "자산",
    "부채",
    "자본",
    "수익",
    "비용",
    "경제",
    "수요",
    "공급",
    "탄력성",
    "확률",
    "통계",
    "분산",
    "표준편차",
    "가설",
    "회귀",
    "상관",
    "운영체제",
    "프로세스",
    "스레드",
    "스케줄링",
    "교착",
    "페이징",
    "네트워크",
    "패킷",
    "라우팅",
    "소켓",
    "인공지능",
    "머신러닝",
    "학습",
    "분류",
    "회로",
    "전압",
    "전류",
    "저항",
    "트랜지스터",
    "물리",
    "힘",
    "에너지",
    "운동량",
    "화학",
    "분자",
    "원자",
    "반응",
    "생명",
    "세포",
    "유전자",
    "market",
    "price",
    "stock",
    "trading",
    "graph",
    "제어",
    "구조",
    "곱셈",
    "대수",
    "명령",
    "메모리",
    "벡터",
    "선형",
    "신호",
    "스칼라",
    "연산",
    "행렬",
    "자료",
    "거래",
    "시장",
    "주가",
    "주식",
    "차트",
    "챕터",
}
ACADEMIC_TEXT_HINTS.update(
    {
        "abstraction",
        "activity",
        "aes",
        "compiler",
        "constructor",
        "extends",
        "implements",
        "interface",
        "method",
        "oop",
        "구현",
        "메서드",
        "상속",
        "생성자",
        "인터페이스",
        "클래스",
    }
)


@dataclass
class VerificationResult:
    approved: bool
    status: str
    total_score: int
    reason: str
    scene_score: int
    text_score: int
    quality_score: int
    forbidden_penalty: int
    representative_frame_path: str | None


@dataclass
class FrameVerificationResult:
    frame_path: Path
    total_score: int
    scene_score: int
    text_score: int
    quality_score: int
    forbidden_penalty: int
    scene_reason: str
    text_reason: str
    classifier_reason: str


_clip_model = None
_clip_processor = None
_clip_torch = None
_clip_error = None
_ocr_reader = None
_ocr_error = None
_embedding_model = None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _short_error(error: Exception) -> str:
    message = str(error).strip()
    if len(message) > 160:
        message = f"{message[:157]}..."
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def verify_study_video(video_url: str, subject: str | None) -> VerificationResult:
    started_at = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="logy_verify_") as temp_dir:
        work_dir = Path(temp_dir)
        video_path = work_dir / "source_video"
        download_video(video_url, video_path)

        frame_paths = extract_candidate_frames(video_path, work_dir)
        if not frame_paths:
            return VerificationResult(
                approved=False,
                status="실패",
                total_score=0,
                reason="대표 프레임을 추출하지 못했습니다.",
                scene_score=0,
                text_score=0,
                quality_score=0,
                forbidden_penalty=0,
                representative_frame_path=None,
            )

        frame_result = select_best_verification_frame(frame_paths, subject)
        representative_frame = frame_result.frame_path
        quality_score = frame_result.quality_score
        scene_score = frame_result.scene_score
        forbidden_penalty = frame_result.forbidden_penalty
        scene_reason = frame_result.scene_reason
        text_score = frame_result.text_score
        text_reason = frame_result.text_reason
        classifier_reason = frame_result.classifier_reason
        total_score = frame_result.total_score
        elapsed_seconds = time.monotonic() - started_at

        needs_retake_for_timeout = elapsed_seconds >= VERIFICATION_TIMEOUT_SECONDS
        approved = total_score >= APPROVAL_THRESHOLD and not needs_retake_for_timeout
        if needs_retake_for_timeout:
            reason = "인증 처리 시간이 초과되어 재인증이 필요합니다."
        elif has_ocr_timeout(text_reason):
            reason = "OCR 처리 시간이 초과되어 재촬영이 필요합니다."
        elif total_score >= APPROVAL_THRESHOLD:
            reason = "학습 장면 맥락과 과목 관련성이 충분합니다."
        elif total_score >= RETAKE_THRESHOLD:
            reason = "학습 여부가 애매하여 재촬영이 필요합니다."
        else:
            reason = "학습 장면 또는 과목 관련성이 부족합니다."

        details = "; ".join(
            detail for detail in (scene_reason, classifier_reason, text_reason) if detail
        )
        if details:
            reason = f"{reason} ({details})"

        return VerificationResult(
            approved=approved,
            status="성공" if approved else "실패",
            total_score=total_score,
            reason=reason,
            scene_score=scene_score,
            text_score=text_score,
            quality_score=quality_score,
            forbidden_penalty=forbidden_penalty,
            representative_frame_path=save_representative_frame(representative_frame),
        )


def download_video(video_url: str, destination: Path) -> None:
    request = urllib.request.Request(
        video_url,
        headers={"User-Agent": "LogyVideoVerifier/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())


def extract_candidate_frames(video_path: Path, work_dir: Path) -> list[Path]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg가 설치되어 있지 않습니다.")

    frame_paths: list[Path] = []
    for timestamp in FRAME_TIMESTAMPS:
        output_path = work_dir / f"frame_{str(timestamp).replace('.', '_')}.jpg"
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if output_path.exists() and output_path.stat().st_size > 0:
            frame_paths.append(output_path)

    return frame_paths


def select_representative_frame(frame_paths: list[Path]) -> tuple[Path, int]:
    scored_frames = [(frame_path, score_frame_quality(frame_path)) for frame_path in frame_paths]
    scored_frames.sort(key=lambda item: item[1], reverse=True)
    return scored_frames[0]


def select_best_verification_frame(
    frame_paths: list[Path],
    subject: str | None,
) -> FrameVerificationResult:
    results: list[FrameVerificationResult] = []
    for frame_path in frame_paths:
        quality_score = score_frame_quality(frame_path)
        classifier_result = score_with_study_classifier(frame_path)
        if classifier_result.available:
            scene_score = classifier_result.scene_score
            forbidden_penalty = 0
            scene_reason = ""
            classifier_reason = classifier_result.reason
        else:
            scene_score, forbidden_penalty, scene_reason = score_scene_context(frame_path, subject)
            classifier_reason = (
                classifier_result.reason
                if classifier_result.reason != "fine_tuned_classifier=not_ready"
                else ""
            )

        extracted_text = extract_text(frame_path)
        text_score, text_reason = score_subject_similarity(subject, extracted_text)
        total_score = max(
            0,
            min(100, scene_score + text_score),
        )
        if has_strong_study_evidence(text_score):
            total_score = max(total_score, 72)

        frame_result = FrameVerificationResult(
            frame_path=frame_path,
            total_score=total_score,
            scene_score=scene_score,
            text_score=text_score,
            quality_score=quality_score,
            forbidden_penalty=forbidden_penalty,
            scene_reason=scene_reason,
            text_reason=text_reason,
            classifier_reason=classifier_reason,
        )
        if frame_result.total_score >= APPROVAL_THRESHOLD:
            return frame_result

        results.append(frame_result)

    results.sort(key=lambda result: (result.total_score, result.quality_score), reverse=True)
    return results[0]


def score_frame_quality(frame_path: Path) -> int:
    try:
        import cv2

        image = cv2.imread(str(frame_path))
        if image is None:
            return 0

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = gray.mean()
        contrast = gray.std()

        blur_component = min(1.0, blur_score / 150.0)
        brightness_component = 1.0 - min(1.0, abs(brightness - 128.0) / 128.0)
        contrast_component = min(1.0, contrast / 64.0)
        quality = (blur_component * 0.5) + (brightness_component * 0.25) + (contrast_component * 0.25)
        return round(quality * 15)
    except Exception:
        size_score = min(15, max(1, frame_path.stat().st_size // 20000))
        return int(size_score)


def score_scene_context(frame_path: Path, subject: str | None = None) -> tuple[int, int, str]:
    study_prompts = build_study_prompts(subject)
    probabilities = classify_image_with_clip(frame_path, study_prompts)
    if not probabilities:
        detail = f" ({_clip_error})" if _clip_error else ""
        return 25, 0, f"이미지 맥락 모델을 사용할 수 없어 기본 장면 점수를 적용했습니다.{detail}"

    study_score = max(probabilities)

    scene_points = round(study_score * SCENE_SCORE_MAX)
    reason = f"study={study_score:.2f}"
    return scene_points, 0, reason


def build_study_prompts(subject: str | None) -> tuple[str, ...]:
    cleaned_subject = (subject or "").strip()
    if not cleaned_subject:
        return STUDY_PROMPTS

    dynamic_prompts = (
        f"a person studying {cleaned_subject}",
        f"study notes related to {cleaned_subject}",
        f"educational material about {cleaned_subject} on a screen",
        f"a textbook, lecture slide, or notebook for {cleaned_subject}",
    )
    return STUDY_PROMPTS + dynamic_prompts


def classify_image_with_clip(frame_path: Path, prompts: tuple[str, ...]) -> list[float]:
    global _clip_error

    try:
        model, processor, torch = get_clip_components()
        from PIL import Image

        image = Image.open(frame_path).convert("RGB")
        inputs = processor(
            text=list(prompts),
            images=image,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = model(**inputs)
            logits_per_image = outputs.logits_per_image
            probabilities = logits_per_image.softmax(dim=1)[0]

        return [float(value) for value in probabilities]
    except Exception as exc:
        _clip_error = _short_error(exc)
        return []


def get_clip_components():
    global _clip_model, _clip_processor, _clip_torch

    if _clip_model is None or _clip_processor is None or _clip_torch is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        local_files_only = _env_bool("CLIP_LOCAL_FILES_ONLY", False)
        _clip_torch = torch
        _clip_model = CLIPModel.from_pretrained(
            "openai/clip-vit-base-patch32",
            local_files_only=local_files_only,
        )
        _clip_processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-base-patch32",
            local_files_only=local_files_only,
        )
        _clip_model.eval()

    return _clip_model, _clip_processor, _clip_torch


def extract_text(frame_path: Path) -> str:
    global _ocr_error

    try:
        ocr_image_path = prepare_ocr_image(frame_path)
        server_text = read_text_from_ocr_server(ocr_image_path)
        if server_text is not None:
            return server_text

        result = read_ocr_text_with_timeout(ocr_image_path, OCR_TIMEOUT_SECONDS)
        return " ".join(text for text in result if text)
    except Exception as exc:
        _ocr_error = _short_error(exc)
        return ""


def prepare_ocr_image(frame_path: Path) -> Path:
    from PIL import Image, ImageEnhance, ImageOps

    image = ImageOps.exif_transpose(Image.open(frame_path)).convert("RGB")
    width, height = image.size
    max_dimension = max(width, height)

    if max_dimension > OCR_MAX_DIMENSION:
        scale = OCR_MAX_DIMENSION / max_dimension
        resized_size = (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )
        image = image.resize(resized_size, Image.Resampling.LANCZOS)

    enhanced_image = ImageOps.autocontrast(image, cutoff=1)
    enhanced_image = ImageEnhance.Contrast(enhanced_image).enhance(1.25)
    enhanced_image = ImageEnhance.Sharpness(enhanced_image).enhance(1.35)
    ocr_path = frame_path.with_name(f"{frame_path.stem}_ocr.jpg")
    enhanced_image.save(ocr_path, format="JPEG", quality=90)
    return ocr_path


def read_ocr_text_with_timeout(ocr_image_path: Path, timeout_seconds: int) -> list[str]:
    global _ocr_error

    context_name = "fork" if hasattr(os, "fork") else "spawn"
    context = mp.get_context(context_name)
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_read_ocr_text_worker,
        args=(str(ocr_image_path), result_queue),
    )
    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(2)
        _ocr_error = f"OCRTimeout: OCR 처리 시간이 {timeout_seconds}초를 초과했습니다."
        return []

    if result_queue.empty():
        _ocr_error = "OCRWorkerError: OCR 처리 결과를 받지 못했습니다."
        return []

    status, payload = result_queue.get()
    if status == "ok":
        _ocr_error = None
        return payload

    _ocr_error = payload
    return []


def read_text_from_ocr_server(ocr_image_path: Path) -> str | None:
    global _ocr_error

    server_url = os.getenv("OCR_SERVER_URL", "").strip().rstrip("/")
    if not server_url:
        return None

    endpoint = server_url if server_url.endswith("/ocr") else f"{server_url}/ocr"
    timeout_seconds = int(os.getenv("OCR_SERVER_TIMEOUT_SECONDS", str(OCR_SERVER_TIMEOUT_SECONDS)))
    try:
        import httpx

        with ocr_image_path.open("rb") as image_file:
            response = httpx.post(
                endpoint,
                files={"file": (ocr_image_path.name, image_file, "image/jpeg")},
                timeout=timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        _ocr_error = f"OCRServerError: {_short_error(exc)}"
        return ""

    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            _ocr_error = None
            return text.strip()

        texts = payload.get("texts")
        if isinstance(texts, list):
            _ocr_error = None
            return " ".join(str(item) for item in texts if item).strip()

    _ocr_error = "OCRServerError: OCR 서버 응답 형식이 올바르지 않습니다."
    return ""


def _read_ocr_text_worker(image_path: str, result_queue) -> None:
    try:
        reader = get_ocr_reader()
        result = reader.readtext(image_path, detail=0)
        result_queue.put(("ok", [text for text in result if text]))
    except Exception as exc:
        result_queue.put(("error", _short_error(exc)))


def get_ocr_reader():
    global _ocr_reader

    if _ocr_reader is None:
        import easyocr

        _ocr_reader = easyocr.Reader(["ko", "en"], gpu=False)

    return _ocr_reader


def score_subject_similarity(subject: str | None, extracted_text: str) -> tuple[int, str]:
    cleaned_subject = (subject or "").strip()
    cleaned_text = extracted_text.strip()
    if not cleaned_subject:
        return DEFAULT_TEXT_SCORE, "과목명이 없어 과목 관련성 점수를 부여하지 않았습니다."
    if not cleaned_text:
        if _ocr_error:
            return DEFAULT_TEXT_SCORE, f"OCR 텍스트가 없어 과목 관련성 점수를 부여하지 않았습니다. ({_ocr_error})"
        return DEFAULT_TEXT_SCORE, "OCR 텍스트가 없어 과목 관련성 점수를 부여하지 않았습니다."

    expanded_subject = expand_subject(cleaned_subject)
    keyword_score, keyword_reason = score_subject_keyword_match(cleaned_subject, cleaned_text)
    similarity = calculate_text_similarity(expanded_subject, cleaned_text)
    if similarity is None:
        return keyword_fallback_score(cleaned_subject, cleaned_text)

    semantic_score = score_similarity(similarity)
    evidence_score, evidence_reason = score_academic_text_evidence(cleaned_subject, cleaned_text)
    cap = subject_text_score_cap(cleaned_subject, keyword_score)
    score = min(max(semantic_score, evidence_score, keyword_score), cap)
    reason = f"text_similarity={similarity:.2f}"
    if keyword_reason:
        reason = f"{reason}, {keyword_reason}"
    if evidence_reason:
        reason = f"{reason}, {evidence_reason}"
    if score < max(semantic_score, evidence_score, keyword_score):
        reason = f"{reason}, subject_cap={cap}"

    return score, reason


def calculate_text_similarity(subject: str, extracted_text: str) -> float | None:
    try:
        model = get_embedding_model()
        chunks = chunk_text(extracted_text)
        embeddings = model.encode([subject, *chunks], normalize_embeddings=True)
        subject_embedding = embeddings[0]
        return max(float(subject_embedding @ chunk_embedding) for chunk_embedding in embeddings[1:])
    except Exception:
        return None


def score_similarity(similarity: float) -> int:
    # Sentence-transformer 유사도는 짧은 과목명 vs 긴 OCR 텍스트에서 0.3대도 꽤 의미 있는 관련성입니다.
    calibrated = (similarity - 0.12) / 0.38
    return round(max(0.0, min(1.0, calibrated)) * TEXT_SCORE_MAX)


def get_embedding_model():
    global _embedding_model

    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL_NAME", EMBEDDING_MODEL_NAME)
        _embedding_model = SentenceTransformer(
            model_name,
            local_files_only=True,
        )

    return _embedding_model


def keyword_fallback_score(subject: str, extracted_text: str) -> tuple[int, str]:
    keyword_score, keyword_reason = score_subject_keyword_match(subject, extracted_text)
    subject_tokens = tokenize_text(expand_subject(subject))
    text_tokens = tokenize_text(extracted_text)
    evidence_score, evidence_reason = score_academic_text_evidence(subject, extracted_text)
    if not subject_tokens or not text_tokens:
        return max(keyword_score, evidence_score), "임베딩 모델을 사용할 수 없어 OCR 근거 기준으로 보정했습니다."

    overlap = len(subject_tokens & text_tokens)
    ratio = overlap / max(1, len(subject_tokens))
    score = DEFAULT_TEXT_SCORE + round(min(1.0, ratio) * 18)
    score = min(max(score, evidence_score, keyword_score), subject_text_score_cap(subject, keyword_score))
    reason = "임베딩 모델을 사용할 수 없어 키워드 겹침 기준으로 보정했습니다."
    if keyword_reason:
        reason = f"{reason}, {keyword_reason}"
    if evidence_reason:
        reason = f"{reason}, {evidence_reason}"
    return score, reason


def tokenize_text(value: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in value)
    return {token for token in normalized.split() if len(token) >= 2 and not token.isdigit()}


def expand_subject(subject: str) -> str:
    alias = SUBJECT_ALIASES.get(subject.replace(" ", ""), "") or SUBJECT_ALIASES.get(subject, "")
    if alias:
        return f"{subject} {alias}".strip()

    generic_context = (
        "lecture textbook notes workbook problem solving equation diagram concept "
        "definition theorem summary educational material study"
    )
    return f"{subject} {generic_context}".strip()


def chunk_text(value: str, chunk_size: int = 320) -> list[str]:
    words = value.split()
    if not words:
        return [value]

    chunks = []
    for index in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[index:index + chunk_size]))
    return chunks


def score_subject_keyword_match(subject: str, extracted_text: str) -> tuple[int, str]:
    normalized_subject = subject.replace(" ", "").lower()
    normalized_text = normalize_text_for_match(extracted_text)
    if normalized_subject and normalized_subject.lower() in normalized_text:
        return TEXT_SCORE_MAX, "subject_direct_match"

    core_keywords = subject_core_keywords(subject)
    if not core_keywords:
        return 0, ""

    matches = matched_keywords(core_keywords, extracted_text)
    match_count = len(matches)
    if match_count >= 3:
        return 36, f"subject_keyword_matches={match_count}"
    if match_count == 2:
        return 32, f"subject_keyword_matches={match_count}"
    if match_count == 1:
        return 24, f"subject_keyword_matches=1:{next(iter(matches))}"

    return 0, ""


def subject_core_keywords(subject: str) -> set[str]:
    compact_subject = subject.replace(" ", "")
    return (
        SUBJECT_CORE_KEYWORDS.get(compact_subject)
        or SUBJECT_CORE_KEYWORDS.get(subject)
        or set()
    )


def matched_keywords(keywords: set[str], extracted_text: str) -> set[str]:
    tokens = tokenize_text(extracted_text)
    compact_text = normalize_text_for_match(extracted_text)
    matches = set()
    for keyword in keywords:
        normalized_keyword = keyword.lower().strip()
        if not normalized_keyword:
            continue
        if " " in normalized_keyword:
            if normalized_keyword.replace(" ", "") in compact_text:
                matches.add(keyword)
            continue
        if normalized_keyword in tokens or normalized_keyword.replace(" ", "") in compact_text:
            matches.add(keyword)
    return matches


def normalize_text_for_match(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def subject_text_score_cap(subject: str, keyword_score: int) -> int:
    if not subject_core_keywords(subject):
        return TEXT_SCORE_MAX
    if keyword_score >= 36:
        return TEXT_SCORE_MAX
    if keyword_score >= 32:
        return 36
    if keyword_score >= 24:
        return 30
    return 20


def score_academic_text_evidence(subject: str, extracted_text: str) -> tuple[int, str]:
    tokens = tokenize_text(extracted_text)
    formula_score, formula_reason = score_formula_evidence(subject, extracted_text)

    hint_matches = tokens & ACADEMIC_TEXT_HINTS
    if len(hint_matches) >= 4:
        return max(18, formula_score), f"academic_text_hints={len(hint_matches)}"
    if len(hint_matches) >= 2:
        return max(12, formula_score), f"academic_text_hints={len(hint_matches)}"
    if formula_score:
        return formula_score, formula_reason
    if len(tokens) >= 20:
        return 10, "OCR 학습 텍스트량이 충분합니다."

    return 0, ""


def score_formula_evidence(subject: str, extracted_text: str) -> tuple[int, str]:
    formula_markers = sum(
        extracted_text.count(marker)
        for marker in ("=", "+", "-", "V", "v", "λ", "∫", "∑", "→", "∞", "√", "^", "≤", "≥")
    )
    compact_text = normalize_text_for_match(extracted_text)
    formula_patterns = (
        r"\bf\s*\(",
        r"\b[a-z]\s*\^\s*\d",
        r"\b[a-z]\d\b",
        r"\bdx\b",
        r"\bdy\b",
        r"\blim\b",
        r"\bsin\b",
        r"\bcos\b",
        r"\btan\b",
        r"\blog\b",
        r"\bln\b",
        r"\bdet\b",
        r"\brank\b",
        r"\bsigma\b",
        r"\btheta\b",
        r"\balpha\b",
        r"\bbeta\b",
    )
    formula_patterns_count = sum(1 for pattern in formula_patterns if re.search(pattern, extracted_text, re.IGNORECASE))
    compact_formula_markers = sum(
        marker in compact_text
        for marker in (
            "lim",
            "dx",
            "dy",
            "dydx",
            "fx",
            "gx",
            "sin",
            "cos",
            "tan",
            "log",
            "ln",
            "det",
            "rank",
            "sigma",
            "theta",
            "alpha",
            "beta",
        )
    )
    math_words = tokenize_text(extracted_text) & {
        "basis",
        "calculus",
        "derivative",
        "differential",
        "equation",
        "fourier",
        "gradient",
        "integral",
        "laplace",
        "linear",
        "matrix",
        "multiplication",
        "series",
        "scalar",
        "span",
        "vector",
        "공식",
        "극한",
        "급수",
        "곱셈",
        "도함수",
        "라플라스",
        "미분",
        "방정식",
        "벡터",
        "선형",
        "스칼라",
        "수식",
        "적분",
        "푸리에",
        "행렬",
    }
    evidence_count = formula_markers + formula_patterns_count + compact_formula_markers

    formula_cap = TEXT_SCORE_MAX if is_formula_heavy_subject(subject) else 16

    if evidence_count >= 6 or len(math_words) >= 2:
        return min(40, formula_cap), f"math_formula_evidence={evidence_count}"
    if evidence_count >= 3 or len(math_words) >= 1:
        return min(32, formula_cap), f"math_formula_evidence={evidence_count}"

    return 0, ""


def is_formula_heavy_subject(subject: str) -> bool:
    compact_subject = subject.replace(" ", "")
    return compact_subject in {
        "공업수학",
        "디지털논리",
        "물리",
        "미분방정식",
        "미적분",
        "선형대수",
        "수치해석",
        "수학",
        "신호및시스템",
        "전자회로",
        "제어공학",
        "통계",
        "확률",
    }


def has_strong_study_evidence(text_score: int) -> bool:
    return text_score >= STRONG_TEXT_SCORE


def has_ocr_timeout(text_reason: str) -> bool:
    return "OCRTimeout" in text_reason or "OCR 처리 시간이" in text_reason


def save_representative_frame(frame_path: Path) -> str:
    output_dir = Path(tempfile.gettempdir()) / "logy_ai_frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid.uuid4().hex}.jpg"
    shutil.copy2(frame_path, output_path)
    return str(output_path)
