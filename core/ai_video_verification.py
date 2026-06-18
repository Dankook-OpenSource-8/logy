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


FRAME_TIMESTAMPS = (2.0,)
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
CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"

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
    "자료구조": "data structure abstract data type adt array list stack queue fifo lifo enqueue dequeue front rear empty size stl vector hash bucket collision graph tree heap dfs bfs connected component",
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
    "전기회로": "electric circuit circuit analysis voltage current resistance capacitance inductance impedance kirchhoff node mesh power",
    "회로이론": "circuit theory circuit analysis voltage current resistance capacitance inductance impedance kirchhoff node mesh phasor",
    "전자기학": "electromagnetics electric field magnetic field maxwell equation gauss law ampere faraday wave potential flux",
    "통신공학": "communication engineering modulation demodulation signal noise channel bandwidth coding antenna transmission receiver",
    "반도체공학": "semiconductor diode transistor mosfet pn junction carrier bandgap doping wafer fabrication cmos device",
    "기계공학": "mechanical engineering force stress strain motion energy machine design mechanics thermodynamics fluid material",
    "열역학": "thermodynamics heat work energy entropy enthalpy temperature pressure cycle ideal gas rankine carnot",
    "유체역학": "fluid mechanics flow pressure viscosity reynolds bernoulli navier stokes boundary layer turbulence",
    "재료역학": "mechanics of materials stress strain beam torsion bending shear moment deflection elasticity",
    "동역학": "dynamics motion force acceleration velocity momentum vibration rigid body newton equation",
    "정역학": "statics force moment equilibrium truss friction centroid free body diagram reaction",
    "재료공학": "materials science crystal structure phase diagram alloy polymer ceramic metal composite microstructure heat treatment",
    "화공양론": "chemical process principles stoichiometry mass balance energy balance mole fraction reaction conversion yield",
    "유기화학": "organic chemistry hydrocarbon alkane alkene aromatic alcohol aldehyde ketone carboxylic acid reaction mechanism",
    "분석화학": "analytical chemistry titration chromatography spectroscopy calibration concentration acid base redox equilibrium",
    "건축학": "architecture building design space plan structure material site section elevation floor plan model",
    "건축구조": "building structure load beam column slab foundation steel concrete seismic design moment shear",
    "토목공학": "civil engineering structure soil concrete bridge road survey hydrology transportation foundation construction",
    "환경공학": "environmental engineering water treatment wastewater air pollution waste management pollutant ecology sustainability",
    "산업공학": "industrial engineering optimization operations research production scheduling quality ergonomics simulation logistics supply chain",
    "품질경영": "quality management six sigma control chart process capability defect sampling iso improvement",
    "인간공학": "ergonomics human factors usability posture workload interface anthropometry safety workplace design",
    "해부학": "anatomy bone muscle nerve organ tissue skeleton artery vein body structure physiology",
    "생리학": "physiology homeostasis cell membrane nervous endocrine cardiovascular respiratory renal metabolism hormone",
    "병리학": "pathology disease inflammation necrosis tumor diagnosis infection immune tissue lesion etiology",
    "약리학": "pharmacology drug receptor dose response pharmacokinetics pharmacodynamics adverse effect metabolism therapy",
    "미생물학": "microbiology bacteria virus fungus culture infection immunity antibiotic pathogen gram staining",
    "간호학": "nursing patient care assessment diagnosis intervention vital signs safety infection medication communication",
    "기본간호학": "fundamentals of nursing patient care vital signs hygiene infection control medication assessment safety",
    "성인간호학": "adult nursing cardiovascular respiratory digestive endocrine neurological patient assessment intervention care",
    "공중보건": "public health epidemiology prevention health promotion disease surveillance population sanitation policy",
    "심리학": "psychology cognition behavior emotion learning memory perception personality development experiment therapy",
    "상담심리": "counseling psychology therapy client interview assessment empathy cognitive behavioral intervention case",
    "교육학": "education curriculum instruction assessment pedagogy learning classroom teacher student development",
    "교육심리": "educational psychology learning motivation cognition development assessment instruction behavior classroom",
    "사회학": "sociology society culture group institution class inequality norm socialization research",
    "사회복지": "social welfare case management policy community service client assessment intervention support",
    "행정학": "public administration policy bureaucracy organization governance budget regulation public service decision",
    "정치학": "political science state government democracy election party ideology power institution policy",
    "법학": "law legal contract tort constitution criminal civil procedure rights obligation case statute",
    "헌법": "constitutional law rights freedom separation of powers judicial review government state constitution",
    "민법": "civil law contract property tort obligation ownership damages family inheritance",
    "형법": "criminal law crime punishment intent negligence liability offense defense sentencing",
    "영어": "english reading grammar vocabulary listening speaking writing comprehension paragraph sentence translation",
    "영문법": "english grammar tense clause phrase subject verb object passive relative pronoun sentence",
    "영어회화": "english conversation speaking listening dialogue expression pronunciation fluency question answer",
    "일본어": "japanese hiragana katakana kanji grammar vocabulary reading listening conversation translation",
    "중국어": "chinese pinyin hanzi grammar vocabulary reading listening conversation tone translation",
    "한국사": "korean history dynasty joseon goryeo silla independence movement colonial period constitution culture",
    "세계사": "world history civilization empire revolution war nationalism imperialism modern history culture",
    "철학": "philosophy ethics metaphysics epistemology logic argument existence knowledge value philosopher",
    "논리학": "logic proposition predicate inference proof validity truth table argument deduction induction",
    "글쓰기": "writing composition essay paragraph thesis argument outline revision citation expression",
    "디자인": "design concept layout color typography composition prototype user research visual communication",
    "시각디자인": "visual design typography layout color branding poster grid composition illustration identity",
    "UX디자인": "ux design user experience usability user research persona journey wireframe prototype interaction",
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
        "adt",
        "array",
        "bfs",
        "dfs",
        "dequeue",
        "empty",
        "enqueue",
        "fifo",
        "front",
        "graph",
        "hash",
        "heap",
        "lifo",
        "queue",
        "rear",
        "size",
        "stack",
        "stl",
        "tree",
        "vector",
        "그래프",
        "덱",
        "리스트",
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

