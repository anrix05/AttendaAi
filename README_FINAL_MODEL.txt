# Final Attendance Recognition Model

## What changed

The old model used a fixed VIT roster and four YOLO classes. That is removed.

The new training pipeline creates two useful classes:

- `ABSENT_MARK`: A / absence mark
- `PRESENT_MARK`: signature OR P annotation

Therefore **every detected signature is PRESENT**.

Student information is obtained from the uploaded sheet through OCR. The engine does not contain a hard-coded student list and does not assume exactly 30 students.

## Files

- `train_attendance_model.py` — converts the existing dataset and trains the final YOLO model.
- `attendance_engine.py` — dynamic OCR + table/grid + YOLO attendance engine.
- `requirements_attendance_final.txt` — required Python packages.

## Train

From:

`C:\Users\User\Desktop\AttendanceSystem\attendance_platform`

run:

```powershell
python -m pip install -r requirements_attendance_final.txt
python train_attendance_model.py
```

The trained model will be:

`weights\attendance_marks_final.pt`

## OCR prerequisite

Install Tesseract OCR on Windows and make sure `tesseract.exe` is in PATH.

Check:

```powershell
tesseract --version
```

If it is installed but not in PATH, set it in Python before creating the engine:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## Test the engine

```powershell
python attendance_engine.py "path\to\attendance_sheet.jpg"
```

## Important

The model can be trained from the current dataset, but a truly reliable model for arbitrary handwriting requires representative training images from the actual sheets you expect to process. The script therefore uses transfer learning, conservative augmentation, and combines `P` + `signature` into PRESENT.

Do not use the old `VIT_STUDENT_ROSTER`, `cluster_by_column`, or `map_to_roster` functions with this engine.
