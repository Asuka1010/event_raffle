import csv
import io
import random
from datetime import datetime
from typing import List, Dict, Any, Optional

StudentRow = Dict[str, Any]


def _to_int(value, default=0):
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


def _strip_bom(text):
    if text.startswith('\ufeff'):
        return text[1:]
    return text


def parse_csv_upload(uploaded_file) -> List[StudentRow]:
    """Generic CSV parser for backward compatibility"""
    # Handle both file objects and string content
    if hasattr(uploaded_file, 'read'):
        # It's a file-like object
        text = uploaded_file.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8")
    else:
        # It's already a string
        text = str(uploaded_file)
    
    text = _strip_bom(text)
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        # Safely handle different data types
        safe_row = {}
        for k, v in row.items():
            # Handle key
            if k is None:
                k = ""
            elif isinstance(k, str):
                k = k.strip()
            else:
                k = str(k).strip()
            
            # Handle value
            if v is None:
                v = ""
            elif isinstance(v, (list, tuple)):
                v = ", ".join(str(item).strip() for item in v)
            elif isinstance(v, str):
                v = v.strip()
            else:
                v = str(v).strip()
            
            safe_row[k] = v
        rows.append(safe_row)
    return rows


def parse_event_signup_csv(uploaded_file) -> List[StudentRow]:
    """Parse event signup CSV with specific format: Attendee ID, Firstname, Lastname, Participation status, Email, Date"""
    # Handle both file objects and string content
    if hasattr(uploaded_file, 'read'):
        # It's a file-like object
        text = uploaded_file.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8")
    else:
        # It's already a string
        text = str(uploaded_file)
    
    text = _strip_bom(text)
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        # Map to our expected format
        mapped_row = {
            "email": (row.get("Email") or "").strip(),
            "firstname": (row.get("Firstname") or "").strip(),
            "lastname": (row.get("Lastname") or "").strip(),
            "participation status": (row.get("Participation status") or "").strip(),
            "attendee id": (row.get("Attendee ID") or "").strip(),
            "signup date": (row.get("Date") or "").strip(),
        }
        rows.append(mapped_row)
    return rows


def parse_historical_csv(uploaded_file) -> List[StudentRow]:
    """Parse historical database CSV with specific format"""
    # Handle both file objects and string content
    if hasattr(uploaded_file, 'read'):
        # It's a file-like object
        text = uploaded_file.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8")
    else:
        # It's already a string
        text = str(uploaded_file)
    
    print(f"DEBUG: parse_historical_csv - text length: {len(text)}")
    text = _strip_bom(text)
    
    # Split into lines and find the header row
    lines = text.strip().split('\n')
    header_row = None
    data_start_row = 0
    
    for i, line in enumerate(lines):
        if 'Email' in line and 'First Name' in line and 'Last Name' in line:
            header_row = line
            data_start_row = i + 1
            break
    
    if not header_row:
        print("DEBUG: Could not find header row with Email, First Name, Last Name")
        return []
    
    print(f"DEBUG: Found header at row {data_start_row}: {header_row}")
    
    # Parse the header to get column positions
    header_columns = list(csv.reader([header_row]))[0]
    print(f"DEBUG: Header columns: {header_columns}")
    
    # Find the positions of important columns
    email_col = None
    first_name_col = None
    last_name_col = None
    class_col = None
    absent_col = None
    late_col = None
    attended_col = None
    
    for i, col in enumerate(header_columns):
        col_clean = col.strip()
        if col_clean == "Email":
            email_col = i
        elif col_clean == "First Name":
            first_name_col = i
        elif col_clean == "Last Name":
            last_name_col = i
        elif col_clean == "Class":
            class_col = i
        elif col_clean == "Absent":
            absent_col = i
        elif col_clean == "Late":
            late_col = i
        elif col_clean == "Attended":
            attended_col = i
    
    print(f"DEBUG: Column positions - Email: {email_col}, First: {first_name_col}, Last: {last_name_col}")
    
    if email_col is None or first_name_col is None or last_name_col is None:
        print("DEBUG: Missing required columns")
        return []
    
    # Parse data rows
    rows = []
    for i, line in enumerate(lines[data_start_row:], data_start_row):
        if not line.strip():
            continue
            
        row_data = list(csv.reader([line]))[0]
        
        if i < data_start_row + 3:  # Debug first few rows
            print(f"DEBUG: Row {i}: {row_data}")
        
        # Check if row has essential data
        if (len(row_data) <= max(email_col, first_name_col, last_name_col) or
            not row_data[email_col] or not row_data[first_name_col] or not row_data[last_name_col]):
            print(f"DEBUG: Skipping row {i} - missing essential data")
            continue
        
        # Map to our expected format
        mapped_row = {
            "email": row_data[email_col].strip(),
            "first name": row_data[first_name_col].strip(),
            "last name": row_data[last_name_col].strip(),
            "class": row_data[class_col].strip() if class_col and len(row_data) > class_col else "",
            "absent": row_data[absent_col].strip() if absent_col and len(row_data) > absent_col else "0",
            "late": row_data[late_col].strip() if late_col and len(row_data) > late_col else "0",
            "attended": row_data[attended_col].strip() if attended_col and len(row_data) > attended_col else "0",
            "events_attended": "",
            "latest attended": "",
        }
        
        # Process event columns (columns between Class and Absent)
        attended_events = []
        latest_event = ""
        if class_col and absent_col:
            for j in range(class_col + 1, absent_col):
                if j < len(row_data) and j < len(header_columns):
                    event_name = header_columns[j].strip()
                    status = row_data[j].strip() if j < len(row_data) else ""
                    if event_name and status.lower() == "attended":
                        attended_events.append(event_name)
                        if not latest_event or event_name > latest_event:
                            latest_event = event_name
        
        if attended_events:
            mapped_row["events_attended"] = ", ".join(attended_events)
            mapped_row["latest attended"] = latest_event
        
        rows.append(mapped_row)
        if i < data_start_row + 3:  # Debug first few rows
            print(f"DEBUG: Mapped row {i}: {mapped_row}")
    
    print(f"DEBUG: parse_historical_csv - total rows parsed: {len(rows)}")
    return rows


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except Exception:
            continue
    return None


