from ultralytics import YOLO
import cv2
import time
import os
import json
import math
import csv
import re
from collections import defaultdict
from datetime import datetime

import easyocr


# ============================================================
# TRAFFIC AI - COMPLETE INTEGRATED PROTOTYPE
# ============================================================

VIDEO_PATH = "videos/traffic.mp4"
OUTPUT_PATH = "results/traffic_ai_final.mp4"

MODEL_PATH = "yolo11n.pt"
CALIBRATION_PATH = "calibration.json"

RESULTS_DIR = "results"
EVIDENCE_DIR = "results/evidence"
CHALLAN_DIR = "results/challans"

EVENT_LOG = "results/events.csv"


# ============================================================
# SETTINGS
# ============================================================

# Speed
SPEED_LIMIT = 50.0

LINE_A_Y = 450
LINE_B_Y = 650


# Direction
# Change to "UP" if normal traffic moves upward.
EXPECTED_DIRECTION = "DOWN"


# Lane boundaries
# These are provisional and can be adjusted after viewing
# your actual road.
LANE_1_MAX = 640
LANE_2_MAX = 1280


# Pedestrian conflict
CONFLICT_DISTANCE_PIXELS = 120


# Pedestrian crossing zone
# Adjust these according to your video.
PEDESTRIAN_ZONE_Y1 = 400
PEDESTRIAN_ZONE_Y2 = 750


# Minimum trajectory history
MIN_HISTORY = 8


# What-if analysis
WHAT_IF_SPEED = 30.0


# ============================================================
# CREATE DIRECTORIES
# ============================================================

os.makedirs(
    RESULTS_DIR,
    exist_ok=True
)

os.makedirs(
    EVIDENCE_DIR,
    exist_ok=True
)

os.makedirs(
    CHALLAN_DIR,
    exist_ok=True
)


# ============================================================
# LOAD CALIBRATION
# ============================================================

distance_meters = None
point_a = None
point_b = None

if os.path.exists(
    CALIBRATION_PATH
):

    try:

        with open(
            CALIBRATION_PATH,
            "r"
        ) as file:

            calibration = json.load(
                file
            )

        distance_meters = float(
            calibration[
                "distance_meters"
            ]
        )

        point_a = (
            calibration[
                "point_1"
            ]["x"],

            calibration[
                "point_1"
            ]["y"]
        )

        point_b = (
            calibration[
                "point_2"
            ]["x"],

            calibration[
                "point_2"
            ]["y"]
        )

        print(
            "\nCalibration loaded:"
        )

        print(
            f"P1: {point_a}"
        )

        print(
            f"P2: {point_b}"
        )

        print(
            f"Distance: "
            f"{distance_meters} m"
        )

    except Exception as e:

        print(
            "WARNING: Calibration error:",
            e
        )

else:

    print(
        "\nWARNING:"
    )

    print(
        "calibration.json not found."
    )

    print(
        "Speed will be unavailable."
    )


# ============================================================
# LOAD YOLO
# ============================================================

print(
    "\nLoading YOLO..."
)

model = YOLO(
    MODEL_PATH
)

print(
    "YOLO loaded successfully."
)


# ============================================================
# LOAD OCR
# ============================================================

print(
    "\nLoading OCR..."
)

ocr_reader = easyocr.Reader(
    ["en"],
    gpu=False
)

print(
    "OCR loaded successfully."
)


# ============================================================
# OPEN VIDEO
# ============================================================

cap = cv2.VideoCapture(
    VIDEO_PATH
)

if not cap.isOpened():

    print(
        "ERROR: Could not open video."
    )

    exit()


width = int(
    cap.get(
        cv2.CAP_PROP_FRAME_WIDTH
    )
)

height = int(
    cap.get(
        cv2.CAP_PROP_FRAME_HEIGHT
    )
)

video_fps = cap.get(
    cv2.CAP_PROP_FPS
)

if video_fps <= 0:

    video_fps = 30.0


total_frames = int(
    cap.get(
        cv2.CAP_PROP_FRAME_COUNT
    )
)


print(
    f"\nResolution: "
    f"{width} x {height}"
)

print(
    f"Video FPS: "
    f"{video_fps:.2f}"
)

print(
    f"Total frames: "
    f"{total_frames}"
)


