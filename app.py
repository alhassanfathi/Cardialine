"""
Foundations of Health Informatics - DICOM Flask App
Covers Questions 1a, 1b, 2a, 2b (text), 2c, 3a, 3b, 3c
"""

import struct, os, base64, io, re
from datetime import datetime, date
import numpy as np
from PIL import Image
from flask import Flask, jsonify, abort

app = Flask(__name__)

# ─── Path to DICOM files ──────────────────────────────────────────────────────
DICOM_DIR = os.path.join(os.path.dirname(__file__), "dicom_data", "untitled folder")


# ─── DICOM Reader (no external pydicom dependency) ───────────────────────────

def read_dicom(filepath):
    """
    Parse a DICOM file manually using the DICOM binary format spec.
    Returns (tags_dict, pixel_data_bytes).
    Handles both Explicit and Implicit VR transfer syntaxes.
    """
    with open(filepath, "rb") as f:
        data = f.read()

    # Validate DICOM magic bytes at offset 128
    if data[128:132] != b'DICM':
        return None, None

    pos = 132
    tags = {}
    pixel_data = None

    # Tags we want to extract
    target_tags = {
        (0x0010, 0x0020): 'PatientID',
        (0x0010, 0x0030): 'PatientBirthDate',
        (0x0010, 0x1010): 'PatientAge',
        (0x0008, 0x0020): 'StudyDate',
        (0x0010, 0x0040): 'PatientSex',
        (0x0028, 0x0010): 'Rows',
        (0x0028, 0x0011): 'Columns',
        (0x0028, 0x0100): 'BitsAllocated',
        (0x0028, 0x0103): 'PixelRepresentation',
        (0x7FE0, 0x0010): 'PixelData',
    }

    while pos < len(data) - 8:
        try:
            group = struct.unpack_from('<H', data, pos)[0]
            elem  = struct.unpack_from('<H', data, pos + 2)[0]
            pos += 4

            # Detect Explicit VR: next 2 bytes are uppercase ASCII letters
            vr = data[pos:pos + 2]
            if len(vr) == 2 and vr.isalpha() and vr == vr.upper():
                pos += 2
                # Long-form VR: 2 reserved bytes + 4-byte length
                if vr in (b'OB', b'OW', b'SQ', b'UN', b'UC', b'UR', b'UT'):
                    pos += 2  # skip reserved
                    length = struct.unpack_from('<I', data, pos)[0]
                    pos += 4
                else:
                    # Short-form VR: 2-byte length
                    length = struct.unpack_from('<H', data, pos)[0]
                    pos += 2
            else:
                # Implicit VR: 4-byte length
                length = struct.unpack_from('<I', data, pos)[0]
                pos += 4
                vr = b'UN'

            # Undefined length (sequences) – skip
            if length == 0xFFFFFFFF:
                continue

            value = data[pos:pos + length]
            pos += length

            key = (group, elem)
            if key in target_tags:
                name = target_tags[key]
                if name == 'PixelData':
                    pixel_data = value
                elif name in ('Rows', 'Columns', 'BitsAllocated', 'PixelRepresentation'):
                    tags[name] = struct.unpack_from('<H', value)[0] if len(value) >= 2 else 0
                else:
                    tags[name] = value.decode('latin-1').strip('\x00 ')
        except Exception:
            break

    return tags, pixel_data


