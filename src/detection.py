# -*- coding: utf-8 -*-
"""
detection.py
============
객체 탐지 모듈입니다. 두 가지 백엔드를 지원하도록 설계했습니다.

  1) ClassicalCVDetector : 색상/형태 기반 탐지 (지금 바로 동작. 학습 불필요)
  2) YoloDetector        : ultralytics YOLO 가중치가 준비되면 이 클래스만 교체 투입
                            (인터페이스가 동일해서 pipeline.py 수정이 거의 필요없음)

왜 고전 CV를 기본으로 했는가:
  - 대회 PC에 GPU/클라우드 사용이 금지되어 있고, 실전 연습 데이터가 제한적이라
    딥러닝 모델의 신뢰도가 흔들릴 수 있음
  - 폭파구(검정 불규칙 blob), 불발탄(뚜렷한 기하학적 형태), 화재(밝은 적/주황색)는
    색상+형태만으로도 상당히 안정적으로 탐지 가능
  - "AI 예측이 실패해도 동작하는 폴백"이라는 안전장치 역할도 겸함
"""
import numpy as np
import cv2

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
import field_config as fc


# =====================================================================
# 공통 유틸: 형태 기술자(shape descriptor)
# =====================================================================
def shape_descriptors(contour):
    """윤곽선의 원형도(circularity), 종횡비(aspect ratio), 등가지름을 계산"""
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    circularity = 0.0
    if perimeter > 0:
        circularity = 4 * np.pi * area / (perimeter ** 2)  # 1.0에 가까울수록 원에 가까움

    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = max(w, h) / max(1e-6, min(w, h))
    equiv_diameter = np.sqrt(4 * area / np.pi)
    return {
        "area_px": area,
        "circularity": circularity,
        "aspect_ratio": aspect_ratio,
        "equiv_diameter_px": equiv_diameter,
        "long_axis_px": max(w, h),
        "bbox": (x, y, w, h),
    }


# =====================================================================
# 0. 공통 blob 탐지 (폭파구/불발탄 모두 어두운 물체이므로 탐지 자체는 공유)
#    -> 탐지는 한 번만 하고, 크기(mm)+형태로 '폭파구 vs 불발탄'을 사후 분류합니다.
#       (분리된 두 탐지기를 각자 돌리면 같은 물체가 양쪽에 다 걸려 이중 카운트됨)
# =====================================================================
def detect_dark_blobs(image_bgr: np.ndarray, dark_threshold=80, min_area_px=40, max_area_px=20000):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, dark_threshold, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blobs = []
    for c in contours:
        desc = shape_descriptors(c)
        if not (min_area_px < desc["area_px"] < max_area_px):
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        blobs.append({
            "center_px": (cx, cy),
            "equiv_diameter_px": desc["equiv_diameter_px"],
            "long_axis_px": desc["long_axis_px"],
            "aspect_ratio": desc["aspect_ratio"],
            "circularity": desc["circularity"],
            "contour": c,
        })
    return blobs