# ============================================================
# OUTPUT VIDEO
# ============================================================

fourcc = cv2.VideoWriter_fourcc(
    *"avc1"
)

out = cv2.VideoWriter(
    OUTPUT_PATH,
    fourcc,
    video_fps,
    (width, height)
)


if not out.isOpened():

    print(
        "avc1 unavailable."
    )

    print(
        "Using mp4v."
    )

    fourcc = cv2.VideoWriter_fourcc(
        *"mp4v"
    )

    out = cv2.VideoWriter(
        OUTPUT_PATH,
        fourcc,
        video_fps,
        (width, height)
    )


if not out.isOpened():

    print(
        "ERROR: Could not create output."
    )

    cap.release()

    exit()


# ============================================================
# DATA STRUCTURES
# ============================================================

# Vehicle trajectories
vehicle_history = defaultdict(list)


# Pedestrian trajectories
pedestrian_history = defaultdict(list)


# Line A crossing frame
line_a_frames = {}


# Vehicle speeds
vehicle_speeds = {}


# Vehicle direction
vehicle_directions = {}


# Vehicle lane
vehicle_lanes = {}


# Previous lane
previous_lane = {}


# Lane transition counter
lane_transition_frames = defaultdict(int)


# Plates
vehicle_plates = {}


# OCR last attempt frame
last_ocr_frame = {}


# Violations
overspeed_ids = set()
wrong_way_ids = set()
lane_change_ids = set()
pedestrian_conflict_ids = set()
illegal_crossing_ids = set()


# Evidence that has already been saved
evidence_saved = set()


# Track classes
track_classes = {}


# ============================================================
# EVENT CSV
# ============================================================

if not os.path.exists(
    EVENT_LOG
):

    with open(
        EVENT_LOG,
        "w",
        newline=""
    ) as file:

        writer = csv.writer(
            file
        )

        writer.writerow([
            "frame",
            "timestamp",
            "vehicle_id",
            "event",
            "speed_kmh",
            "plate",
            "evidence"
        ])


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_direction(history):

    if len(history) < MIN_HISTORY:

        return "UNKNOWN"


    old_x, old_y = history[
        -MIN_HISTORY
    ]

    new_x, new_y = history[-1]


    dx = new_x - old_x
    dy = new_y - old_y


    if (
        abs(dx) < 5
        and abs(dy) < 5
    ):

        return "STATIONARY"


    if abs(dy) >= abs(dx):

        if dy > 0:

            return "DOWN"

        return "UP"


    if dx > 0:

        return "RIGHT"

    return "LEFT"


# ------------------------------------------------------------


def get_lane(x):

    if x < LANE_1_MAX:

        return 1

    if x < LANE_2_MAX:

        return 2

    return 3


# ------------------------------------------------------------


def distance_between(
    p1,
    p2
):

    return math.sqrt(
        (
            p1[0] -
            p2[0]
        ) ** 2
        +
        (
            p1[1] -
            p2[1]
        ) ** 2
    )


# ------------------------------------------------------------


def read_plate(
    frame,
    box
):

    x1, y1, x2, y2 = box


    h, w = frame.shape[:2]


    x1 = max(
        0,
        int(x1)
    )

    y1 = max(
        0,
        int(y1)
    )

    x2 = min(
        w,
        int(x2)
    )

    y2 = min(
        h,
        int(y2)
    )


    if (
        x2 <= x1
        or y2 <= y1
    ):

        return None


    vehicle = frame[
        y1:y2,
        x1:x2
    ]


    if vehicle.size == 0:

        return None


    vh = vehicle.shape[0]


    # Lower part of vehicle
    plate_region = vehicle[
        int(vh * 0.40):vh,
        :
    ]


    if plate_region.size == 0:

        return None


    # Upscale
    plate_region = cv2.resize(
        plate_region,
        None,
        fx=2.5,
        fy=2.5,
        interpolation=cv2.INTER_CUBIC
    )


    gray = cv2.cvtColor(
        plate_region,
        cv2.COLOR_BGR2GRAY
    )


    gray = cv2.GaussianBlur(
        gray,
        (3, 3),
        0
    )


    # OCR
    results = ocr_reader.readtext(
        gray,
        detail=1
    )


    candidates = []


    for detection in results:

        text = detection[1]
        confidence = detection[2]


        cleaned = re.sub(
            r"[^A-Z0-9]",
            "",
            text.upper()
        )


        if (
            len(cleaned) >= 4
            and confidence >= 0.25
        ):

            candidates.append(
                (
                    cleaned,
                    confidence
                )
            )


    if not candidates:

        return None


    # Prefer highest confidence
    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )


    return candidates[0][0]