def dicom_to_png_b64(filepath):
    """Convert DICOM pixel data to a base64-encoded PNG string."""
    tags, pixel_data = read_dicom(filepath)
    if tags is None or pixel_data is None:
        return None

    rows = tags.get('Rows', 512)
    cols = tags.get('Columns', 512)
    bits = tags.get('BitsAllocated', 16)
    signed = tags.get('PixelRepresentation', 0)

    dtype = np.int16 if (bits == 16 and signed) else (np.uint16 if bits == 16 else np.uint8)
    expected_bytes = rows * cols * (bits // 8)
    arr = np.frombuffer(pixel_data[:expected_bytes], dtype=dtype).reshape(rows, cols)

    # Normalise to 0–255 for display
    arr = arr.astype(np.float32)
    mn, mx = arr.min(), arr.max()
    if mx > mn:
        arr = (arr - mn) / (mx - mn) * 255
    img = Image.fromarray(arr.astype(np.uint8)).convert('L').resize((200, 200))

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


# ─── Helper: format age ───────────────────────────────────────────────────────

def format_age(raw_age: str) -> str:
    """
    Convert DICOM age string (e.g. '060Y') to human-readable '60 years'.
    Also handles months (M) and days (D).
    """
    if not raw_age:
        return "Unknown"
    m = re.match(r'^(\d+)([YMWD])$', raw_age.strip())
    if not m:
        return raw_age
    num, unit = int(m.group(1)), m.group(2)
    units = {'Y': 'year', 'M': 'month', 'W': 'week', 'D': 'day'}
    label = units.get(unit, unit)
    return f"{num} {label}{'s' if num != 1 else ''}"


def format_date(raw_date: str) -> str:
    """Convert DICOM date string YYYYMMDD to human-readable format."""
    if not raw_date or len(raw_date) < 8:
        return raw_date or "Unknown"
    try:
        return datetime.strptime(raw_date[:8], "%Y%m%d").strftime("%d %B %Y")
    except ValueError:
        return raw_date


# ─── Load all DICOM files at startup ─────────────────────────────────────────

def load_all_dicom():
    """Read metadata from all DICOM files in DICOM_DIR."""
    records = []
    for fname in sorted(os.listdir(DICOM_DIR)):
        if not fname.endswith('.dcm'):
            continue
        fpath = os.path.join(DICOM_DIR, fname)
        tags, _ = read_dicom(fpath)
        if tags is None:
            continue
        records.append({
            "filename":   fname,
            "filepath":   fpath,
            "PatientID":  tags.get('PatientID', 'Unknown'),
            "StudyDate":  tags.get('StudyDate', ''),
            "PatientAge": tags.get('PatientAge', ''),
            "PatientSex": tags.get('PatientSex', ''),
            # Human-readable versions
            "DateDisplay": format_date(tags.get('StudyDate', '')),
            "AgeDisplay":  format_age(tags.get('PatientAge', '')),
        })
    return records


RECORDS = load_all_dicom()  # cached at startup


# ─── Shared HTML template helpers ────────────────────────────────────────────

HTML_STYLE = """
<style>
  body { font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:20px; }
  h1 { color:#333; }
  .grid { display:flex; flex-wrap:wrap; gap:16px; }
  .card { background:#fff; border-radius:8px; padding:12px; box-shadow:0 2px 6px rgba(0,0,0,.15);
          width:220px; text-align:center; }
  .card img { width:200px; height:200px; object-fit:contain; border-radius:4px; }
  .card p { margin:4px 0; font-size:13px; color:#555; }
  .card .pid { font-weight:bold; color:#333; }
  .filter-bar { margin-bottom:20px; }
  .filter-bar input { padding:8px 12px; font-size:14px; border:1px solid #ccc;
                      border-radius:4px; width:300px; }
  nav a { margin-right:12px; text-decoration:none; color:#0077cc; font-weight:bold; }
</style>
<script>
function filterCards(val) {
  document.querySelectorAll('.card').forEach(c => {
    c.style.display = c.dataset.pid.toLowerCase().includes(val.toLowerCase()) ? '' : 'none';
  });
}
</script>
"""


def render_card(rec):
    """Render a single image card with metadata."""
    b64 = dicom_to_png_b64(rec['filepath'])
    img_tag = (f'<img src="data:image/png;base64,{b64}" alt="CT scan">'
               if b64 else '<div style="width:200px;height:200px;background:#ddd;">No image</div>')
    return f"""
    <div class="card" data-pid="{rec['PatientID']}">
      <a href="/patient/{rec['PatientID']}">{img_tag}</a>
      <p class="pid">ID: {rec['PatientID']}</p>
      <p>📅 {rec['DateDisplay']}</p>
      <p>🧓 {rec['AgeDisplay']}</p>
    </div>"""


# ─── Question 1a: Grid view (4 per row) ──────────────────────────────────────

@app.route('/')
def index():
    """
    Q1a: Grid of all DICOM images, 4 per row, with Patient ID, Date, Age.
    Also includes a live search bar (Q1b filter logic reused here).
    """
    cards_html = "\n".join(render_card(r) for r in RECORDS)

    # Build table rows of 4 cards each
    rows_html = ""
    for i in range(0, len(RECORDS), 4):
        row_cards = RECORDS[i:i+4]
        cells = "".join(
            f"<td style='padding:8px;vertical-align:top;'>{render_card(r)}</td>"
            for r in row_cards
        )
        rows_html += f"<tr>{cells}</tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>DICOM Viewer</title>{HTML_STYLE}</head>
<body>
  <nav><a href="/">All Images</a></nav>
  <h1>🏥 DICOM Image Overview ({len(RECORDS)} scans)</h1>
  <div class="filter-bar">
    <input type="text" placeholder="Filter by Patient ID..." oninput="filterCards(this.value)">
  </div>
  <table style="border-collapse:collapse;">
    {rows_html}
  </table>
</body>
</html>"""
    return html


# ─── Question 1b: Patient-specific view ──────────────────────────────────────

@app.route('/patient/<patient_id>')
def patient_view(patient_id):
    """
    Q1b: Filterable route showing all images for a specific patient.
    """
    patient_records = [r for r in RECORDS if r['PatientID'] == patient_id]

    if not patient_records:
        abort(404, description=f"No records found for Patient ID: {patient_id}")

    rows_html = ""
    for i in range(0, len(patient_records), 4):
        row_cards = patient_records[i:i+4]
        cells = "".join(
            f"<td style='padding:8px;vertical-align:top;'>{render_card(r)}</td>"
            for r in row_cards
        )
        rows_html += f"<tr>{cells}</tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Patient {patient_id}</title>{HTML_STYLE}</head>
<body>
  <nav><a href="/">← Back to All Images</a></nav>
  <h1>Patient: {patient_id} ({len(patient_records)} scan(s))</h1>
  <table style="border-collapse:collapse;">
    {rows_html}
  </table>
</body>
</html>"""
    return html


# ─── Question 2a: JSON API – all metadata ────────────────────────────────────

@app.route('/api')
def api_all():
    """
    Q2a: JSON endpoint with all DICOM metadata.
    Includes Patient ID, Date, Age, and link to the image file on disk.
    Note: Data is NOT yet FHIR-interoperable (see Q2b for that discussion).
    """
    result = []
    for r in RECORDS:
        result.append({
            "patient_id":   r['PatientID'],
            "study_date":   r['StudyDate'],
            "date_display": r['DateDisplay'],
            "patient_age":  r['PatientAge'],
            "age_display":  r['AgeDisplay'],
            "patient_sex":  r['PatientSex'],
            "filename":     r['filename'],
            "image_path":   r['filepath'],       # absolute path on disk
        })
    return jsonify(result)


# ─── Question 2c: JSON API – per patient ─────────────────────────────────────

@app.route('/api/patient/<patient_id>')
def api_patient(patient_id):
    """
    Q2c: JSON endpoint filtered by patient_id.
    """
    patient_records = [
        {
            "patient_id":   r['PatientID'],
            "study_date":   r['StudyDate'],
            "date_display": r['DateDisplay'],
            "patient_age":  r['PatientAge'],
            "age_display":  r['AgeDisplay'],
            "patient_sex":  r['PatientSex'],
            "filename":     r['filename'],
            "image_path":   r['filepath'],
        }
        for r in RECORDS if r['PatientID'] == patient_id
    ]

    if not patient_records:
        return jsonify({"error": f"No records for patient {patient_id}"}), 404

    return jsonify(patient_records)


# ─── Question 3: Filename vs Metadata Mismatch Detection ─────────────────────

def parse_filename(fname):
    """
    Extract ID number and AGE embedded in the filename.
    Pattern: ID_XXXX_AGE_YYYY_CONTRAST_Z_CT.dcm
    """
    m = re.match(r'ID_(\d{4})_AGE_(\d{4})_CONTRAST_(\d)_CT\.dcm', fname)
    if not m:
        return None
    return {
        "id_num":    m.group(1),
        "age_fname": int(m.group(2)),
        "contrast":  int(m.group(3)),
    }


def check_mismatches():
    """
    Q3b: Compare filename-embedded age vs DICOM metadata age.
    Returns list of mismatched files with details.

    Cues used (Q3a):
    - Filename encodes: sequential ID number, patient age, contrast flag (0/1)
    - DICOM metadata has: PatientID (TCGA format), PatientAge (e.g. '060Y'), StudyDate
    - The age in the filename (AGE_XXXX) should match the metadata PatientAge numeric value
    """
    mismatches = []
    for r in RECORDS:
        fname_info = parse_filename(r['filename'])
        if not fname_info:
            continue

        # Extract numeric age from DICOM metadata (e.g. '060Y' → 60)
        meta_age_raw = r['PatientAge']
        m = re.match(r'^(\d+)Y$', meta_age_raw)
        if not m:
            continue
        meta_age = int(m.group(1))
        fname_age = fname_info['age_fname']

        if meta_age != fname_age:
            mismatches.append({
                "filename":          r['filename'],
                "patient_id":        r['PatientID'],
                "age_in_filename":   fname_age,
                "age_in_metadata":   meta_age,
                "correct_filename":  r['filename'].replace(
                    f"AGE_{fname_age:04d}", f"AGE_{meta_age:04d}"
                ),
            })
    return mismatches


def fix_filenames(dry_run=True):
    """
    Q3c: Rename mismatched files to reflect correct metadata age.
    Set dry_run=False to actually rename files.
    Returns list of rename operations performed (or planned).
    """
    mismatches = check_mismatches()
    operations = []
    for m in mismatches:
        old_path = os.path.join(DICOM_DIR, m['filename'])
        new_path = os.path.join(DICOM_DIR, m['correct_filename'])
        if not dry_run:
            os.rename(old_path, new_path)
        operations.append({
            "old_name": m['filename'],
            "new_name": m['correct_filename'],
            "renamed":  not dry_run,
        })
    return operations


# ─── Q3 diagnostic route ──────────────────────────────────────────────────────

@app.route('/api/mismatches')
def api_mismatches():
    """
    Q3b/3c: JSON endpoint listing all filename↔metadata mismatches.
    """
    mismatches = check_mismatches()
    return jsonify({
        "total_files":      len(RECORDS),
        "mismatch_count":   len(mismatches),
        "mismatches":       mismatches,
        "rename_plan":      fix_filenames(dry_run=True),
    })


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Print Q3 results to console at startup
    print("\n=== Q3: Filename vs Metadata Mismatch Report ===")
    mismatches = check_mismatches()
    print(f"Total files: {len(RECORDS)}, Mismatches found: {len(mismatches)}")
    for m in mismatches:
        print(f"  ✗ {m['filename']}")
        print(f"      Age in filename: {m['age_in_filename']}  |  Age in metadata: {m['age_in_metadata']}")
        print(f"      Correct name: {m['correct_filename']}")

    print("\nTo fix filenames, call: fix_filenames(dry_run=False)")
    print("\nStarting Flask server on http://localhost:5000 ...\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