SUBJECT_ALIASES.update(
    {
        "컴퓨터공학": "computer science programming algorithm data structure database operating system network software engineering artificial intelligence",
        "정보통신": "information communication network signal data communication wireless modulation protocol antenna transmission",
        "전기전자공학": "electrical electronic engineering circuit electromagnetics semiconductor signal control communication microprocessor",
        "기초전자공학": "basic electronics circuit diode transistor voltage current resistance capacitor amplifier semiconductor",
        "데이터사이언스": "data science statistics machine learning dataframe visualization regression classification clustering preprocessing model",
        "경영정보시스템": "management information system mis database erp crm decision support business process information technology",
        "회계원리": "accounting principle asset liability equity revenue expense debit credit journal ledger financial statement",
        "재무제표분석": "financial statement analysis balance sheet income statement cash flow ratio profitability liquidity leverage",
        "기업재무": "corporate finance capital structure dividend valuation cash flow cost of capital investment decision",
        "투자론": "investment portfolio stock bond risk return capm beta diversification valuation market",
        "세법": "tax law income tax corporate tax value added tax deduction taxable income return",
        "원가회계": "cost accounting cost allocation overhead variance standard costing activity based costing budget",
        "무역학": "international trade export import tariff exchange rate incoterms customs payment logistics contract",
        "국제무역": "international trade export import tariff exchange rate incoterms customs payment logistics contract",
        "전자상거래": "e commerce online platform payment shopping mall digital marketing logistics customer data",
        "창업론": "entrepreneurship startup business model lean startup market validation venture investment pitch",
        "물류관리": "logistics inventory transportation warehouse distribution supply chain lead time routing",
        "공급사슬관리": "supply chain management procurement logistics inventory demand forecasting distribution supplier bullwhip",
        "인적자원관리": "human resource management recruitment selection training performance appraisal compensation labor",
        "노사관계론": "industrial relations labor union collective bargaining wage employment dispute labor law",
        "국제경영": "international business globalization trade exchange rate multinational strategy foreign market",
        "조직이론": "organization theory structure culture environment bureaucracy contingency decision power",
        "광고홍보": "advertising public relations campaign media brand message audience promotion communication",
        "소비자행동": "consumer behavior decision making attitude perception motivation purchase satisfaction loyalty",
        "서비스마케팅": "service marketing customer satisfaction service quality servqual relationship marketing experience",
        "시장조사론": "marketing research survey sampling questionnaire data analysis consumer insight hypothesis",
        "비즈니스분석": "business analytics data analysis dashboard kpi regression forecasting decision model visualization",
        "인지심리": "cognitive psychology memory attention perception language problem solving reasoning information processing",
        "발달심리": "developmental psychology child adolescence attachment cognition social development piaget erikson",
        "임상심리": "clinical psychology assessment diagnosis therapy disorder depression anxiety counseling case",
        "청소년상담": "youth counseling adolescent client crisis career family school violence intervention case",
        "가족상담": "family counseling family therapy system communication conflict relationship genogram intervention",
        "상담이론": "counseling theory psychoanalysis cognitive behavioral therapy humanistic client counselor intervention",
        "범죄학": "criminology crime deviance victim policing punishment correction prevention justice",
        "지식재산": "intellectual property ip patent trademark copyright design right licensing license assignment sale transfer royalty infringement technology commercialization",
        "지식재산권": "intellectual property ip patent trademark copyright design right licensing license assignment sale transfer royalty infringement technology commercialization",
        "지적재산권": "intellectual property ip patent trademark copyright design right licensing license assignment sale transfer royalty infringement technology commercialization",
        "상법": "commercial law company negotiable instrument insurance commerce merchant transaction corporation shareholder",
        "회사법": "corporate law corporation shareholder director board stock capital merger governance",
        "노동법": "labor law employment wage working hour dismissal union collective bargaining worker",
        "국제거래법": "international transaction law trade contract cisg arbitration jurisdiction governing law payment",
        "형사소송법": "criminal procedure investigation prosecution arrest warrant evidence trial defendant due process",
        "행정법": "administrative law agency disposition appeal regulation public authority litigation",
        "국제법": "international law treaty state sovereignty jurisdiction human rights un convention",
        "교육과정": "curriculum education objective content instruction assessment lesson design learning outcome",
        "교수학습": "teaching learning instruction pedagogy classroom strategy assessment feedback lesson",
        "교육행정": "educational administration school organization leadership policy budget teacher principal management",
        "특수교육": "special education disability inclusion individualized education plan iep intervention support assessment",
        "유아교육": "early childhood education child development play curriculum observation kindergarten interaction",
        "평생교육": "lifelong education adult learning program planning community learning participation evaluation",
        "교육평가": "educational assessment evaluation reliability validity item analysis test score rubric",
        "교육학개론": "introduction to education pedagogy curriculum instruction assessment classroom teacher student learning development",
        "교육철학": "philosophy of education educational thought idealism pragmatism humanism purpose value school",
        "교육사회학": "sociology of education school inequality culture socialization class curriculum hidden curriculum",
        "교육공학": "educational technology instructional design media e learning learning management system lms",
        "미술치료": "art therapy counseling client emotion expression drawing painting assessment intervention psychology",
        "놀이치료": "play therapy child counseling play assessment intervention emotion behavior relationship",
        "음악치료": "music therapy rhythm song intervention emotion communication client assessment counseling",
        "심리학개론": "introduction to psychology cognition behavior emotion learning memory personality development experiment",
        "사회학개론": "introduction to sociology society culture institution group inequality socialization research",
        "행정학개론": "introduction to public administration policy bureaucracy organization governance budget public service",
        "법학개론": "introduction to law constitution civil criminal contract rights procedure case statute",
        "경제학개론": "introduction to economics demand supply market price elasticity gdp inflation unemployment",
        "경영학개론": "introduction to management organization strategy marketing finance accounting operation leadership",
        "회계학개론": "introduction to accounting asset liability equity revenue expense debit credit financial statement",
        "무역학개론": "introduction to international trade export import tariff exchange rate customs logistics",
        "미디어학개론": "introduction to media communication journalism broadcasting content platform audience message",
        "언론학개론": "introduction to journalism media news reporting audience agenda framing communication",
        "철학개론": "introduction to philosophy ethics metaphysics epistemology logic knowledge existence value",
        "문학개론": "literature poetry novel drama narrative theme character criticism genre",
        "예술학개론": "art studies aesthetics art history visual culture style work artist criticism",
        "디자인학개론": "introduction to design concept layout color typography composition user research visual communication",
        "언어학": "linguistics phonetics phonology morphology syntax semantics pragmatics language grammar",
        "국어국문학": "korean literature language grammar poetry novel criticism classical literature linguistics",
        "문헌정보학": "library information science catalog metadata classification database retrieval archive bibliography",
        "미디어커뮤니케이션": "media communication journalism broadcasting content audience platform public opinion message",
        "신문방송학": "journalism broadcasting news media audience agenda framing reporting communication",
        "영상제작": "video production camera lighting editing storyboard shot sequence audio",
        "영화이론": "film theory montage mise en scene narrative genre cinematography editing",
        "기초디자인": "basic design dot line plane color shape composition contrast balance typography",
        "패션디자인": "fashion design textile pattern silhouette garment color fabric collection",
        "색채학": "color theory hue saturation brightness contrast harmony color wheel perception",
        "사진학": "photography exposure aperture shutter iso composition lens lighting",
        "음악이론": "music theory scale chord harmony rhythm melody key interval notation",
        "미술사": "art history renaissance baroque impressionism modern art artist style",
        "간호관리학": "nursing management leadership staffing delegation quality patient safety organization communication",
        "모성간호학": "maternal nursing pregnancy labor delivery postpartum fetus newborn reproductive health",
        "아동간호학": "pediatric nursing child growth development vaccination family fever respiratory care",
        "정신간호학": "psychiatric nursing mental health depression anxiety schizophrenia therapeutic communication crisis",
        "지역사회간호학": "community health nursing public health epidemiology family community prevention health promotion",
        "응급간호학": "emergency nursing triage cpr shock trauma airway resuscitation emergency patient",
        "간호연구": "nursing research evidence based practice hypothesis sample statistics questionnaire validity",
        "보건통계": "health statistics epidemiology prevalence incidence odds ratio relative risk confidence interval",
        "역학": "epidemiology prevalence incidence cohort case control odds ratio relative risk outbreak",
        "보건교육": "health education health promotion behavior change program planning community prevention",
        "의학용어": "medical terminology anatomy prefix suffix diagnosis symptom disease treatment",
        "면역학": "immunology antigen antibody immune response t cell b cell cytokine vaccine",
        "영양학": "nutrition carbohydrate protein fat vitamin mineral metabolism calorie diet digestion",
        "운동생리학": "exercise physiology muscle oxygen heart rate metabolism energy aerobic anaerobic training",
        "스포츠과학": "sports science biomechanics exercise physiology training performance injury motor learning",
        "식품공학": "food engineering processing preservation fermentation sterilization packaging quality safety",
        "식품영양학": "food nutrition carbohydrate protein fat vitamin mineral metabolism diet calorie health",
        "분자생물학": "molecular biology dna rna replication transcription translation protein gene expression",
        "유전학": "genetics gene chromosome inheritance allele mutation genotype phenotype mendel",
        "생화학": "biochemistry enzyme protein carbohydrate lipid metabolism glycolysis krebs atp",
        "세포생물학": "cell biology membrane organelle nucleus mitochondria cell cycle cytoskeleton signaling",
        "동물생리학": "animal physiology nervous endocrine circulation respiration digestion excretion homeostasis",
        "식물생리학": "plant physiology photosynthesis transpiration hormone xylem phloem stomata growth",
        "생명과학개론": "introduction to life science biology cell dna gene protein evolution ecology organism metabolism",
        "생명학개론": "introduction to life science biology cell dna gene protein evolution ecology organism metabolism",
        "일반생물학": "general biology cell dna gene protein enzyme metabolism evolution ecology organism",
        "일반화학": "general chemistry atom molecule reaction bond acid base equilibrium concentration mole",
        "일반물리학": "general physics force motion energy momentum wave electricity magnetism equation",
        "대학수학": "college mathematics calculus function limit derivative integral matrix vector probability",
        "기초수학": "basic mathematics function equation limit derivative integral matrix vector probability",
        "공학수학": "engineering mathematics differential equation laplace fourier matrix vector series transform",
        "기초통계학": "basic statistics mean variance distribution sample hypothesis regression correlation",
        "통계학개론": "introduction to statistics mean variance distribution sample hypothesis regression correlation",
        "컴퓨터공학개론": "introduction to computer science programming algorithm data structure database network operating system",
        "프로그래밍기초": "programming basics code variable function loop array condition class python java c",
        "파이썬기초": "python basics variable function list dictionary loop class module input output",
        "컴퓨터활용": "computer literacy spreadsheet word processor presentation internet file data software",
        "정보사회와컴퓨터": "information society computer internet data software digital technology security ai",
        "로봇공학": "robotics kinematics dynamics actuator sensor control path planning manipulator",
        "메카트로닉스": "mechatronics sensor actuator controller motor embedded system robotics control",
        "자동차공학": "automotive engineering engine transmission suspension brake vehicle dynamics powertrain",
        "CAD": "cad computer aided design drawing modeling dimension assembly solidworks autocad",
        "캡스톤디자인": "capstone design project prototype requirement design implementation testing presentation",
        "공학설계": "engineering design problem definition concept design prototype testing evaluation requirement",
        "실험통계": "experimental statistics design of experiment anova regression hypothesis sample variance",
        "논문작성": "research writing thesis abstract introduction method result discussion citation reference",
        "관광학개론": "introduction to tourism tourism industry destination traveler hospitality service attraction itinerary",
        "관광경영": "tourism management destination marketing travel agency hospitality service tourist behavior",
        "호텔경영": "hotel management hospitality front office housekeeping reservation revenue service guest",
        "외식경영": "food service management restaurant menu service kitchen cost hygiene customer",
        "조리원리": "culinary principle cooking heat ingredient recipe food safety sauce baking",
        "식품위생학": "food hygiene food safety microorganism contamination sanitation haccp sterilization",
        "항공서비스": "airline service cabin crew passenger safety hospitality airport reservation",
        "항공운항": "aviation flight navigation aircraft weather air traffic control safety",
        "항공정비": "aircraft maintenance engine airframe avionics inspection repair safety",
        "부동산학개론": "real estate property appraisal investment land housing lease mortgage market",
        "도시계획": "urban planning land use transportation zoning housing infrastructure development",
        "조경학": "landscape architecture planting site design park ecology landscape planning",
        "실내건축": "interior architecture space design furniture lighting material floor plan",
        "주거학": "housing residential environment household family space dwelling interior",
        "경찰학개론": "police science policing crime investigation patrol public safety law enforcement",
        "소방학개론": "fire science fire prevention combustion disaster rescue emergency safety",
        "재난관리": "disaster management risk prevention response recovery emergency safety crisis",
        "군사학": "military science strategy tactics security defense leadership operation",
        "국가안보론": "national security defense strategy alliance threat intelligence policy",
        "국제관계": "international relations diplomacy security state power alliance conflict",
        "국제정치": "international politics diplomacy state sovereignty alliance security war",
        "지역학": "area studies region culture politics economy society language history",
        "중국학": "china studies chinese politics economy culture history society language",
        "일본학": "japan studies japanese politics economy culture history society language",
        "영미문화": "english american culture literature history society language communication",
        "통번역": "translation interpretation source text target language equivalence terminology",
        "한국어교육": "korean language education grammar vocabulary speaking writing learner instruction",
        "윤리학": "ethics moral philosophy virtue duty utilitarianism justice value",
        "생명윤리": "bioethics medical ethics autonomy consent dignity life research ethics",
        "종교학": "religious studies religion ritual belief scripture theology culture",
        "신학": "theology bible doctrine church faith christian ethics scripture",
        "기독교개론": "introduction to christianity bible church faith jesus theology ethics",
        "수의학": "veterinary medicine animal disease anatomy physiology diagnosis treatment",
        "동물자원학": "animal science livestock breeding nutrition reproduction management",
        "축산학": "animal husbandry livestock feed breeding reproduction dairy meat",
        "농학": "agriculture crop soil plant cultivation fertilizer pest farm",
        "원예학": "horticulture plant flower fruit vegetable greenhouse cultivation",
        "작물학": "crop science rice wheat seed cultivation yield soil fertilizer",
        "산림학": "forestry forest tree ecology silviculture timber conservation",
        "해양학": "oceanography ocean current wave marine ecosystem salinity tide",
        "수산학": "fisheries aquaculture fish marine resource breeding water quality",
        "지질학": "geology rock mineral earth crust plate tectonics sediment fossil",
        "천문학": "astronomy star planet galaxy universe telescope orbit cosmology",
        "대기과학": "atmospheric science weather climate pressure humidity wind precipitation",
        "기상학": "meteorology weather climate pressure humidity wind cloud precipitation",
        "치위생학": "dental hygiene oral health plaque periodontal scaling caries prevention",
        "물리치료학": "physical therapy rehabilitation exercise joint muscle gait pain treatment",
        "작업치료학": "occupational therapy rehabilitation daily living activity cognition function",
        "방사선학": "radiology x ray ct mri radiation imaging dose safety",
        "임상병리학": "clinical pathology laboratory blood urine specimen diagnosis test",
        "의공학": "biomedical engineering medical device biosignal imaging biomaterial sensor",
        "보건행정": "health administration hospital management insurance policy medical record",
        "미용학": "cosmetology skin hair makeup beauty care treatment hygiene",
        "피부미용": "skin care esthetics cosmetic facial treatment hair removal hygiene",
        "게임기획": "game design mechanic level balance narrative player experience",
        "게임프로그래밍": "game programming engine unity unreal csharp physics rendering input",
        "애니메이션": "animation character storyboard keyframe motion timing rendering",
        "만화콘텐츠": "comics content story character panel narrative illustration",
        "문화콘텐츠": "cultural content storytelling media platform character ip planning",
        "빅데이터분석": "big data analytics hadoop spark dataframe visualization model clustering",
        "데이터베이스설계": "database design erd normalization entity relationship schema sql transaction",
        "정보검색": "information retrieval search index ranking query tf idf document",
        "자연어처리": "natural language processing token embedding transformer syntax semantics corpus",
        "컴퓨터비전": "computer vision image detection segmentation feature cnn recognition",
        "강화학습": "reinforcement learning agent environment reward policy value q learning",
        "블록체인": "blockchain hash block transaction consensus smart contract cryptocurrency",
        "핀테크": "fintech payment banking blockchain risk finance platform regulation",
        "보험학": "insurance risk premium policy claim underwriting life nonlife",
        "금융기관론": "financial institution bank securities insurance interest rate risk regulation",
        "화폐금융론": "money banking monetary policy interest rate inflation central bank",
        "계량경제학": "econometrics regression time series panel data hypothesis estimator",
    }
)

