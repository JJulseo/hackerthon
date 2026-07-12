# -*- coding: utf-8 -*-
"""
generate_test_scene.py
=======================
실제 드론 촬영 사진이 없는 상태에서도 전체 파이프라인이 정상 동작하는지 검증하기 위해,
ArUco 마커 + 경기장 구획 + 미션 객체(폭파구/불발탄/시설물)를 합성한 테스트 이미지를 만듭니다.

이 스크립트가 만드는 시나리오:
  - RW-03, RW-07 구간에 폭파구 배치 -> 최장 가용구간은 RW-08~RW-10 (3칸=150m) 이어야 함
    (RW-04~06도 3칸이지만 먼저 나오는 순서 정책상 RW-04가 먼저 선택될 수 있음 -> 실행 결과로 확인)
  - RW-05에 자탄(uxo) 배치 -> 활주로 불발탄 개수 1개로 집계되어야 함
  - TW-B2에 포탄 배치 -> 활주로 불발탄 집계에는 포함되지 않아야 함(유도로이므로)
  - FA-02(관제레이더)에 화재 표시, FA-03(격납고)에 파손 표시, 나머지는 정상
"""
import os
import sys
import numpy as np
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import field_config as fc

PX_PER_CM = 3
MARGIN_PX = 60


def world_to_canvas(wx, wy):
    return int(MARGIN_PX + wx * PX_PER_CM), int(MARGIN_PX + wy * PX_PER_CM)


def draw_field_base(canvas):
    """활주로/유도로/시설물 구역을 색으로 구분해서 그림"""
    zone_colors = {
        "RW": (130, 130, 130),   # 활주로: 회색 아스팔트 (탐지 임계값과 확실히 구분되는 밝기)
        "TW": (140, 160, 140),   # 유도로: 녹색빛 도는 회색
        "FA": (170, 170, 170),   # 시설물 구역: 밝은 회색
    }
    for seg_name, b in fc.SEGMENTS.items():
        color = zone_colors.get(seg_name[:2], (120, 120, 120))
        p1 = world_to_canvas(b["x_min"], b["y_min"])
        p2 = world_to_canvas(b["x_max"], b["y_max"])
        cv2.rectangle(canvas, p1, p2, color, thickness=-1)
        cv2.rectangle(canvas, p1, p2, (40, 40, 40), thickness=1)
        cv2.putText(canvas, seg_name, (p1[0] + 3, p1[1] + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (20, 20, 20), 1, cv2.LINE_AA)
    return canvas


def draw_aruco_markers(canvas, aruco_dict):
    """4개 모서리 마커를 grid 좌표에 렌더링 (흰색 여백/quiet zone 포함 - 검출에 필수)"""
    marker_core_px = 50
    quiet_zone_px = 16  # 마커 주변 흰 여백 두께
    block_size = marker_core_px + 2 * quiet_zone_px

    for marker_id, (wx, wy) in fc.ARUCO_MARKER_WORLD_POSITIONS.items():
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_core_px)
        # 흰 배경 블록 위에 마커를 중앙 배치 -> quiet zone 확보
        block = np.full((block_size, block_size), 255, dtype=np.uint8)
        block[quiet_zone_px:quiet_zone_px + marker_core_px,
              quiet_zone_px:quiet_zone_px + marker_core_px] = marker_img
        block_bgr = cv2.cvtColor(block, cv2.COLOR_GRAY2BGR)

        cx, cy = world_to_canvas(wx, wy)
        x0, y0 = cx - block_size // 2, cy - block_size // 2
        h, w = canvas.shape[:2]
        x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(w, x0 + block_size), min(h, y0 + block_size)
        if x1c > x0c and y1c > y0c:
            canvas[y0c:y1c, x0c:x1c] = block_bgr[
                (y0c - y0):(y1c - y0), (x0c - x0):(x1c - x0)
            ]
    return canvas


def draw_crater(canvas, segment_name, size_class="중형"):
    """지정 구간 중앙에 검정 불규칙 blob(폭파구)을 그림"""
    b = fc.SEGMENTS[segment_name]
    cx_world = (b["x_min"] + b["x_max"]) / 2
    cy_world = (b["y_min"] + b["y_max"]) / 2
    cx, cy = world_to_canvas(cx_world, cy_world)

    dims = fc.CRATER_SIZE_TABLE_MM[size_class]
    radius_cm = (dims["w"] / 10.0) / 2.0  # mm -> cm -> 반지름
    radius_px = max(6, int(radius_cm * PX_PER_CM))

    # 완전한 원이 아니라 살짝 불규칙한 다각형으로 그려서 '자연스러운' 폭파구 형태 흉내
    rng = np.random.default_rng(abs(hash(segment_name)) % (2**32))
    angles = np.linspace(0, 2 * np.pi, 14)
    pts = []
    for a in angles:
        r = radius_px * (0.8 + 0.4 * rng.random())
        pts.append((int(cx + r * np.cos(a)), int(cy + r * np.sin(a))))
    cv2.fillPoly(canvas, [np.array(pts, dtype=np.int32)], (15, 15, 15))
    return cx_world, cy_world


