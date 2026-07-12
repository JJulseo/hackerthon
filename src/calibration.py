# -*- coding: utf-8 -*-
"""
calibration.py
==============
ArUco 마커로 카메라 픽셀 좌표 <-> 경기장 실좌표(cm)를 변환하는 호모그래피를 계산합니다.

핵심 아이디어:
  - 대회 규정상 ArUco 마커는 테스트 경기장 포함 '사전 공개'됨
  - 따라서 호모그래피 행렬은 대회 당일 실시간으로 계산하지 않고,
    사전 연습 기간에 미리 계산해서 캐시(저장)해두는 것이 이상적.
  - 이 모듈은 두 가지 모드를 지원:
      1) calibrate_from_image(): 이미지에서 마커를 검출해 H 행렬을 계산
      2) load_cached_homography() / save_cached_homography(): 사전 계산값 재사용
"""
import json
import numpy as np
import cv2

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
import field_config as fc


def _get_aruco_dictionary():
    dict_id = getattr(cv2.aruco, fc.ARUCO_DICT_NAME)
    return cv2.aruco.getPredefinedDictionary(dict_id)


class FieldCalibrator:
    def __init__(self):
        self.aruco_dict = _get_aruco_dictionary()
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        self.homography = None  # 3x3, pixel(x,y,1) -> world_cm(x,y,1)
        self.last_marker_corners = []  # 최근 검출된 마커들의 픽셀 코너 (마스킹용)

    # -----------------------------------------------------------------
    def detect_markers(self, image_bgr: np.ndarray):
        """이미지에서 ArUco 마커를 검출. corners, ids 반환."""
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _rejected = self.detector.detectMarkers(gray)
        return corners, ids

    # -----------------------------------------------------------------
    def calibrate_from_image(self, image_bgr: np.ndarray, refine_subpixel: bool = True):
        """
        이미지 속 마커 중심좌표(픽셀) <-> 알려진 실좌표(cm)로 호모그래피를 계산.
        최소 4개 마커(경기장 모서리)가 필요.
        """
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids = self.detect_markers(image_bgr)

        if ids is None or len(ids) < 4:
            raise RuntimeError(
                f"ArUco 마커가 4개 미만 검출됨(검출:{0 if ids is None else len(ids)}). "
                "드론 고도/각도를 조정하거나 조명을 확인하세요."
            )

        # 서브픽셀 코너 정밀화 (호모그래피 오차를 줄이는 핵심 포인트)
        if refine_subpixel:
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            for c in corners:
                cv2.cornerSubPix(gray, c, (5, 5), (-1, -1), criteria)

        pixel_pts = []
        world_pts = []
        marker_corner_list = []
        for marker_corners, marker_id in zip(corners, ids.flatten()):
            marker_id = int(marker_id)
            marker_corner_list.append(marker_corners[0])  # 4x2 픽셀 코너 (마스킹용, 필드 밖 마커 포함)
            if marker_id not in fc.ARUCO_MARKER_WORLD_POSITIONS:
                continue  # 필드 밖/미사용 마커는 무시
            center_px = marker_corners[0].mean(axis=0)  # (x,y) 픽셀 중심
            pixel_pts.append(center_px)
            world_pts.append(fc.ARUCO_MARKER_WORLD_POSITIONS[marker_id])
        self.last_marker_corners = marker_corner_list

        if len(pixel_pts) < 4:
            raise RuntimeError("설정된 마커 ID와 일치하는 마커가 4개 미만입니다.")

        pixel_pts = np.array(pixel_pts, dtype=np.float32)
        world_pts = np.array(world_pts, dtype=np.float32)

        H, mask = cv2.findHomography(pixel_pts, world_pts, method=cv2.RANSAC)
        if H is None:
            raise RuntimeError("호모그래피 계산 실패 (마커 배치를 확인하세요)")

        self.homography = H
        return H

    # -----------------------------------------------------------------
    def pixel_to_world(self, px: float, py: float):
        """픽셀좌표 -> 경기장 실좌표(cm)"""
        if self.homography is None:
            raise RuntimeError("먼저 calibrate_from_image() 또는 load_cached_homography()를 호출하세요.")
        pt = np.array([[px, py]], dtype=np.float32).reshape(-1, 1, 2)
        world = cv2.perspectiveTransform(pt, self.homography)
        return float(world[0, 0, 0]), float(world[0, 0, 1])

    def world_to_pixel(self, wx: float, wy: float):
        """실좌표(cm) -> 픽셀좌표. 위치가 고정된 시설물의 ROI를 역으로 찾을 때 사용."""
        if self.homography is None:
            raise RuntimeError("먼저 calibrate_from_image() 또는 load_cached_homography()를 호출하세요.")
        H_inv = np.linalg.inv(self.homography)
        pt = np.array([[wx, wy]], dtype=np.float32).reshape(-1, 1, 2)
        px = cv2.perspectiveTransform(pt, H_inv)
        return float(px[0, 0, 0]), float(px[0, 0, 1])

    def world_bbox_to_pixel_bbox(self, x_min, y_min, x_max, y_max, image_shape):
        """실좌표 사각형(FA 슬롯 등) -> 픽셀 bbox(x,y,w,h), 이미지 경계 밖으로 나가지 않도록 클램프"""
        corners_world = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
        corners_px = np.array([self.world_to_pixel(wx, wy) for wx, wy in corners_world])
        h, w = image_shape[:2]
        px_x_min = int(np.clip(corners_px[:, 0].min(), 0, w - 1))
        px_x_max = int(np.clip(corners_px[:, 0].max(), 0, w - 1))
        px_y_min = int(np.clip(corners_px[:, 1].min(), 0, h - 1))
        px_y_max = int(np.clip(corners_px[:, 1].max(), 0, h - 1))
        return px_x_min, px_y_min, max(1, px_x_max - px_x_min), max(1, px_y_max - px_y_min)

    def pixels_to_world_batch(self, points_px: np.ndarray):
        """N x 2 픽셀좌표 배열 -> N x 2 실좌표(cm) 배열"""
        if self.homography is None:
            raise RuntimeError("먼저 calibrate_from_image() 또는 load_cached_homography()를 호출하세요.")
        pts = points_px.reshape(-1, 1, 2).astype(np.float32)
        world = cv2.perspectiveTransform(pts, self.homography)
        return world.reshape(-1, 2)

    # -----------------------------------------------------------------
    def save_cached_homography(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"homography": self.homography.tolist()}, f, ensure_ascii=False, indent=2)

    def load_cached_homography(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.homography = np.array(data["homography"], dtype=np.float64)
        return self.homography


# -----------------------------------------------------------------------
# 렌즈 왜곡 보정 (선택적 - 사전에 카메라 캘리브레이션 체커보드로 계수를 구해두면 사용)
# -----------------------------------------------------------------------
class LensUndistorter:
    """
    DJI Neo2 광각렌즈의 배럴 왜곡을 보정합니다.
    camera_matrix, dist_coeffs는 사전에 체커보드 촬영으로 구해서 저장해두는 것을 권장합니다.
    (여기서는 값이 없으면 보정을 건너뛰는 안전한 기본 동작을 제공)
    """
    def __init__(self, camera_matrix=None, dist_coeffs=None):
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs

    def undistort(self, image_bgr: np.ndarray) -> np.ndarray:
        if self.camera_matrix is None or self.dist_coeffs is None:
            return image_bgr  # 보정계수 없으면 원본 그대로 반환
        return cv2.undistort(image_bgr, self.camera_matrix, self.dist_coeffs)

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "camera_matrix": None if self.camera_matrix is None else self.camera_matrix.tolist(),
                "dist_coeffs": None if self.dist_coeffs is None else self.dist_coeffs.tolist(),
            }, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cm = None if data["camera_matrix"] is None else np.array(data["camera_matrix"])
        dc = None if data["dist_coeffs"] is None else np.array(data["dist_coeffs"])
        return cls(cm, dc)