SUBJECT_CORE_KEYWORDS.update(
    {
        "전기회로": {"circuit", "kirchhoff", "node", "mesh", "impedance", "phasor", "voltage", "current", "전압", "전류", "임피던스", "키르히호프"},
        "회로이론": {"circuit", "kirchhoff", "node", "mesh", "impedance", "phasor", "voltage", "current", "전압", "전류", "회로", "키르히호프"},
        "전자기학": {"electric field", "magnetic field", "maxwell", "gauss", "faraday", "flux", "전기장", "자기장", "맥스웰", "가우스", "자속"},
        "통신공학": {"modulation", "demodulation", "channel", "bandwidth", "antenna", "receiver", "변조", "복조", "채널", "대역폭", "안테나"},
        "반도체공학": {"semiconductor", "mosfet", "diode", "transistor", "pn junction", "carrier", "doping", "반도체", "다이오드", "트랜지스터", "도핑"},
        "열역학": {"entropy", "enthalpy", "temperature", "pressure", "cycle", "ideal gas", "heat", "work", "엔트로피", "엔탈피", "열", "일", "사이클"},
        "유체역학": {"flow", "pressure", "viscosity", "reynolds", "bernoulli", "navier", "turbulence", "유동", "압력", "점성", "레이놀즈", "베르누이"},
        "재료역학": {"stress", "strain", "beam", "torsion", "bending", "shear", "moment", "deflection", "응력", "변형률", "보", "전단", "모멘트"},
        "정역학": {"equilibrium", "force", "moment", "truss", "friction", "centroid", "free body", "평형", "힘", "모멘트", "트러스", "마찰"},
        "화공양론": {"stoichiometry", "mass balance", "energy balance", "mole", "conversion", "yield", "물질수지", "에너지수지", "몰", "전환율", "수율"},
        "유기화학": {"alkane", "alkene", "aromatic", "alcohol", "aldehyde", "ketone", "reaction mechanism", "유기", "알코올", "케톤", "반응메커니즘"},
        "건축구조": {"load", "beam", "column", "slab", "foundation", "concrete", "seismic", "하중", "보", "기둥", "슬래브", "기초", "콘크리트"},
        "토목공학": {"structure", "soil", "concrete", "bridge", "road", "survey", "hydrology", "구조", "토질", "교량", "도로", "측량", "수문"},
        "산업공학": {"optimization", "operations research", "scheduling", "quality", "simulation", "logistics", "최적화", "스케줄링", "품질", "시뮬레이션", "물류"},
        "해부학": {"anatomy", "bone", "muscle", "nerve", "organ", "tissue", "skeleton", "artery", "뼈", "근육", "신경", "장기", "조직"},
        "생리학": {"physiology", "homeostasis", "membrane", "nervous", "endocrine", "cardiovascular", "renal", "항상성", "막", "신경", "내분비", "심혈관"},
        "병리학": {"pathology", "disease", "inflammation", "necrosis", "tumor", "infection", "lesion", "질병", "염증", "괴사", "종양", "감염"},
        "약리학": {"pharmacology", "drug", "receptor", "dose", "pharmacokinetics", "adverse effect", "약물", "수용체", "용량", "약동학", "부작용"},
        "간호학": {"nursing", "patient", "assessment", "intervention", "vital signs", "infection", "medication", "간호", "환자", "사정", "중재", "활력징후"},
        "심리학": {"psychology", "cognition", "behavior", "emotion", "learning", "memory", "personality", "심리", "인지", "행동", "정서", "기억"},
        "교육학": {"education", "curriculum", "instruction", "assessment", "pedagogy", "classroom", "교육", "교육과정", "교수", "평가", "수업"},
        "사회학": {"sociology", "society", "culture", "institution", "class", "inequality", "socialization", "사회", "문화", "계급", "불평등"},
        "행정학": {"public administration", "policy", "bureaucracy", "governance", "budget", "regulation", "행정", "정책", "관료제", "예산", "규제"},
        "법학": {"law", "contract", "tort", "constitution", "criminal", "civil", "procedure", "rights", "법", "계약", "불법행위", "헌법", "형법", "민법"},
        "지식재산": {"intellectual property", "ip", "patent", "trademark", "copyright", "licensing", "license", "assignment", "royalty", "infringement", "지식재산", "지식재산권", "특허", "상표", "저작권", "디자인권", "라이선싱", "라이선스", "권리", "매각", "양도", "로열티", "침해"},
        "지식재산권": {"intellectual property", "ip", "patent", "trademark", "copyright", "licensing", "license", "assignment", "royalty", "infringement", "지식재산", "지식재산권", "특허", "상표", "저작권", "디자인권", "라이선싱", "라이선스", "권리", "매각", "양도", "로열티", "침해"},
        "지적재산권": {"intellectual property", "ip", "patent", "trademark", "copyright", "licensing", "license", "assignment", "royalty", "infringement", "지적재산권", "지식재산", "특허", "상표", "저작권", "디자인권", "라이선싱", "라이선스", "권리", "매각", "양도", "로열티", "침해"},
        "상법": {"commercial law", "company", "merchant", "corporation", "shareholder", "insurance", "상법", "회사", "상인", "주주", "어음", "보험"},
        "회사법": {"corporate law", "corporation", "shareholder", "director", "board", "stock", "merger", "회사", "주주", "이사", "주식", "합병"},
        "노동법": {"labor law", "employment", "wage", "dismissal", "union", "collective bargaining", "노동", "근로", "임금", "해고", "노조"},
        "청소년상담": {"youth", "adolescent", "counseling", "client", "crisis", "career", "청소년", "상담", "내담자", "위기", "진로"},
        "가족상담": {"family counseling", "family therapy", "system", "communication", "conflict", "genogram", "가족", "상담", "치료", "갈등", "의사소통"},
        "특수교육": {"special education", "disability", "inclusion", "iep", "intervention", "support", "특수교육", "장애", "통합교육", "개별화", "중재"},
        "교육행정": {"educational administration", "school", "leadership", "policy", "budget", "principal", "교육행정", "학교", "리더십", "정책", "예산"},
        "교육학개론": {"education", "pedagogy", "curriculum", "instruction", "assessment", "classroom", "teacher", "student", "learning", "교육", "교육학", "교육과정", "교수", "평가", "수업", "교사", "학생", "학습"},
        "미술치료": {"art therapy", "therapy", "client", "emotion", "expression", "drawing", "painting", "assessment", "intervention", "counseling", "미술치료", "치료", "내담자", "정서", "표현", "그림", "상담", "중재"},
        "생명과학개론": {"biology", "life science", "cell", "dna", "gene", "protein", "evolution", "ecology", "organism", "metabolism", "생명", "생명과학", "세포", "유전자", "단백질", "진화", "생태", "대사"},
        "생명학개론": {"biology", "life science", "cell", "dna", "gene", "protein", "evolution", "ecology", "organism", "metabolism", "생명", "생명과학", "세포", "유전자", "단백질", "진화", "생태", "대사"},
        "무역학": {"international trade", "export", "import", "tariff", "incoterms", "customs", "무역", "수출", "수입", "관세", "통관"},
        "전자상거래": {"e commerce", "platform", "payment", "online", "customer", "digital marketing", "전자상거래", "플랫폼", "결제", "온라인"},
        "창업론": {"entrepreneurship", "startup", "business model", "lean startup", "venture", "pitch", "창업", "스타트업", "비즈니스모델", "벤처"},
        "색채학": {"color", "hue", "saturation", "brightness", "contrast", "harmony", "색채", "색상", "채도", "명도", "대비"},
        "사진학": {"photography", "exposure", "aperture", "shutter", "iso", "lens", "사진", "노출", "조리개", "셔터", "렌즈"},
        "음악이론": {"music", "scale", "chord", "harmony", "rhythm", "melody", "음악", "음계", "화음", "리듬", "선율"},
        "로봇공학": {"robotics", "kinematics", "actuator", "sensor", "control", "manipulator", "로봇", "센서", "액추에이터", "제어"},
        "메카트로닉스": {"mechatronics", "sensor", "actuator", "controller", "motor", "embedded", "메카트로닉스", "센서", "모터", "제어기"},
        "캡스톤디자인": {"capstone", "project", "prototype", "requirement", "implementation", "testing", "캡스톤", "프로젝트", "프로토타입", "요구사항"},
        "공학설계": {"engineering design", "concept", "prototype", "testing", "evaluation", "requirement", "공학설계", "개념설계", "프로토타입", "평가"},
        "간호연구": {"nursing research", "evidence", "hypothesis", "sample", "statistics", "validity", "간호연구", "근거", "가설", "표본", "타당도"},
        "역학": {"epidemiology", "prevalence", "incidence", "cohort", "odds ratio", "relative risk", "역학", "유병률", "발생률", "코호트"},
        "면역학": {"immunology", "antigen", "antibody", "immune", "t cell", "b cell", "면역", "항원", "항체", "백신"},
        "영어": {"english", "grammar", "vocabulary", "reading", "listening", "speaking", "writing", "영어", "문법", "어휘", "독해", "작문"},
        "한국사": {"joseon", "goryeo", "silla", "independence movement", "colonial", "dynasty", "조선", "고려", "신라", "독립운동", "일제"},
        "세계사": {"civilization", "empire", "revolution", "war", "nationalism", "imperialism", "문명", "제국", "혁명", "전쟁", "제국주의"},
        "디자인": {"design", "layout", "color", "typography", "composition", "prototype", "디자인", "레이아웃", "색채", "타이포그래피", "구성"},
        "데이터사이언스": {"data science", "dataframe", "visualization", "regression", "classification", "clustering", "preprocessing", "데이터", "시각화", "회귀", "분류", "군집"},
        "관광경영": {"tourism", "destination", "hospitality", "service", "travel", "관광", "여행", "목적지", "서비스"},
        "호텔경영": {"hotel", "hospitality", "reservation", "front office", "housekeeping", "guest", "호텔", "객실", "예약", "고객"},
        "조리원리": {"culinary", "cooking", "ingredient", "recipe", "food safety", "조리", "식재료", "레시피", "위생"},
        "항공서비스": {"airline", "cabin crew", "passenger", "safety", "airport", "항공", "승객", "객실", "안전"},
        "부동산학개론": {"real estate", "property", "appraisal", "land", "lease", "mortgage", "부동산", "토지", "임대차", "감정평가"},
        "도시계획": {"urban planning", "land use", "zoning", "transportation", "housing", "도시", "토지이용", "교통", "주거"},
        "경찰학개론": {"police", "crime", "investigation", "patrol", "law enforcement", "경찰", "범죄", "수사", "순찰"},
        "소방학개론": {"fire", "combustion", "disaster", "rescue", "emergency", "소방", "화재", "연소", "구조", "재난"},
        "군사학": {"military", "strategy", "tactics", "defense", "operation", "군사", "전략", "전술", "국방", "작전"},
        "국제관계": {"international relations", "diplomacy", "security", "state", "alliance", "국제관계", "외교", "안보", "동맹"},
        "윤리학": {"ethics", "moral", "virtue", "duty", "justice", "윤리", "도덕", "정의", "가치"},
        "생명윤리": {"bioethics", "medical ethics", "autonomy", "consent", "dignity", "생명윤리", "동의", "자율성", "존엄"},
        "수의학": {"veterinary", "animal", "disease", "diagnosis", "treatment", "수의", "동물", "질병", "진단"},
        "농학": {"agriculture", "crop", "soil", "cultivation", "fertilizer", "농업", "작물", "토양", "재배"},
        "지질학": {"geology", "rock", "mineral", "plate", "fossil", "지질", "암석", "광물", "화석"},
        "천문학": {"astronomy", "star", "planet", "galaxy", "universe", "천문", "별", "행성", "은하"},
        "치위생학": {"dental hygiene", "oral", "plaque", "periodontal", "scaling", "치위생", "구강", "치석", "스케일링"},
        "물리치료학": {"physical therapy", "rehabilitation", "exercise", "joint", "muscle", "물리치료", "재활", "운동", "관절", "근육"},
        "작업치료학": {"occupational therapy", "rehabilitation", "daily living", "activity", "cognition", "작업치료", "재활", "일상생활", "인지"},
        "방사선학": {"radiology", "x ray", "ct", "mri", "radiation", "방사선", "영상", "촬영", "선량"},
        "게임기획": {"game design", "mechanic", "level", "balance", "player", "게임", "기획", "레벨", "밸런스"},
        "자연어처리": {"natural language processing", "token", "embedding", "transformer", "corpus", "자연어", "토큰", "임베딩", "말뭉치"},
        "컴퓨터비전": {"computer vision", "image", "detection", "segmentation", "cnn", "비전", "영상", "검출", "분할"},
        "블록체인": {"blockchain", "hash", "transaction", "consensus", "smart contract", "블록체인", "해시", "트랜잭션", "합의"},
        "계량경제학": {"econometrics", "regression", "time series", "panel data", "estimator", "계량경제", "회귀", "시계열", "패널"},
    }
)

