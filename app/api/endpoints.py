from flask import Flask, jsonify, request, send_from_directory, render_template, make_response
import uuid
import threading
import os
import time
import psycopg2
import csv
from datetime import datetime, timedelta, time as time_obj
import pytz
from typing import Dict, List, Tuple, Optional

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) 
PROJECT_ROOT = os.path.abspath(os.path.join(APP_ROOT, '..'))
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

# creates the reports directory if it does not exist
os.makedirs(REPORTS_DIR, exist_ok=True)

# template contains the html file and static contains the javascript and css files.
app = Flask(__name__,
            template_folder=os.path.join(APP_ROOT, 'templates'),
            static_folder=os.path.join(APP_ROOT, 'static'))

# Connection to postgresql. The database I have created is named 'loop'
def get_db_params() -> Dict[str, str]:
    return {
        'dbname': os.environ.get('POSTGRES_DB', 'loop'),
        'user': os.environ.get('POSTGRES_USER', 'postgres'),
        'password': os.environ.get('POSTGRES_PASSWORD', 'password'),
        'host': os.environ.get('POSTGRES_HOST', 'localhost'),
        'port': os.environ.get('POSTGRES_PORT', '5432')
    }

# We use the pytz library to get the time based on utc timezone
def parse_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not(timestamp):
        return None
    if isinstance(timestamp, datetime):
        return timestamp.astimezone(pytz.utc) if timestamp.tzinfo else pytz.utc.localize(timestamp)
    try:
        if timestamp.endswith(' UTC'):
            timestamp = timestamp[:-4]
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
        return pytz.utc.localize(dt)
    except ValueError:
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.astimezone(pytz.utc) if dt.tzinfo else pytz.utc.localize(dt)
        except ValueError:
            print(f"Failed to parse timestamp: {timestamp}. Using current UTC time.")
            return datetime.now(pytz.utc)