def mask_out_regions(image_bgr: np.ndarray, polygons: list, fill_value=255):
    """
    ArUco 마커처럼 '물체가 아닌데 어둡게 보이는' 영역을 미리 지워서(흰색 등으로 채움)
    오탐을 방지합니다. polygons: [Nx2 array, ...] 픽셀좌표 다각형 리스트 (여유있게 살짝 확대해서 사용 권장)
    """
    if not polygons:
        return image_bgr
    masked = image_bgr.copy()
    for poly in polygons:
        pts = np.array(poly, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(masked, [pts], (fill_value, fill_value, fill_value))
    return masked


def classify_blob(diameter_mm: float, long_axis_mm: float, aspect_ratio: float):
    """
    실측 mm 크기 + 종횡비를 기준으로 '폭파구' 또는 '불발탄' 중 어느 쪽에 더 가까운지,
    그리고 세부 종류(대형/중형/소형 또는 자탄/포탄/미사일)를 함께 판정합니다.

    - 폭파구는 비교적 둥글둥글하므로 등가지름(diameter_mm, 원 기준 환산값)과 비교
    - 불발탄(특히 포탄/미사일)은 길쭉하므로 장축길이(long_axis_mm)와 비교하는 것이 더 정확함
    두 치수표를 동시에 놓고 '가장 가까운 후보'를 전역적으로 찾는 방식이라
    폭파구/불발탄이 서로 중복 집계되지 않습니다.
    """
    candidates = []

    for name, dims in fc.CRATER_SIZE_TABLE_MM.items():
        ref_diameter = (dims["w"] + dims["h"]) / 2.0
        ref_aspect = max(dims["w"], dims["h"]) / min(dims["w"], dims["h"])
        diam_diff = abs(diameter_mm - ref_diameter) / ref_diameter
        ar_diff = abs(aspect_ratio - ref_aspect) / ref_aspect
        score = diam_diff * 0.7 + ar_diff * 0.3   # 폭파구는 크기가 더 결정적
        candidates.append(("crater", name, score))

    for name, dims in fc.UXO_SIZE_TABLE_MM.items():
        ref_length = max(dims["w"], dims["d"])
        ref_aspect = dims["d"] / dims["w"]
        len_diff = abs(long_axis_mm - ref_length) / ref_length
        ar_diff = abs(aspect_ratio - ref_aspect) / max(ref_aspect, 0.01)
        score = len_diff * 0.4 + ar_diff * 0.6   # 불발탄은 형태(길쭉함)가 더 결정적
        candidates.append(("uxo", name, score))

    candidates.sort(key=lambda x: x[2])
    category, subtype, score = candidates[0]
    confidence = max(0.3, round(1.0 - min(score, 0.7), 2))
    return category, subtype, confidence


# =====================================================================
# 1. 폭파구 탐지 (검정 불규칙 blob)
# =====================================================================
class CraterDetector:
    def __init__(self, dark_threshold=60, min_area_px=80):
        self.dark_threshold = dark_threshold
        self.min_area_px = min_area_px

    def detect(self, image_bgr: np.ndarray):
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        # 어두운 영역(검정 폭파구 모형) 이진화
        _, binary = cv2.threshold(gray, self.dark_threshold, 255, cv2.THRESH_BINARY_INV)
        # 노이즈 제거 + 구멍 메우기
        kernel = np.ones((5, 5), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for c in contours:
            desc = shape_descriptors(c)
            if desc["area_px"] < self.min_area_px:
                continue
            # 폭파구는 불규칙하지만 대체로 둥글둥글함(원형도 0.3~0.9 범위로 완화된 필터)
            if desc["circularity"] < 0.15:
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            detections.append({
                "center_px": (cx, cy),
                "equiv_diameter_px": desc["equiv_diameter_px"],
                "contour": c,
            })
        return detections

    @staticmethod
    def classify_size(diameter_mm: float) -> str:
        """실측 치수표와 대조해서 대형/중형/소형 판정 (최근접 매칭)"""
        best_class, best_diff = None, float("inf")
        for cls_name, dims in fc.CRATER_SIZE_TABLE_MM.items():
            ref_diameter = (dims["w"] + dims["h"]) / 2.0
            diff = abs(diameter_mm - ref_diameter)
            if diff < best_diff:
                best_diff = diff
                best_class = cls_name
        return best_class


# =====================================================================
# 2. 불발탄 탐지 (형태 기반: 자탄=원형, 포탄=중간 종횡비, 미사일=매우 길쭉)
# =====================================================================
class UXODetector:
    def __init__(self, dark_threshold=90, min_area_px=30, max_area_px=6000):
        self.dark_threshold = dark_threshold
        self.min_area_px = min_area_px
        self.max_area_px = max_area_px

    def detect(self, image_bgr: np.ndarray):
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, self.dark_threshold, 255, cv2.THRESH_BINARY_INV)
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for c in contours:
            desc = shape_descriptors(c)
            if not (self.min_area_px < desc["area_px"] < self.max_area_px):
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            uxo_type, confidence = self._classify_by_shape(desc)
            detections.append({
                "center_px": (cx, cy),
                "equiv_diameter_px": desc["equiv_diameter_px"],
                "aspect_ratio": desc["aspect_ratio"],
                "type": uxo_type,
                "confidence": confidence,
                "contour": c,
            })
        return detections

    @staticmethod
    def _classify_by_shape(desc):
        """
        형태 기술자(원형도/종횡비)로 1차 분류.
        - 자탄: 거의 정원형 (aspect_ratio ~ 1.0, circularity 높음)
        - 포탄: 중간 종횡비 (원통형, 세워서 촬영 시 원형/누워서 촬영 시 타원)
        - 미사일: 매우 길쭉함 (aspect_ratio 큼)
        치수표(fc.UXO_SIZE_TABLE_MM)의 세로/가로 비율과 대조해 신뢰도를 계산합니다.
        """
        ar = desc["aspect_ratio"]
        ref_ratios = {
            name: dims["d"] / dims["w"] for name, dims in fc.UXO_SIZE_TABLE_MM.items()
        }
        # ref_ratios 예: 자탄 ~0.73, 포탄 ~2.11, 미사일 ~2.3
        best_type, best_diff = None, float("inf")
        for name, ratio in ref_ratios.items():
            diff = abs(ar - ratio)
            if diff < best_diff:
                best_diff = diff
                best_type = name
        confidence = max(0.3, 1.0 - min(best_diff / 3.0, 0.7))  # 0.3~1.0 사이로 클램프
        return best_type, round(confidence, 2)


# =====================================================================
# 3. 시설물 상태 분류 (정상/파손/화재) - 색상 기반 + 시계열 깜빡임 검사
# =====================================================================
class FacilityStatusClassifier:
    def __init__(self):
        pass

    def classify_single_frame(self, roi_bgr: np.ndarray):
        """
        roi_bgr: 이미 잘라낸(crop된) 시설물 영역 이미지.
        프레임마다 호모그래피가 다를 수 있으므로, ROI 자르기는 pipeline 쪽에서
        프레임별로 수행하고 이 함수에는 잘라진 결과만 넘깁니다.
        화재(밝은 적/주황), 파손(불규칙 어두운 패치 비율), 정상 중 하나를 1차 판정.
        """
        roi = roi_bgr
        if roi.size == 0:
            return "미확인", 0.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # 화재색 범위 (빨강~주황, 높은 채도/명도)
        fire_mask1 = cv2.inRange(hsv, (0, 120, 150), (15, 255, 255))
        fire_mask2 = cv2.inRange(hsv, (160, 120, 150), (179, 255, 255))
        fire_ratio = (cv2.countNonZero(fire_mask1) + cv2.countNonZero(fire_mask2)) / max(1, roi.shape[0] * roi.shape[1])

        if fire_ratio > 0.03:
            return "화재", round(min(1.0, fire_ratio * 10), 2)

        # 파손 추정: 어두운 불규칙 영역 비율(그림자/균열/붕괴 등으로 어두워짐)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        dark_ratio = np.mean(gray < 60)
        if dark_ratio > 0.35:
            return "파손", round(min(1.0, dark_ratio), 2)

        return "정상", round(1.0 - dark_ratio, 2)

    def classify_with_temporal_check(self, rois_bgr: list):
        """
        여러 프레임에 걸쳐 '화재 깜빡임'을 확인하여 오탐(빨간 벽돌 등)을 걸러냄.
        rois_bgr: 프레임별로 각각 잘라낸(이미 crop된) 같은 시설물의 ROI 이미지 리스트
        """
        results = [self.classify_single_frame(r) for r in rois_bgr]
        labels = [r[0] for r in results]
        confidences = [r[1] for r in results]

        if labels.count("화재") == 0:
            # 화재가 아니면 다수결로 결정
            from collections import Counter
            most_common = Counter(labels).most_common(1)[0][0]
            avg_conf = float(np.mean(confidences))
            return most_common, round(avg_conf, 2)

        # 화재로 판정된 프레임 비율이 충분히 높고, 밝기 변화(깜빡임)가 감지되면 화재 확정
        fire_ratio_frames = labels.count("화재") / len(labels)
        brightness_series = [np.mean(r) for r in rois_bgr]
        flicker = float(np.std(brightness_series))

        if fire_ratio_frames > 0.3 and flicker > 1.0:
            return "화재", round(float(np.mean(confidences)), 2)
        else:
            # 화재로 보였지만 깜빡임이 없다면 정지된 붉은 물체(오탐 가능성) -> 파손/정상 재판정
            non_fire_labels = [l for l in labels if l != "화재"]
            if non_fire_labels:
                from collections import Counter
                return Counter(non_fire_labels).most_common(1)[0][0], 0.5
            return "파손", 0.4


# =====================================================================
# 4. (확장용) YOLO 백엔드 스텁 - 학습된 가중치가 생기면 이 클래스를 완성해서 교체
# =====================================================================
class YoloDetectorStub:
    """
    ultralytics YOLO가 설치되고 학습된 .pt 파일이 준비되면 아래처럼 구현합니다.
    인터페이스(detect 메서드가 center_px, type, confidence를 반환)를 동일하게 맞추면
    pipeline.py 수정 없이 백엔드만 교체할 수 있습니다.

        from ultralytics import YOLO
        class YoloDetector:
            def __init__(self, weights_path):
                self.model = YOLO(weights_path)
            def detect(self, image_bgr):
                results = self.model.predict(image_bgr, verbose=False)[0]
                out = []
                for box in results.boxes:
                    cx, cy = box.xywh[0][:2].tolist()
                    out.append({"center_px": (cx, cy),
                                "type": self.model.names[int(box.cls)],
                                "confidence": float(box.conf)})
                return out

    SAHI(타일 분할 추론)를 적용하려면 예측 전 이미지를 겹치는 타일로 나누고,
    각 타일 결과를 전역 좌표로 오프셋한 뒤 병합하면 됩니다.
    """
    pass