# ------------------------------------------------------------


def save_event(
    frame,
    frame_number,
    vehicle_id,
    event,
    speed=None
):

    key = (
        vehicle_id,
        event
    )


    if key in evidence_saved:

        return None


    evidence_saved.add(
        key
    )


    timestamp = (
        frame_number /
        video_fps
    )


    filename = (
        f"ID_{vehicle_id}_"
        f"{event}_"
        f"{frame_number}.jpg"
    )


    evidence_path = os.path.join(
        EVIDENCE_DIR,
        filename
    )


    cv2.imwrite(
        evidence_path,
        frame
    )


    plate = vehicle_plates.get(
        vehicle_id,
        "PENDING"
    )


    with open(
        EVENT_LOG,
        "a",
        newline=""
    ) as file:

        writer = csv.writer(
            file
        )

        writer.writerow([
            frame_number,
            f"{timestamp:.2f}",
            vehicle_id,
            event,
            (
                f"{speed:.2f}"
                if speed is not None
                else ""
            ),
            plate,
            evidence_path
        ])


    print(
        f"[EVENT] "
        f"ID {vehicle_id}: "
        f"{event}"
    )


    return evidence_path


# ------------------------------------------------------------


def create_challan(
    vehicle_id,
    violation,
    speed=None,
    evidence=None
):

    plate = vehicle_plates.get(
        vehicle_id,
        "NOT_RECOGNIZED"
    )


    challan = {

        "challan_type":
            "SIMULATED",

        "vehicle_id":
            vehicle_id,

        "vehicle_number":
            plate,

        "violation":
            violation,

        "speed_kmh":
            (
                round(speed, 2)
                if speed is not None
                else None
            ),

        "speed_limit":
            SPEED_LIMIT,

        "date_time":
            datetime.now().isoformat(),

        "location":
            "Demo Traffic Camera",

        "evidence":
            evidence,

        "status":
            "DEMO ONLY"
    }


    filename = (
        f"challan_ID_"
        f"{vehicle_id}_"
        f"{violation}.json"
    )


    path = os.path.join(
        CHALLAN_DIR,
        filename
    )


    with open(
        path,
        "w"
    ) as file:

        json.dump(
            challan,
            file,
            indent=4
        )


    return path


# ------------------------------------------------------------


def what_if_analysis(
    actual_speed
):

    if actual_speed <= 0:

        return {
            "actual_speed": None,
            "what_if_speed": WHAT_IF_SPEED,
            "actual_risk": "UNKNOWN",
            "what_if_risk": "UNKNOWN"
        }


    # Simple prototype risk index.
    #
    # Risk is NOT a real accident probability.
    # It is a relative demonstration metric.

    actual_risk = (
        actual_speed /
        max(SPEED_LIMIT, 1)
    )


    what_if_risk = (
        WHAT_IF_SPEED /
        max(SPEED_LIMIT, 1)
    )


    if actual_risk >= 1.0:

        actual_label = "HIGH"

    elif actual_risk >= 0.7:

        actual_label = "MEDIUM"

    else:

        actual_label = "LOW"


    if what_if_risk >= 1.0:

        what_if_label = "HIGH"

    elif what_if_risk >= 0.7:

        what_if_label = "MEDIUM"

    else:

        what_if_label = "LOW"


    return {

        "actual_speed":
            round(actual_speed, 2),

        "what_if_speed":
            WHAT_IF_SPEED,

        "actual_risk":
            actual_label,

        "what_if_risk":
            what_if_label
    }


# ------------------------------------------------------------


def closest_pedestrian(
    vehicle_point,
    pedestrians
):

    nearest_id = None
    nearest_distance = float(
        "inf"
    )


    for (
        pedestrian_id,
        point
    ) in pedestrians.items():

        d = distance_between(
            vehicle_point,
            point
        )


        if d < nearest_distance:

            nearest_distance = d

            nearest_id = (
                pedestrian_id
            )


    return (
        nearest_id,
        nearest_distance
    )