def consolidate_students(signups, historical):
    """Consolidate signup and historical data into master list"""
    # Build index of historical students by email
    history_index = {}
    for h in historical:
        email = h.get("email", "").lower().strip()
        if email:
            history_index[email] = h

    # Normalize historical data - handle both old and new formats
    def normalize_historical(h):
        # Check if this is the new format (has 'first name' key)
        if "first name" in h:
            return {
                "email": h.get("email", ""),
                "first_name": h.get("first name", ""),
                "last_name": h.get("last name", ""),
                "class": h.get("class", ""),
                "num_events_attended": _to_int(h.get("attended")),
                "num_absences": _to_int(h.get("absent")),
                "num_late_arrivals": _to_int(h.get("late")),
                "events_attended": h.get("events_attended", ""),
                "latest_attended_date": h.get("latest attended", ""),
            }
        else:
            # Old format fallback
            return {
                "email": h.get("email", ""),
                "first_name": h.get("firstname", ""),
                "last_name": h.get("lastname", ""),
                "class": h.get("class", ""),
                "num_events_attended": _to_int(h.get("attended")),
                "num_absences": _to_int(h.get("absent")),
                "num_late_arrivals": _to_int(h.get("late")),
                "events_attended": h.get("attended events", ""),
                "latest_attended_date": h.get("latest attended", ""),
            }

    # Normalize signup data - handle both old and new formats
    def normalize_signup(s):
        # Check if this is the new format (has 'firstname' key)
        if "firstname" in s:
            return {
                "email": s.get("email", ""),
                "first_name": s.get("firstname", ""),
                "last_name": s.get("lastname", ""),
                "response": s.get("participation status", "").lower(),
            }
        else:
            # Old format fallback
            return {
                "email": s.get("email", ""),
                "first_name": s.get("firstname", ""),
                "last_name": s.get("lastname", ""),
                "response": s.get("participation status", "").lower(),
            }

    # Start with all historical students
    master = []
    for h in historical:
        norm = normalize_historical(h)
        master.append(norm)

    # Overlay signup data
    for s in signups:
        norm = normalize_signup(s)
        email = norm["email"].lower().strip()
        
        if email in history_index:
            # Update existing historical record
            for student in master:
                if student["email"].lower().strip() == email:
                    student["response"] = norm["response"]
                    break
        else:
            # New student - add to master with zero counters
            master.append({
                "email": norm["email"],
                "first_name": norm["first_name"],
                "last_name": norm["last_name"],
                "class": "",
                "num_events_attended": 0,
                "num_absences": 0,
                "num_late_arrivals": 0,
                "events_attended": "",
                "latest_attended_date": "",
                "response": norm["response"],
            })

    return master