def generate_report_logic(report_id: str, conn, store_ids: List[str]) -> None:
    cursor = None
    try:
        cursor = conn.cursor()
        report_output_list = []
        for store_id in store_ids:
            print(f"Generating report for store_id: {store_id}")

            cursor.execute("SELECT store_id FROM store_status WHERE store_id = %s", (store_id,))
            if not cursor.fetchone():
                print(f"Store {store_id} not found in store_status.")
                continue

            # Use the max timestamp as the current timestamp
            cursor.execute("SELECT MAX(timestamp_utc::timestamp) FROM store_status WHERE store_id = %s;", (store_id,))
            max_timestamp_result = cursor.fetchone()[0]
            max_utc_from_data = parse_timestamp(str(max_timestamp_result)) or datetime.now(pytz.utc)

            cursor.execute("SELECT timezone_str FROM timezones WHERE store_id = %s", (store_id,))
            tz_result = cursor.fetchone()
            # Set default timezones as America/Chicago
            tz_str = tz_result[0] if tz_result else 'America/Chicago'
            try:
                pytz_timezone = pytz.timezone(tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                print(f"Unknown timezone '{tz_str}' for store {store_id}. Defaulting to America/Chicago.")
                pytz_timezone = pytz.timezone('America/Chicago')

            cursor.execute(
                'SELECT "dayOfWeek", start_time_local, end_time_local FROM menu_hours WHERE store_id = %s',
                (store_id,)
            )

            # Create a dictionary to store the business_hours every day
            store_business_hours: Dict[int, Tuple[time_obj, time_obj]] = {}
            for day_of_week, start_local, end_local in cursor.fetchall():
                # datetime.time doesn't read the time properly if the store closes at midnight so we address this edge case
                end_local = time_obj(23, 59, 59, 999999) if end_local == time_obj(0, 0) else end_local
                store_business_hours[day_of_week] = (start_local, end_local)

            # The target time in this case is the max timestamp
            target_ref_time_utc = max_utc_from_data
            # Time taken 7 days before reference time
            one_week_ago_utc = target_ref_time_utc - timedelta(days=7)
            last_hour_start_utc = target_ref_time_utc - timedelta(hours=1)

            print(f"Processing store {store_id}")

            # output parameters
            total_uptime_last_hour_s = 0
            total_active_time_in_business_last_hour_s = 0
            total_uptime_last_day_s = 0
            total_active_time_in_business_last_day_s = 0
            total_uptime_last_week_s = 0
            total_active_time_in_business_last_week_s = 0

            # Retrieves the status of the store that is present within the last 7 days
            cursor.execute(
                "SELECT timestamp_utc, status FROM store_status WHERE store_id = %s AND timestamp_utc::timestamp >= %s ORDER BY timestamp_utc::timestamp",
                (store_id, one_week_ago_utc)
            )
            store_polls = [(parse_timestamp(row[0]), row[1]) for row in cursor.fetchall()]

            # Calculate uptime for the last hour
            # Converts time to local timezone
            last_hour_local_dt = last_hour_start_utc.astimezone(pytz_timezone)
            target_local_dt = target_ref_time_utc.astimezone(pytz_timezone)
            local_date = last_hour_local_dt.date()
            day_of_week_local = last_hour_local_dt.weekday()

            biz_hours = store_business_hours.get(day_of_week_local, (time_obj(0, 0), time_obj(23, 59, 59, 999999)))
            start_time_local, end_time_local = biz_hours

            business_periods = []
            naive_start_local = datetime.combine(local_date, start_time_local)
            naive_end_local = datetime.combine(local_date, end_time_local)
            if end_time_local <= start_time_local:
                naive_end_local += timedelta(days=1)

            try:
                start_utc = pytz_timezone.localize(naive_start_local, is_dst=None).astimezone(pytz.utc)
                end_utc = pytz_timezone.localize(naive_end_local, is_dst=None).astimezone(pytz.utc)
                business_periods.append((start_utc, end_utc))
            except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e:
                print(f"DST issue for store {store_id} on {local_date}: {e}. Using fallback.")
                try:
                    start_utc = pytz_timezone.localize(naive_start_local, is_dst=False).astimezone(pytz.utc)
                    end_utc = pytz_timezone.localize(naive_end_local, is_dst=False).astimezone(pytz.utc)
                    business_periods.append((start_utc, end_utc))
                except:
                    start_utc = pytz_timezone.localize(naive_start_local + timedelta(hours=1), is_dst=None).astimezone(pytz.utc)
                    end_utc = pytz_timezone.localize(naive_end_local + timedelta(hours=1), is_dst=None).astimezone(pytz.utc)
                    business_periods.append((start_utc, end_utc))

            # Set the end_time to next day in case this situation takes place (edge case)
            if end_time_local <= start_time_local:
                prev_local_date = local_date - timedelta(days=1)
                prev_day_of_week = prev_local_date.weekday()
                prev_biz_hours = store_business_hours.get(prev_day_of_week, (time_obj(0, 0), time_obj(23, 59, 59, 999999)))
                prev_start_local, prev_end_local = prev_biz_hours
                if prev_end_local <= prev_start_local:
                    naive_prev_end = datetime.combine(local_date, prev_end_local)
                    try:
                        prev_end_utc = pytz_timezone.localize(naive_prev_end, is_dst=None).astimezone(pytz.utc)
                        business_periods.append((last_hour_start_utc, prev_end_utc))
                    except:
                        prev_end_utc = pytz_timezone.localize(naive_prev_end + timedelta(hours=1), is_dst=None).astimezone(pytz.utc)
                        business_periods.append((last_hour_start_utc, prev_end_utc))

            # For each poll we calculate the duration of the poll to find the total uptime
            for business_opens_utc, business_closes_utc in business_periods:
                if business_closes_utc < last_hour_start_utc or business_opens_utc > target_ref_time_utc:
                    continue
                store_hour_polls = [
                    (ts, status) for ts, status in store_polls
                    if last_hour_start_utc - timedelta(hours=1) <= ts <= target_ref_time_utc + timedelta(hours=1)
                ]
                events = [(last_hour_start_utc, 'SYSTEM_OPEN')] + store_hour_polls + [(target_ref_time_utc, 'SYSTEM_CLOSE')]
                events.sort(key=lambda x: x[0])

                current_status = 'inactive'
                last_poll_before = next((p for p in store_polls if p[0] < last_hour_start_utc), None)
                if last_poll_before:
                    current_status = last_poll_before[1]

                prev_event_time = last_hour_start_utc
                for event_time, event_type in events:
                    actual_event_time = max(last_hour_start_utc, min(event_time, target_ref_time_utc))
                    actual_event_time = max(actual_event_time, business_opens_utc)
                    actual_event_time = min(actual_event_time, business_closes_utc)
                    if actual_event_time > prev_event_time:
                        duration_s = (actual_event_time - prev_event_time).total_seconds()
                        if current_status == 'active':
                            total_uptime_last_hour_s += duration_s
                        total_active_time_in_business_last_hour_s += duration_s
                    if event_type not in ['SYSTEM_OPEN', 'SYSTEM_CLOSE']:
                        current_status = event_type
                    elif event_type == 'SYSTEM_CLOSE':
                        current_status = 'inactive'
                    prev_event_time = actual_event_time

            # Calculate uptime for the last day and the last week
            current_utc_date = one_week_ago_utc.date()
            while current_utc_date <= target_ref_time_utc.date():
                iter_utc_dt = pytz.utc.localize(datetime.combine(current_utc_date, time_obj.min))
                iter_local_dt = iter_utc_dt.astimezone(pytz_timezone)
                local_date = iter_local_dt.date()
                day_of_week_local = iter_local_dt.weekday()

                biz_hours = store_business_hours.get(day_of_week_local, (time_obj(0, 0), time_obj(23, 59, 59, 999999)))
                start_time_local, end_time_local = biz_hours

                business_periods = []
                naive_start_local = datetime.combine(local_date, start_time_local)
                naive_end_local = datetime.combine(local_date, end_time_local)
                if end_time_local <= start_time_local:
                    naive_end_local += timedelta(days=1)

                try:
                    start_utc = pytz_timezone.localize(naive_start_local, is_dst=None).astimezone(pytz.utc)
                    end_utc = pytz_timezone.localize(naive_end_local, is_dst=None).astimezone(pytz.utc)
                    business_periods.append((start_utc, end_utc))
                except (pytz.exceptions.AmbiguousTimeError, pytz.exceptions.NonExistentTimeError) as e:
                    print(f"DST issue for store {store_id} on {local_date}: {e}. Using fallback.")
                    try:
                        start_utc = pytz_timezone.localize(naive_start_local, is_dst=False).astimezone(pytz.utc)
                        end_utc = pytz_timezone.localize(naive_end_local, is_dst=False).astimezone(pytz.utc)
                        business_periods.append((start_utc, end_utc))
                    except:
                        start_utc = pytz_timezone.localize(naive_start_local + timedelta(hours=1), is_dst=None).astimezone(pytz.utc)
                        end_utc = pytz_timezone.localize(naive_end_local + timedelta(hours=1), is_dst=None).astimezone(pytz.utc)
                        business_periods.append((start_utc, end_utc))

                if end_time_local <= start_time_local:
                    prev_local_date = local_date - timedelta(days=1)
                    prev_day_of_week = prev_local_date.weekday()
                    prev_biz_hours = store_business_hours.get(prev_day_of_week, (time_obj(0, 0), time_obj(23, 59, 59, 999999)))
                    prev_start_local, prev_end_local = prev_biz_hours
                    if prev_end_local <= prev_start_local:
                        naive_prev_end = datetime.combine(local_date, prev_end_local)
                        try:
                            prev_end_utc = pytz_timezone.localize(naive_prev_end, is_dst=None).astimezone(pytz.utc)
                            business_periods.append((iter_utc_dt, prev_end_utc))
                        except:
                            prev_end_utc = pytz_timezone.localize(naive_prev_end + timedelta(hours=1), is_dst=None).astimezone(pytz.utc)
                            business_periods.append((iter_utc_dt, prev_end_utc))

                daily_uptime_s = 0
                total_business_seconds_for_day = 0
                for business_opens_utc, business_closes_utc in business_periods:
                    store_day_polls = [
                        (ts, status) for ts, status in store_polls
                        if business_opens_utc - timedelta(hours=1) <= ts <= business_closes_utc + timedelta(hours=1)
                    ]

                    events = [(business_opens_utc, 'SYSTEM_OPEN')] + store_day_polls + [(business_closes_utc, 'SYSTEM_CLOSE')]
                    events.sort(key=lambda x: x[0])

                    current_status = 'inactive'
                    last_poll_before = next((p for p in store_polls if p[0] < business_opens_utc), None)
                    if last_poll_before:
                        current_status = last_poll_before[1]

                    prev_event_time = business_opens_utc
                    for event_time, event_type in events:
                        actual_event_time = max(business_opens_utc, min(event_time, business_closes_utc))
                        if actual_event_time > prev_event_time:
                            duration_s = (actual_event_time - prev_event_time).total_seconds()
                            if current_status == 'active':
                                daily_uptime_s += duration_s
                        if event_type not in ['SYSTEM_OPEN', 'SYSTEM_CLOSE']:
                            current_status = event_type
                        elif event_type == 'SYSTEM_CLOSE':
                            current_status = 'inactive'
                        prev_event_time = actual_event_time

                    total_business_seconds_for_day += max(0, (business_closes_utc - business_opens_utc).total_seconds())

                if iter_utc_dt >= target_ref_time_utc - timedelta(days=1):
                    total_uptime_last_day_s += daily_uptime_s
                    total_active_time_in_business_last_day_s += total_business_seconds_for_day

                total_uptime_last_week_s += daily_uptime_s
                total_active_time_in_business_last_week_s += total_business_seconds_for_day

                current_utc_date += timedelta(days=1)

            # Final output parameters
            uptime_last_hour_min = round(total_uptime_last_hour_s / 60)
            downtime_last_hour_min = round(max(0, total_active_time_in_business_last_hour_s - total_uptime_last_hour_s) / 60)
            uptime_last_day_hours = round(total_uptime_last_day_s / 3600)
            downtime_last_day_hours = round(max(0, total_active_time_in_business_last_day_s - total_uptime_last_day_s) / 3600)
            uptime_last_week_hours = round(total_uptime_last_week_s / 3600)
            downtime_last_week_hours = round(max(0, total_active_time_in_business_last_week_s - total_uptime_last_week_s) / 3600)

            report_output_list.append([
                store_id, uptime_last_hour_min, uptime_last_day_hours, uptime_last_week_hours,
                downtime_last_hour_min, downtime_last_day_hours, downtime_last_week_hours
            ])

        # Convert the final list into a csv
        report_filename = f"{report_id}.csv"
        report_filepath = os.path.join(REPORTS_DIR, report_filename)
        header = ['store_id', 'uptime_last_hour(minutes)', 'uptime_last_day(hours)', 'uptime_last_week(hours)',
                  'downtime_last_hour(minutes)', 'downtime_last_day(hours)', 'downtime_last_week(hours)']
        with open(report_filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)
            writer.writerows(report_output_list)
        print(f"Report CSV created at {report_filepath}")

        # Set the status to completed once the report is generated
        cursor.execute(
            "UPDATE reports SET status = 'Complete', completed_at = %s, report_path = %s WHERE report_id = %s",
            (datetime.now(pytz.utc), report_filepath, report_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error during report generation: {e}")
        if conn:
            try:
                cursor.execute(
                    "UPDATE reports SET status = 'Error', completed_at = %s WHERE report_id = %s",
                    (datetime.now(pytz.utc), report_id)
                )
                conn.commit()
            except:
                conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# The first API
@app.route('/trigger_report', methods=['POST'])
def trigger_report_endpoint():
    data = request.get_json()
    db_connection_params = get_db_params()
    conn = None
    try:
        conn = psycopg2.connect(**db_connection_params)
        with conn.cursor() as cur:
            # Determine which stores to process
            store_ids = []
            report_store_id = None
            if data and 'store_id' in data and data['store_id']:
                store_id = data['store_id']
                cur.execute("SELECT store_id FROM store_status WHERE store_id = %s", (store_id,))
                if not cur.fetchone():
                    return jsonify({"error": f"Store {store_id} not found"}), 404
                store_ids = [store_id]
                report_store_id = store_id
            else:
                # If no store_id is provided, process all stores
                cur.execute("SELECT DISTINCT store_id FROM store_status")
                store_ids = [row[0] for row in cur.fetchall()]
                if not store_ids:
                    return jsonify({"error": "No stores found in store_status"}), 404
                # Set store_id to NULL for multi-store reports
                report_store_id = None

            # Generate a single report for the selected stores
            report_id = uuid.uuid4().hex
            cur.execute(
                "INSERT INTO reports (report_id, store_id, status, created_at) VALUES (%s, %s, 'Running', %s)",
                (report_id, report_store_id, datetime.now(pytz.utc))
            )
            conn.commit()

            # Run report generation in a background thread
            thread = threading.Thread(target=generate_report_logic, args=(report_id, conn, store_ids))
            thread.start()

            return jsonify({"report_id": report_id}), 202
    except Exception as e:
        print(f"Endpoint /trigger_report: Error: {e}")
        return jsonify({"error": "Failed to trigger report", "details": str(e)}), 500
    finally:
        pass

# This is the second API call which is used to download the report.
@app.route('/get_report/<report_id>', methods=['GET'])
def get_report_endpoint(report_id: str):
    db_connection_params = get_db_params()
    conn = None
    try:
        conn = psycopg2.connect(**db_connection_params)
        with conn.cursor() as cur:
            cur.execute("SELECT status, report_path FROM reports WHERE report_id = %s", (report_id,))
            result = cur.fetchone()
        if not result:
            return jsonify({"error": "Report not found"}), 404

        status, report_path = result

        if status == 'Running':
            return jsonify({"status": "Running"}), 200

        if status == 'Error':
            return jsonify({"status": "Error"}), 200

        if status == 'Complete':
            if not report_path:
                return jsonify({"status": "Complete", "error": "Report file path missing"}), 200
            if not os.path.exists(report_path):
                return jsonify({"status": "Complete", "error": "Report file not found"}), 200

            #Identify the report path to download the report
            report_dir = os.path.abspath(os.path.dirname(report_path))
            expected_dir = os.path.abspath(REPORTS_DIR)
            if report_dir != expected_dir:
                return jsonify({"status": "Complete", "error": "Report file path does not match expected directory"}), 200

            filename = os.path.basename(report_path)
            with open(report_path, 'rb') as f:
                response = make_response(f.read())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename={filename}'
            response.headers['X-Report-Status'] = 'Complete'
            return response

        return jsonify({"status": status, "error": "Unexpected status"}), 500

    except Exception as e:
        print(f"Endpoint /get_report: Error: {e}")
        return jsonify({"error": "Failed to retrieve report status", "details": str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)