# ============================================================
# MAIN PROCESSING
# ============================================================

frame_number = 0

previous_time = time.time()

print(
    "\n======================================"
)

print(
    "TRAFFIC AI FINAL PROTOTYPE"
)

print(
    "======================================"
)

print(
    "Detection"
)

print(
    "Tracking"
)

print(
    "Speed"
)

print(
    "Overspeed"
)

print(
    "Wrong-way"
)

print(
    "Lane-change"
)

print(
    "Pedestrian analysis"
)

print(
    "ANPR"
)

print(
    "Evidence"
)

print(
    "What-If analysis"
)

print(
    "Simulated e-Challan"
)

print(
    "======================================\n"
)


while True:

    ret, frame = cap.read()


    if not ret:

        break


    frame_number += 1


    # ========================================================
    # YOLO TRACKING
    # ========================================================

    results = model.track(

        frame,

        persist=True,

        tracker="bytetrack.yaml",

        classes=[
            0,  # person
            2,  # car
            3,  # motorcycle
            5,  # bus
            7   # truck
        ],

        verbose=False
    )


    result = results[0]


    output_frame = result.plot()


    # ========================================================
    # CURRENT PEDESTRIANS
    # ========================================================

    current_pedestrians = {}


    # ========================================================
    # PROCESS TRACKS
    # ========================================================

    if (
        result.boxes is not None
        and result.boxes.id is not None
    ):

        boxes = (
            result.boxes.xyxy
            .cpu()
            .tolist()
        )


        ids = (
            result.boxes.id
            .int()
            .cpu()
            .tolist()
        )


        classes = (
            result.boxes.cls
            .int()
            .cpu()
            .tolist()
        )


        confidences = (
            result.boxes.conf
            .cpu()
            .tolist()
        )


        for (
            box,
            track_id,
            cls,
            confidence
        ) in zip(
            boxes,
            ids,
            classes,
            confidences
        ):

            x1, y1, x2, y2 = map(
                int,
                box
            )


            cx = int(
                (x1 + x2) / 2
            )


            cy = int(y2)


            # =================================================
            # PEDESTRIAN
            # =================================================

            if cls == 0:

                phistory = (
                    pedestrian_history[
                        track_id
                    ]
                )


                phistory.append(
                    (cx, cy)
                )


                if len(phistory) > 25:

                    phistory.pop(0)


                current_pedestrians[
                    track_id
                ] = (cx, cy)


                # ---------------------------------------------
                # Pedestrian crossing analysis
                # ---------------------------------------------

                if (
                    len(phistory) >= MIN_HISTORY
                ):

                    old_y = phistory[
                        -MIN_HISTORY
                    ][1]

                    new_y = phistory[-1][1]


                    # Detect movement through road zone
                    if (
                        old_y <
                        PEDESTRIAN_ZONE_Y1
                        and
                        new_y >
                        PEDESTRIAN_ZONE_Y2
                    ) or (
                        old_y >
                        PEDESTRIAN_ZONE_Y2
                        and
                        new_y <
                        PEDESTRIAN_ZONE_Y1
                    ):

                        illegal_crossing_ids.add(
                            track_id
                        )


                continue


            # =================================================
            # VEHICLE
            # =================================================

            if cls not in [
                2,
                3,
                5,
                7
            ]:

                continue


            track_classes[
                track_id
            ] = cls


            vhistory = (
                vehicle_history[
                    track_id
                ]
            )


            vhistory.append(
                (cx, cy)
            )


            if len(vhistory) > 30:

                vhistory.pop(0)


            # =================================================
            # ANPR
            # =================================================

            # OCR only every 15 frames per vehicle
            # to avoid running OCR on every frame.

            if (
                track_id not in vehicle_plates
                and
                (
                    track_id
                    not in last_ocr_frame
                    or
                    frame_number -
                    last_ocr_frame[
                        track_id
                    ] >= 15
                )
            ):

                last_ocr_frame[
                    track_id
                ] = frame_number


                plate = read_plate(
                    frame,
                    (
                        x1,
                        y1,
                        x2,
                        y2
                    )
                )


                if plate:

                    vehicle_plates[
                        track_id
                    ] = plate


                    print(
                        f"[ANPR] "
                        f"Vehicle "
                        f"{track_id}: "
                        f"{plate}"
                    )


            # =================================================
            # DIRECTION
            # =================================================

            direction = get_direction(
                vhistory
            )


            vehicle_directions[
                track_id
            ] = direction


            # =================================================
            # WRONG-WAY
            # =================================================

            if (
                len(vhistory) >= 12
                and
                direction != "UNKNOWN"
                and
                direction != "STATIONARY"
                and
                direction != EXPECTED_DIRECTION
            ):

                wrong_way_ids.add(
                    track_id
                )


                evidence = save_event(
                    output_frame,
                    frame_number,
                    track_id,
                    "WRONG_WAY"
                )


                if evidence:

                    create_challan(
                        track_id,
                        "WRONG_WAY",
                        evidence=evidence
                    )


            # =================================================
            # LANE
            # =================================================

            current_lane = get_lane(
                cx
            )


            vehicle_lanes[
                track_id
            ] = current_lane


            if track_id not in previous_lane:

                previous_lane[
                    track_id
                ] = current_lane


            else:

                old_lane = (
                    previous_lane[
                        track_id
                    ]
                )


                if current_lane != old_lane:

                    lane_transition_frames[
                        track_id
                    ] += 1


                    # Require vehicle to stay
                    # in new lane for multiple frames.

                    if (
                        lane_transition_frames[
                            track_id
                        ] >= 8
                    ):

                        lane_change_ids.add(
                            track_id
                        )


                        evidence = save_event(
                            output_frame,
                            frame_number,
                            track_id,
                            "LANE_CHANGE"
                        )


                        if evidence:

                            create_challan(
                                track_id,
                                "LANE_CHANGE",
                                evidence=evidence
                            )


                        previous_lane[
                            track_id
                        ] = current_lane


                        lane_transition_frames[
                            track_id
                        ] = 0


                else:

                    lane_transition_frames[
                        track_id
                    ] = 0


            # =================================================
            # SPEED - LINE A
            # =================================================

            if (
                distance_meters is not None
                and
                track_id not in line_a_frames
                and
                cy >= LINE_A_Y
                and
                direction ==
                EXPECTED_DIRECTION
            ):

                line_a_frames[
                    track_id
                ] = frame_number


            # =================================================
            # SPEED - LINE B
            # =================================================

            if (
                distance_meters is not None
                and
                track_id in line_a_frames
                and
                track_id not in vehicle_speeds
                and
                cy >= LINE_B_Y
                and
                direction ==
                EXPECTED_DIRECTION
            ):

                start_frame = (
                    line_a_frames[
                        track_id
                    ]
                )


                frames_taken = (
                    frame_number -
                    start_frame
                )


                elapsed_seconds = (
                    frames_taken /
                    video_fps
                )


                if elapsed_seconds > 0:

                    speed_mps = (
                        distance_meters /
                        elapsed_seconds
                    )


                    speed_kmh = (
                        speed_mps *
                        3.6
                    )


                    vehicle_speeds[
                        track_id
                    ] = speed_kmh


                    # -----------------------------------------
                    # Overspeed
                    # -----------------------------------------

                    if (
                        speed_kmh >
                        SPEED_LIMIT
                    ):

                        overspeed_ids.add(
                            track_id
                        )


                        evidence = save_event(
                            output_frame,
                            frame_number,
                            track_id,
                            "OVERSPEED",
                            speed_kmh
                        )


                        if evidence:

                            create_challan(
                                track_id,
                                "OVERSPEED",
                                speed_kmh,
                                evidence
                            )


            # =================================================
            # WHAT-IF ANALYSIS
            # =================================================

            if track_id in vehicle_speeds:

                speed = vehicle_speeds[
                    track_id
                ]


                what_if = what_if_analysis(
                    speed
                )


                # Display only for violations
                if track_id in overspeed_ids:

                    cv2.putText(
                        output_frame,
                        (
                            "WHAT-IF: "
                            f"{WHAT_IF_SPEED:.0f} km/h "
                            f"-> "
                            f"{what_if['what_if_risk']} RISK"
                        ),
                        (
                            x1,
                            min(
                                y2 + 135,
                                height - 20
                            )
                        ),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 255),
                        2
                    )


            # =================================================
            # VEHICLE TRAJECTORY
            # =================================================

            for i in range(
                1,
                len(vhistory)
            ):

                cv2.line(
                    output_frame,
                    vhistory[i - 1],
                    vhistory[i],
                    (255, 255, 255),
                    2
                )


            # =================================================
            # VEHICLE LABEL
            # =================================================

            label = (
                f"ID {track_id}"
                f" | {direction}"
                f" | L{current_lane}"
            )


            cv2.putText(
                output_frame,
                label,
                (
                    x1,
                    max(
                        y1 - 12,
                        25
                    )
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2
            )


            # =================================================
            # PLATE LABEL
            # =================================================

            if track_id in vehicle_plates:

                plate = vehicle_plates[
                    track_id
                ]


                cv2.putText(
                    output_frame,
                    f"PLATE: {plate}",
                    (
                        x1,
                        y2 + 105
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2
                )


            # =================================================
            # SPEED LABEL
            # =================================================

            if track_id in vehicle_speeds:

                speed = vehicle_speeds[
                    track_id
                ]


                cv2.putText(
                    output_frame,
                    f"{speed:.1f} km/h",
                    (
                        x1,
                        y1 + 20
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2
                )


            # =================================================
            # VIOLATION LABELS
            # =================================================

            if track_id in overspeed_ids:

                cv2.putText(
                    output_frame,
                    "OVERSPEEDING!",
                    (
                        x1,
                        y2 + 30
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )


            if track_id in wrong_way_ids:

                cv2.putText(
                    output_frame,
                    "WRONG WAY!",
                    (
                        x1,
                        y2 + 55
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )


            if track_id in lane_change_ids:

                cv2.putText(
                    output_frame,
                    "LANE CHANGE!",
                    (
                        x1,
                        y2 + 80
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 165, 255),
                    2
                )


    # ========================================================
    # VEHICLE - PEDESTRIAN CONFLICT
    # ========================================================

    for (
        vehicle_id,
        vhistory
    ) in vehicle_history.items():

        if not vhistory:

            continue


        vehicle_point = vhistory[-1]


        pedestrian_id, distance = (
            closest_pedestrian(
                vehicle_point,
                current_pedestrians
            )
        )


        if (
            pedestrian_id is not None
            and
            distance <
            CONFLICT_DISTANCE_PIXELS
        ):

            pedestrian_conflict_ids.add(
                vehicle_id
            )


            cv2.line(
                output_frame,
                vehicle_point,
                current_pedestrians[
                    pedestrian_id
                ],
                (0, 0, 255),
                3
            )


            cv2.circle(
                output_frame,
                vehicle_point,
                CONFLICT_DISTANCE_PIXELS,
                (0, 0, 255),
                2
            )


            cv2.putText(
                output_frame,
                "PEDESTRIAN CONFLICT",
                (
                    vehicle_point[0] - 80,
                    vehicle_point[1] - 20
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 0, 255),
                2
            )


            evidence = save_event(
                output_frame,
                frame_number,
                vehicle_id,
                "PEDESTRIAN_CONFLICT"
            )


            if evidence:

                create_challan(
                    vehicle_id,
                    "PEDESTRIAN_CONFLICT",
                    evidence=evidence
                )


    # ========================================================
    # DRAW PEDESTRIAN ZONE
    # ========================================================

    cv2.line(
        output_frame,
        (0, PEDESTRIAN_ZONE_Y1),
        (
            width,
            PEDESTRIAN_ZONE_Y1
        ),
        (255, 255, 255),
        2
    )


    cv2.line(
        output_frame,
        (0, PEDESTRIAN_ZONE_Y2),
        (
            width,
            PEDESTRIAN_ZONE_Y2
        ),
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        "PEDESTRIAN ZONE",
        (
            20,
            PEDESTRIAN_ZONE_Y1 - 10
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2
    )


    # ========================================================
    # DRAW SPEED LINES
    # ========================================================

    cv2.line(
        output_frame,
        (0, LINE_A_Y),
        (width, LINE_A_Y),
        (255, 255, 255),
        3
    )


    cv2.line(
        output_frame,
        (0, LINE_B_Y),
        (width, LINE_B_Y),
        (255, 255, 255),
        3
    )


    cv2.putText(
        output_frame,
        "A - SPEED START",
        (
            20,
            LINE_A_Y - 10
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        "B - SPEED END",
        (
            20,
            LINE_B_Y - 10
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2
    )


    # ========================================================
    # DRAW LANES
    # ========================================================

    cv2.line(
        output_frame,
        (LANE_1_MAX, 0),
        (
            LANE_1_MAX,
            height
        ),
        (255, 255, 255),
        2
    )


    cv2.line(
        output_frame,
        (LANE_2_MAX, 0),
        (
            LANE_2_MAX,
            height
        ),
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        "LANE 1",
        (100, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        "LANE 2",
        (750, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        "LANE 3",
        (1450, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    # ========================================================
    # PROCESSING FPS
    # ========================================================

    current_time = time.time()


    processing_fps = (
        1 /
        max(
            current_time -
            previous_time,
            0.001
        )
    )


    previous_time = current_time


    # ========================================================
    # DASHBOARD
    # ========================================================

    visible = (
        len(result.boxes)
        if result.boxes is not None
        else 0
    )


    cv2.rectangle(
        output_frame,
        (10, 10),
        (500, 210),
        (0, 0, 0),
        -1
    )


    cv2.putText(
        output_frame,
        "TRAFFIC AI",
        (25, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        f"Objects: {visible}",
        (25, 68),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        f"Processing: {processing_fps:.1f} FPS",
        (25, 94),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        f"Overspeed: {len(overspeed_ids)}",
        (25, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        f"Wrong Way: {len(wrong_way_ids)}",
        (25, 146),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        f"Lane Change: {len(lane_change_ids)}",
        (25, 172),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2
    )


    cv2.putText(
        output_frame,
        f"Ped Conflict: {len(pedestrian_conflict_ids)}",
        (25, 198),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (255, 255, 255),
        2
    )


       # ========================================================
       # SAVE OUTPUT
       # ========================================================

    out.write(output_frame)

       # GUI preview disabled because this OpenCV
       # installation does not support cv2.imshow().


# ============================================================
# CLEANUP
# ============================================================

cap.release()

out.release()

# GUI cleanup not required.


# ============================================================
# FINAL SUMMARY
# ============================================================

print(
    "\n======================================"
)

print(
    "TRAFFIC AI ANALYSIS COMPLETE"
)

print(
    "======================================"
)


print(
    f"\nOutput video:"
)

print(
    OUTPUT_PATH
)


print(
    f"\nEvent log:"
)

print(
    EVENT_LOG
)


print(
    "\nEvidence:"
)

print(
    EVIDENCE_DIR
)


print(
    "\nSimulated challans:"
)

print(
    CHALLAN_DIR
)


print(
    "\n--------------------------------------"
)

print(
    "VIOLATION SUMMARY"
)

print(
    "--------------------------------------"
)


print(
    f"Overspeed: "
    f"{len(overspeed_ids)}"
)


print(
    f"Wrong-way: "
    f"{len(wrong_way_ids)}"
)


print(
    f"Lane changes: "
    f"{len(lane_change_ids)}"
)


print(
    f"Pedestrian conflicts: "
    f"{len(pedestrian_conflict_ids)}"
)


print(
    f"Pedestrian crossings: "
    f"{len(illegal_crossing_ids)}"
)


print(
    "\n--------------------------------------"
)

print(
    "ANPR RESULTS"
)

print(
    "--------------------------------------"
)


if vehicle_plates:

    for vehicle_id, plate in (
        vehicle_plates.items()
    ):

        print(
            f"Vehicle {vehicle_id}: "
            f"{plate}"
        )

else:

    print(
        "No plates recognized."
    )


print(
    "\n--------------------------------------"
)

print(
    "SPEED RESULTS"
)

print(
    "--------------------------------------"
)


if vehicle_speeds:

    for vehicle_id, speed in (
        vehicle_speeds.items()
    ):

        print(
            f"Vehicle {vehicle_id}: "
            f"{speed:.2f} km/h"
        )

else:

    print(
        "No calibrated speeds."
    )


print(
    "\n======================================"
)

print(
    "DONE"
)

print(
    "======================================"
)