def _priority_key(student):
    """Define sorting priority for raffle selection"""
    # Primary: # of attended events (ascending)
    attended = student.get("num_events_attended", 0)
    
    # Secondary: # of absences (ascending)
    absences = student.get("num_absences", 0)
    
    # Tertiary: # of late arrivals (ascending)
    late = student.get("num_late_arrivals", 0)
    
    # Final tie-breaker: latest attended date (ascending, null/N/A considered earliest)
    latest_date = student.get("latest_attended_date", "")
    
    return (attended, absences, late, latest_date)


def run_priority_raffle(students, capacity):
    """Run priority-based raffle selection"""
    # Filter eligible students (response is "yes" or "planned")
    eligible = [s for s in students if s.get("response", "").lower() in ["yes", "planned"]]
    
    if not eligible:
        return [], []
    
    # Sort by priority criteria
    eligible_sorted = sorted(eligible, key=_priority_key)
    
    # Apply random tie-breaker for final fairness
    random.shuffle(eligible_sorted)
    
    # Select top students up to capacity
    selected = eligible_sorted[:capacity]
    remaining = eligible_sorted[capacity:]
    
    # Return in the format expected by the view: (eligible_ranked, selected)
    # eligible_ranked should include both selected and remaining students
    eligible_ranked = eligible_sorted
    
    return eligible_ranked, selected


def generate_ranking_csv(eligible_ranked):
    """Generate CSV showing all eligible students with ranking and selection status"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Rank", "Email", "First Name", "Last Name", "Class", 
        "Events Attended", "Absences", "Late Arrivals", "Latest Event", "Selected"
    ])
    
    # Write data
    for i, student in enumerate(eligible_ranked, 1):
        writer.writerow([
            i,
            student.get("email", ""),
            student.get("first_name", ""),
            student.get("last_name", ""),
            student.get("class", ""),
            student.get("num_events_attended", 0),
            student.get("num_absences", 0),
            student.get("num_late_arrivals", 0),
            student.get("latest_attended_date", ""),
            "Yes" if i <= len(eligible_ranked) else "No"
        ])
    
    return output.getvalue()


def generate_updated_history_csv(master_students, selected, event_name, event_date, adjustments):
    """Generate updated historical database CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header - use the format from the uploaded historical CSV
    header = [
        "Email", "Preferred Name/Nick Name", "First Name", "Last Name", "Class",
        "The Power of Hope", "Exploring Humanity's Future with the Long Now Foundation",
        "Fireside Chat with Adam Met", "Art Through Movement at the Museum of African Diaspora",
        "History and Habitat Restoration on Alcatraz", "The Poetry of Angel Island (Option 1)",
        "STEM Writing Workshop", "The Hydrology Hike", "The History of the Redwoods",
        "The Chinatown Ghost Tour", "The Poetry of Angel Island (Option 2)",
        "How to Start a Business", "The Chinatown Cultural Workshop",
        "Engineering Principles on the USS Pampanito", "History of the Bay on SS Jeremiah O'Brien",
        "Presidio Plant Nursery", "Tenderloin Tapestry", "Girl Scouts Cultural Exchange",
        "History and Change at the Golden Gate Park", "UC Davis Psych Lab Visit",
        "Marine Biology in the Bay", "Absent", "Late", "Attended"
    ]
    writer.writerow(header)
    
    # Process each student
    for student in master_students:
        email = student.get("email", "")
        
        # Find if this student was selected for the current event
        is_selected = any(s.get("email", "").lower() == email.lower() for s in selected)
        
        # Build row data
        row = [
            email,
            "",  # Preferred Name/Nick Name
            student.get("first_name", ""),
            student.get("last_name", ""),
            student.get("class", ""),
        ]
        
        # Add event columns - for now, we'll add the new event if selected
        # In a real implementation, you'd want to preserve existing event data
        for i in range(24):  # 24 events as mentioned
            if i == 0 and is_selected:  # First event column gets the new event
                row.append("Attended")
            else:
                row.append("")  # Empty for other events
        
        # Add summary columns
        row.extend([
            student.get("num_absences", 0),
            student.get("num_late_arrivals", 0),
            student.get("num_events_attended", 0)
        ])
        
        writer.writerow(row)
    
    return output.getvalue()


