# -*- coding: utf-8 -*-
"""
field_config.py
================
경기장의 모든 '고정된 사실'을 모아둔 파일입니다.
슬라이드에서 미리 공개된 정보(치수표, 구간 레이아웃, 축척)를 그대로 코드로 옮겼습니다.
대회 규정상 ArUco 마커와 경기장 레이아웃은 테스트 경기장 포함 사전 공개되므로,
이 파일의 좌표값은 실제 테스트 경기장에서 다시 측정해 업데이트해야 합니다.
"""

# ---------------------------------------------------------
# 1. 경기장 전체 규격
# ---------------------------------------------------------
FIELD_WIDTH_CM = 500       # 가로 (실제 경기장 모형 크기)
FIELD_HEIGHT_CM = 400      # 세로
SCALE_RATIO = 600          # 1 : 600 축척
# 모형 1cm = 실제 600cm = 실제 6m
REAL_METERS_PER_MODEL_CM = SCALE_RATIO / 100.0  # = 6.0 m/cm


# ---------------------------------------------------------
# 2. ArUco 마커 설정 (경기장 4개 모서리 기준점)
# ---------------------------------------------------------
# 실전에서는 테스트 경기장에서 각 마커의 실제 위치를 재측정해서 갱신하세요.
ARUCO_DICT_NAME = "DICT_4X4_50"

# 마커 ID -> 경기장 기준 좌표(cm). 이미지 6번에서 모서리에 X 표시가 있던 지점.
ARUCO_MARKER_WORLD_POSITIONS = {
    0: (0.0, 0.0),                          # 좌상단
    1: (FIELD_WIDTH_CM, 0.0),               # 우상단
    2: (FIELD_WIDTH_CM, FIELD_HEIGHT_CM),   # 우하단
    3: (0.0, FIELD_HEIGHT_CM),              # 좌하단
}


# ---------------------------------------------------------
# 3. 구역/구간 레이아웃 (이미지 18 기준)
#    좌표계: 원점(0,0)은 좌상단, x는 오른쪽, y는 아래쪽 (cm 단위, 모형 기준)
# ---------------------------------------------------------
def _row(y0, y1, names, widths, x0=0.0):
    """가로로 나열된 구간들의 (x_min,y_min,x_max,y_max) 딕셔너리를 생성하는 헬퍼"""
    segs = {}
    x = x0
    for name, w in zip(names, widths):
        segs[name] = {"x_min": x, "y_min": y0, "x_max": x + w, "y_max": y1}
        x += w
    return segs


SEGMENTS = {}

# 상단 시설물 구역 (FA-01, FA-02, FA-03) : y 0~80
SEGMENTS.update(_row(
    0, 80,
    ["FA-01", "FA-02", "FA-03"],
    [160, 180, 160],
))

# 유도로 A구역 (TW-A1~TW-A5) : y 80~160
SEGMENTS.update(_row(
    80, 160,
    ["TW-A1", "TW-A2", "TW-A3", "TW-A4", "TW-A5"],
    [100, 100, 100, 100, 100],
))

# 활주로 구역 (RW-01~RW-10) : y 160~240
SEGMENTS.update(_row(
    160, 240,
    [f"RW-{i:02d}" for i in range(1, 11)],
    [50] * 10,
))

# 유도로 B구역 (TW-B1~TW-B5) : y 240~320
SEGMENTS.update(_row(
    240, 320,
    ["TW-B1", "TW-B2", "TW-B3", "TW-B4", "TW-B5"],
    [100, 100, 100, 100, 100],
))

# 하단 시설물 구역 (FA-04, FA-05, FA-06) : y 320~400
SEGMENTS.update(_row(
    320, 400,
    ["FA-04", "FA-05", "FA-06"],
    [160, 180, 160],
))

# 활주로 구간 순서 (가용길이 산출용, 왼쪽->오른쪽)
RUNWAY_SEGMENT_ORDER = [f"RW-{i:02d}" for i in range(1, 11)]
TAXIWAY_A_ORDER = ["TW-A1", "TW-A2", "TW-A3", "TW-A4", "TW-A5"]
TAXIWAY_B_ORDER = ["TW-B1", "TW-B2", "TW-B3", "TW-B4", "TW-B5"]
FACILITY_SLOTS = ["FA-01", "FA-02", "FA-03", "FA-04", "FA-05", "FA-06"]

# 예시 검증: RW-01 실제 길이 = 50cm(모형) * 6.0(m/cm) = 300m -> 슬라이드 예시와 일치
_RW01_REAL_LEN = (SEGMENTS["RW-01"]["x_max"] - SEGMENTS["RW-01"]["x_min"]) * REAL_METERS_PER_MODEL_CM
assert abs(_RW01_REAL_LEN - 300.0) < 1e-6, "RW-01 실제 길이가 300m가 되어야 합니다(슬라이드 예시 기준)"