def draw_uxo(canvas, segment_name, uxo_type="자탄", offset_cm=(0, 0)):
    """지정 구간에 불발탄 형태(원형/타원형)를 그림"""
    b = fc.SEGMENTS[segment_name]
    cx_world = (b["x_min"] + b["x_max"]) / 2 + offset_cm[0]
    cy_world = (b["y_min"] + b["y_max"]) / 2 + offset_cm[1]
    cx, cy = world_to_canvas(cx_world, cy_world)

    dims = fc.UXO_SIZE_TABLE_MM[uxo_type]
    w_px = max(4, int((dims["w"] / 10.0) * PX_PER_CM))
    d_px = max(4, int((dims["d"] / 10.0) * PX_PER_CM))
    # 종횡비를 실제 치수 비율대로 타원으로 표현 (세로가 긴 형태)
    cv2.ellipse(canvas, (cx, cy), (w_px // 2, d_px // 2), 0, 0, 360, (30, 30, 30), -1)
    return cx_world, cy_world


def draw_facility_state(canvas, slot, state="정상"):
    """FA 슬롯 영역에 상태별 색상 오버레이"""
    b = fc.SEGMENTS[slot]
    p1 = world_to_canvas(b["x_min"] + 5, b["y_min"] + 5)
    p2 = world_to_canvas(b["x_max"] - 5, b["y_max"] - 5)

    if state == "화재":
        cv2.rectangle(canvas, p1, p2, (0, 90, 230), -1)   # 주황/빨강 계열(BGR)
    elif state == "파손":
        cv2.rectangle(canvas, p1, p2, (25, 25, 25), -1)   # 어두운 잔해 색
    else:
        cv2.rectangle(canvas, p1, p2, (170, 170, 170), -1)  # 정상(밝은 회색 건물)
    cv2.putText(canvas, f"{slot}:{state}", (p1[0], p1[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1, cv2.LINE_AA)


def generate_scene(seed=0, fire_flicker_phase=0.0):
    dict_id = getattr(cv2.aruco, fc.ARUCO_DICT_NAME)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)

    canvas_w = fc.FIELD_WIDTH_CM * PX_PER_CM + 2 * MARGIN_PX
    canvas_h = fc.FIELD_HEIGHT_CM * PX_PER_CM + 2 * MARGIN_PX
    canvas = np.full((canvas_h, canvas_w, 3), 200, dtype=np.uint8)  # 밝은 배경(잔디 등)

    draw_field_base(canvas)

    # ---- 시나리오 배치 ----
    draw_crater(canvas, "RW-03", "중형")
    draw_crater(canvas, "RW-07", "대형")

    draw_uxo(canvas, "RW-05", "자탄")
    draw_uxo(canvas, "TW-B2", "포탄")
    draw_uxo(canvas, "RW-09", "미사일", offset_cm=(15, 0))

    draw_facility_state(canvas, "FA-01", "정상")
    # 화재는 깜빡임을 흉내내기 위해 프레임마다 밝기를 살짝 변화
    fire_state = "화재"
    draw_facility_state(canvas, "FA-02", fire_state)
    draw_facility_state(canvas, "FA-03", "파손")
    draw_facility_state(canvas, "FA-04", "정상")
    draw_facility_state(canvas, "FA-05", "정상")
    draw_facility_state(canvas, "FA-06", "정상")

    draw_aruco_markers(canvas, aruco_dict)

    # 프레임 간 미세한 노이즈(카메라 센서 노이즈 흉내) 추가 - 재현성 위해 seed 사용
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1.5, canvas.shape).astype(np.int16)
    noisy = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 화재 영역만 프레임마다 밝기를 흔들어 '깜빡임'을 시뮬레이션
    b = fc.SEGMENTS["FA-02"]
    p1 = world_to_canvas(b["x_min"] + 5, b["y_min"] + 5)
    p2 = world_to_canvas(b["x_max"] - 5, b["y_max"] - 5)
    flicker = int(30 * np.sin(fire_flicker_phase))
    noisy[p1[1]:p2[1], p1[0]:p2[0]] = np.clip(
        noisy[p1[1]:p2[1], p1[0]:p2[0]].astype(np.int16) + flicker, 0, 255
    ).astype(np.uint8)

    return noisy


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    frames = []
    for i in range(4):
        frame = generate_scene(seed=i, fire_flicker_phase=i * 1.6)
        path = os.path.join(out_dir, f"frame_{i:02d}.png")
        cv2.imwrite(path, frame)
        frames.append(path)
        print(f"생성됨: {path}  (shape={frame.shape})")
    return frames


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "test_images"
    main(out)