ACADEMIC_TEXT_HINTS.update(
    {
        keyword
        for keywords in SUBJECT_CORE_KEYWORDS.values()
        for keyword in keywords
        if " " not in keyword
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


def _perf_log(stage: str, started_at: float, **fields) -> None:
    if not _env_bool("VERIFY_PERF_LOGS", True):
        return
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    suffix = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    print(f"[video-verify] {stage} elapsed_ms={elapsed_ms}" + (f" {suffix}" if suffix else ""))


def verify_study_video(video_url: str, subject: str | None) -> VerificationResult:
    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="logy_verify_") as temp_dir:
        work_dir = Path(temp_dir)
        video_path = work_dir / "source_video"
        download_video(video_url, video_path)

        frame_paths = extract_candidate_frames(video_path, work_dir)
        _perf_log("frames_ready", started_at, frame_count=len(frame_paths))
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
        _perf_log("frame_scored", started_at, total_score=frame_result.total_score)
        representative_frame = frame_result.frame_path
        quality_score = frame_result.quality_score
        scene_score = frame_result.scene_score
        forbidden_penalty = frame_result.forbidden_penalty
        scene_reason = frame_result.scene_reason
        text_score = frame_result.text_score
        text_reason = frame_result.text_reason
        classifier_reason = frame_result.classifier_reason
        total_score = frame_result.total_score
        approved = total_score >= APPROVAL_THRESHOLD
        if total_score < RETAKE_THRESHOLD:
            reason = "학습 장면 또는 과목 관련성이 부족합니다."
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

        result = VerificationResult(
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
        _perf_log("verify_done", started_at, status=result.status, total_score=result.total_score)
        return result


def download_video(video_url: str, destination: Path) -> None:
    started_at = time.perf_counter()
    request = urllib.request.Request(
        video_url,
        headers={"User-Agent": "LogyVideoVerifier/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())
    _perf_log("download_video", started_at, bytes=destination.stat().st_size)


def extract_candidate_frames(video_path: Path, work_dir: Path) -> list[Path]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg가 설치되어 있지 않습니다.")

    started_at = time.perf_counter()
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

    _perf_log("extract_frames", started_at, frame_count=len(frame_paths))
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
        extracted_text = extract_text(frame_path)
        classifier_started_at = time.perf_counter()
        classifier_result = score_with_study_classifier(frame_path)
        _perf_log(
            "study_classifier",
            classifier_started_at,
            available=classifier_result.available,
        )
        if classifier_result.available:
            scene_score = classifier_result.scene_score
            forbidden_penalty = 0
            scene_reason = ""
            classifier_reason = classifier_result.reason
        else:
            scene_started_at = time.perf_counter()
            scene_score, forbidden_penalty, scene_reason = score_scene_context(frame_path, subject)
            _perf_log("scene_context", scene_started_at)
            classifier_reason = (
                classifier_result.reason
                if classifier_result.reason != "fine_tuned_classifier=not_ready"
                else ""
            )

        text_started_at = time.perf_counter()
        text_score, text_reason = score_subject_similarity(subject, extracted_text)
        if has_strong_study_evidence(text_score):
            text_score = TEXT_SCORE_MAX
            text_reason = f"{text_reason}, strong_text_evidence_boost={TEXT_SCORE_MAX}"
        _perf_log("subject_similarity", text_started_at, text_score=text_score)
        total_score = max(
            0,
            min(100, scene_score + text_score),
        )

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
        model_name = os.getenv("CLIP_MODEL_NAME", CLIP_MODEL_NAME)
        _clip_model = CLIPModel.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        _clip_processor = CLIPProcessor.from_pretrained(
            model_name,
            local_files_only=local_files_only,
        )
        _clip_model.eval()

    return _clip_model, _clip_processor, _clip_torch


def extract_text(frame_path: Path) -> str:
    global _ocr_error

    try:
        started_at = time.perf_counter()
        ocr_image_path = prepare_ocr_image(frame_path)
        _perf_log("prepare_ocr_image", started_at, bytes=ocr_image_path.stat().st_size)
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
        try:
            result = read_ocr_text_variants(str(ocr_image_path))
            if result:
                _ocr_error = None
                return result
        except Exception as exc:
            _ocr_error = f"OCRWorkerError: {_short_error(exc)}"
            return []

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
    started_at = time.perf_counter()
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
        _perf_log("ocr_server", started_at, status="error")
        _ocr_error = f"OCRServerError: {_short_error(exc)}"
        return None

    _perf_log("ocr_server", started_at, status="ok")
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            _ocr_error = None
            cleaned_text = text.strip()
            return cleaned_text if cleaned_text else None

        texts = payload.get("texts")
        if isinstance(texts, list):
            _ocr_error = None
            cleaned_text = " ".join(str(item) for item in texts if item).strip()
            return cleaned_text if cleaned_text else None

    _ocr_error = "OCRServerError: OCR 서버 응답 형식이 올바르지 않습니다."
    return None


def _read_ocr_text_worker(image_path: str, result_queue) -> None:
    try:
        result_queue.put(("ok", read_ocr_text_variants(image_path)))
    except Exception as exc:
        result_queue.put(("error", _short_error(exc)))


def read_ocr_text_variants(image_path: str) -> list[str]:
    reader = get_ocr_reader()
    attempts = (
        {"detail": 0},
        {
            "detail": 0,
            "canvas_size": 1280,
            "min_size": 20,
            "bbox_min_size": 8,
            "text_threshold": 0.4,
            "low_text": 0.2,
        },
        {
            "detail": 0,
            "canvas_size": 1920,
            "min_size": 10,
            "bbox_min_size": 5,
            "text_threshold": 0.3,
            "low_text": 0.1,
        },
    )
    best_result: list[str] = []
    for options in attempts:
        result = [text for text in reader.readtext(image_path, **options) if text]
        if len(" ".join(result)) > len(" ".join(best_result)):
            best_result = result
        if len(best_result) >= 8 or len(" ".join(best_result)) >= 120:
            break
    return best_result


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
    score = max(semantic_score, evidence_score, keyword_score)
    reason = f"text_similarity={similarity:.2f}"
    if keyword_reason:
        reason = f"{reason}, {keyword_reason}"
    if evidence_reason:
        reason = f"{reason}, {evidence_reason}"

    return score, reason


def calculate_text_similarity(subject: str, extracted_text: str) -> float | None:
    try:
        started_at = time.perf_counter()
        model = get_embedding_model()
        chunks = chunk_text(extracted_text)
        embeddings = model.encode([subject, *chunks], normalize_embeddings=True)
        subject_embedding = embeddings[0]
        similarity = max(float(subject_embedding @ chunk_embedding) for chunk_embedding in embeddings[1:])
        _perf_log("embedding_similarity", started_at, chunk_count=len(chunks))
        return similarity
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
    started_at = time.perf_counter()
    output_dir = Path(tempfile.gettempdir()) / "logy_ai_frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid.uuid4().hex}.jpg"
    shutil.copy2(frame_path, output_path)
    _perf_log("save_representative_frame", started_at)
    return str(output_path)