# ---------------------------------------------------------
# 4. 시설물 종류 (6종) - FA 슬롯과의 매핑
#    * 실제 배치 순서는 테스트 경기장에서 확인 후 아래 매핑을 갱신하세요.
# ---------------------------------------------------------
FACILITY_TYPE_BY_SLOT = {
    "FA-01": "관제탑",
    "FA-02": "관제레이더",
    "FA-03": "격납고",
    "FA-04": "일반건물1",
    "FA-05": "일반건물2",
    "FA-06": "무기고",
}
FACILITY_STATUS_OPTIONS = ["정상", "파손", "화재", "미확인"]


# ---------------------------------------------------------
# 5. 폭파구 실측 치수표 (단위: mm, 이미지 16 기준)
#    (가로, 세로, 높이/깊이)
# ---------------------------------------------------------
CRATER_SIZE_TABLE_MM = {
    "대형": {"w": 179.0, "h": 200.0, "d": 30.0},
    "중형": {"w": 159.0, "h": 150.0, "d": 23.0},
    "소형": {"w": 102.5, "h": 99.0, "d": 16.0},
}

# ---------------------------------------------------------
# 6. 불발탄 실측 치수표 (단위: mm, 이미지 8 기준)
# ---------------------------------------------------------
UXO_SIZE_TABLE_MM = {
    "자탄": {"w": 28.0, "h": 28.0, "d": 20.5},   # 집속탄 내부 자탄, 구형에 가까움
    "포탄": {"w": 44.0, "h": 44.0, "d": 93.0},   # 원통형
    "미사일": {"w": 50.0, "h": 50.0, "d": 115.0},  # 가장 길쭉함
}

# ---------------------------------------------------------
# 7. 미션 코드 (mission_code)  -  실전 시작 전 갱신 필요
# ---------------------------------------------------------
MISSION_CODE = "LKUSDC8O"  # 예시. 실제 대회에서 팀별로 부여된 코드로 교체

# ---------------------------------------------------------
# 8. 임무 제한시간
# ---------------------------------------------------------
MISSION_TIME_LIMIT_SEC = 180

# ---------------------------------------------------------
# 9. 탐지 백엔드 설정 (고전 CV <-> YOLO 전환)
# ---------------------------------------------------------
# 대회 현장에서 테스트 기간 중 촬영한 이미지로 YOLO 학습이 끝나면
# 아래 두 값만 "yolo"로 바꾸면 src/pipeline.py 수정 없이 백엔드가 전환됩니다.
# (src/detection.py의 build_object_detector()/build_facility_classifier() 참고)
DETECTOR_BACKEND = "classical"   # "classical" | "yolo" - 폭파구/불발탄 통합 탐지
FACILITY_BACKEND = "classical"   # "classical" | "yolo" - 시설물 상태(정상/파손/화재) 분류

# --- 폭파구/불발탄 YOLO 모델 설정 ---
YOLO_OBJECT_WEIGHTS = "models/object_detector.pt"
YOLO_OBJECT_CONF_THRESHOLD = 0.4
# 학습 클래스 idx -> (category, subtype). data.yaml의 names 순서와 반드시 일치시킬 것.
YOLO_OBJECT_CLASS_MAP = {
    0: ("crater", "대형"),
    1: ("crater", "중형"),
    2: ("crater", "소형"),
    3: ("uxo", "미사일"),
    4: ("uxo", "포탄"),
    5: ("uxo", "자탄"),
}

# --- 시설물 상태 YOLO 모델 설정 ---
YOLO_FACILITY_WEIGHTS = "models/facility_classifier.pt"
YOLO_FACILITY_CONF_THRESHOLD = 0.4
# 학습 클래스 idx -> 상태 라벨. data.yaml/분류 폴더 순서와 반드시 일치시킬 것.
YOLO_FACILITY_CLASS_MAP = {
    0: "정상",
    1: "파손",
    2: "화재",
}

# ---------------------------------------------------------
# 10. 고전 CV 알고리즘 하이퍼파라미터
#     실제 드론 촬영본으로 재조정할 값들을 전부 이 섹션에 모아둠
# ---------------------------------------------------------
# -- 어두운 blob(폭파구/불발탄 후보) 탐지 (detection.detect_dark_blobs) --
BLOB_DARK_THRESHOLD = 80   # 이 값보다 어두운 픽셀만 물체 후보로 봄 (0~255, 낮을수록 더 어두운 것만 탐지)
BLOB_MIN_AREA_PX = 40      # 이보다 작은 컨투어는 노이즈로 무시
BLOB_MAX_AREA_PX = 20000   # 이보다 큰 컨투어는 그림자 등으로 보고 무시

