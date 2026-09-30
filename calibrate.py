import cv2
import json
import os

VIDEO_PATH = "videos/traffic.mp4"
CALIBRATION_PATH = "calibration.json"

# ---------------------------------
# Open video
# ---------------------------------

cap = cv2.VideoCapture(VIDEO_PATH)

if not cap.isOpened():
    print("ERROR: Could not open video.")
    exit()

total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
middle_frame = total_frames // 2

cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)

ret, frame = cap.read()

if not ret:
    print("ERROR: Could not read frame.")
    cap.release()
    exit()

display = frame.copy()
points = []


# ---------------------------------
# Mouse callback
# ---------------------------------

def mouse_callback(event, x, y, flags, param):

    if event == cv2.EVENT_LBUTTONDOWN:

        if len(points) >= 2:
            return

        points.append((x, y))

        print(
            f"Point {len(points)}: ({x}, {y})"
        )

        cv2.circle(
            display,
            (x, y),
            8,
            (255, 255, 255),
            -1
        )

        cv2.putText(
            display,
            f"P{len(points)}",
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        if len(points) == 2:

            cv2.line(
                display,
                points[0],
                points[1],
                (255, 255, 255),
                3
            )


# ---------------------------------
# Window
# ---------------------------------

cv2.namedWindow("Speed Calibration")

cv2.setMouseCallback(
    "Speed Calibration",
    mouse_callback
)

print("--------------------------------")
print("SPEED CALIBRATION")
print("--------------------------------")
print("Click TWO points on the SAME")
print("vehicle travel path.")
print()
print("Press R to reset.")
print("Press Q to finish.")
print("--------------------------------")


while True:

    cv2.imshow(
        "Speed Calibration",
        display
    )

    key = cv2.waitKey(1) & 0xFF

    if key == ord("r"):

        points.clear()
        display = frame.copy()

        print("Points reset.")

    elif key == ord("q"):
        break


cap.release()
cv2.destroyAllWindows()


# ---------------------------------
# Validate
# ---------------------------------

print("\nSelected points:")

for i, point in enumerate(points):

    print(
        f"P{i + 1}: {point}"
    )


if len(points) != 2:

    print(
        "\nERROR: You need exactly TWO points."
    )

    exit()


# ---------------------------------
# Distance
# ---------------------------------

print("\nCalibration points successfully selected.")

while True:

    distance_input = input(
        "\nEnter REAL distance between "
        "these points in metres: "
    )

    try:

        distance = float(distance_input)

        if distance <= 0:
            print("Distance must be greater than 0.")
            continue

        break

    except ValueError:

        print("Please enter a valid number.")


# ---------------------------------
# Save calibration
# ---------------------------------

calibration = {

    "point_1": {
        "x": points[0][0],
        "y": points[0][1]
    },

    "point_2": {
        "x": points[1][0],
        "y": points[1][1]
    },

    "distance_meters": distance

}


with open(
    CALIBRATION_PATH,
    "w"
) as file:

    json.dump(
        calibration,
        file,
        indent=4
    )


print("\n================================")
print("CALIBRATION SAVED")
print("================================")

print(
    f"P1: {points[0]}"
)

print(
    f"P2: {points[1]}"
)

print(
    f"Distance: {distance} metres"
)

print(
    f"Saved to: {CALIBRATION_PATH}"
)