# -- 폭파구/불발탄 분류 점수 가중치 (detection.classify_blob) --
CRATER_SCORE_WEIGHTS = {"diameter": 0.7, "aspect_ratio": 0.3}  # 폭파구는 크기가 더 결정적
UXO_SCORE_WEIGHTS = {"length": 0.4, "aspect_ratio": 0.6}       # 불발탄은 길쭉한 형태가 더 결정적
CLASSIFY_CONFIDENCE_FLOOR = 0.3   # 분류 신뢰도 최저값
CLASSIFY_SCORE_CAP = 0.7          # 신뢰도 = 1 - min(점수, 이 값)

# -- 시설물 상태(정상/파손/화재) 판정 (detection.ClassicalFacilityClassifier) --
FACILITY_FIRE_HSV_RANGES = [                # 화재색(빨강~주황) HSV 범위, (하한, 상한) 쌍의 리스트
    ((0, 120, 150), (15, 255, 255)),
    ((160, 120, 150), (179, 255, 255)),
]
FACILITY_FIRE_RATIO_THRESHOLD = 0.03        # 화재로 1차 판정하는 최소 화재색 픽셀 비율
FACILITY_FIRE_CONFIDENCE_SCALE = 10.0       # fire_ratio -> confidence 환산 배율
FACILITY_DAMAGE_GRAY_THRESHOLD = 60         # 이보다 어두운 픽셀을 '파손 후보'로 셈 (그레이스케일 0~255)
FACILITY_DAMAGE_DARK_RATIO_THRESHOLD = 0.35 # 파손으로 판정하는 최소 어두운 픽셀 비율
FACILITY_FIRE_FRAME_RATIO_THRESHOLD = 0.3   # 여러 프레임 중 화재로 확정하는 최소 프레임 비율
FACILITY_FIRE_FLICKER_THRESHOLD = 1.0       # 화재 확정에 필요한 프레임 간 밝기 표준편차(깜빡임)
FACILITY_FALLBACK_NONFIRE_CONFIDENCE = 0.5  # 화재로 보였으나 깜빡임 없어 non-화재로 재판정할 때 신뢰도
FACILITY_FALLBACK_DAMAGE_CONFIDENCE = 0.4   # 위 재판정에서 non-화재 라벨조차 없을 때의 기본 신뢰도

# -- 지오레퍼런스드 중복 제거 거리 임계값 (geo_dedup.dedup_by_world_distance, 단위: cm) --
CRATER_DEDUP_DISTANCE_CM = 5.0
UXO_DEDUP_DISTANCE_CM = 3.0

# -- ArUco 캘리브레이션 (calibration.FieldCalibrator) --
ARUCO_MIN_MARKERS = 4                  # 호모그래피 계산에 필요한 최소 마커 개수
ARUCO_SUBPIX_WINDOW = (5, 5)           # cornerSubPix 탐색 윈도우 크기
ARUCO_SUBPIX_CRITERIA_MAX_ITER = 30    # cornerSubPix 반복 종료 조건 (최대 반복 횟수)
ARUCO_SUBPIX_CRITERIA_EPS = 0.001      # cornerSubPix 반복 종료 조건 (오차 임계값)

# -- 마커 마스킹 (pipeline.MissionPipeline) --
MARKER_MASK_EXPAND_RATIO = 1.15  # 마커 영역 마스킹 시 여유 확장 비율 (경계까지 확실히 제거)
MARKER_MASK_FILL_VALUE = 255     # 마스킹 채움 색상 (흰색)

# -- 로컬 LLM 설정 (report_generator.py) --
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b"          # 대회 PC 사양에 맞춰 사전에 벤치마크 후 결정
OLLAMA_REQUEST_TIMEOUT_SEC = 8       # 임무 시간이 촉박하므로 타임아웃을 짧게 설정
OLLAMA_TEMPERATURE = 0.2             # 보고서이므로 창의성보다 일관성 우선

# ---------------------------------------------------------
# 11. 파일 경로 (원하는 위치로 자유롭게 변경 가능, CLI 인자로도 override 가능)
# ---------------------------------------------------------
TEST_IMAGE_DIR = "test_images"  # --synthetic 실행 시 합성 테스트/학습용 이미지가 저장되는 폴더
OUTPUT_DIR = "output"           # 8개 결과 JSON이 저장되는 폴더
