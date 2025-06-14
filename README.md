
## Objective
To create a flask application that generates reports for a restaurant. The report should be a csv file and contain store_id, uptime_last_hour(in minutes), uptime_last_day(in hours), uptime_last_week(in hours), downtime_last_hour(in minutes), downtime_last_day(in hours), downtime_last_week(in hours).

## Constraints
Uptime and downtime should only include observations within business hours.
Extrapolate uptime and downtime based on the periodic polls we have ingested, to the entire time interval.

## API Requirements
/trigger_report endpoint: trigger report generation from the data provided  
/get_report endpoint: return the status of the report or the csv

## Setup Instructions

### Prerequisites
Python 3.8+  
PostgreSQL  
Git (optional).

### Steps
Clone the Repository (if applicable):
```bash
git clone github.com/arvindkrishna0212/Arvind_15-06-2025
cd Arvind_15-06-2025
```

Install Dependencies:
```bash
pip install flask psycopg2-binary pytz
```

Set Up the Database:
Create a PostgreSQL database named loop (or update the credentials in endpoints.py to match your database):
```bash
psql -U postgres -c "CREATE DATABASE loop;"
```

Run the create_table.py script to create the necessary tables:
```bash
python create_table.py
```

Ensure you update the database credentials in create_table.py if they differ from the defaults (user: postgres, password: password, host: localhost, port: 5432).

Import Data:
Run the convert_to_pg.py script to import data from CSV files into the PostgreSQL tables. Ensure to change the table names and the file path before running the script.
```bash
python convert_to_pg.py
```

Run the Application: Start the Flask development server:
```bash
python run.py
```

The application will be available at http://localhost:5000.

## Usage

### Frontend Interface
Open your browser and navigate to http://localhost:5000.  
The webpage displays a simple interface with two buttons:  
Trigger Report: Initiates report generation for a specific store (if a store_id is provided) or all stores.  
Get Report: Retrieves the status of a report or downloads the CSV file once complete.  
After clicking "Trigger Report," a report_id will be displayed immediately. Use this ID to check the report status or download the report using the "Get Report" button.



### Example CSV Output
The generated CSV file will have the following structure:

```text
store_id,uptime_last_hour(minutes),uptime_last_day(hours),uptime_last_week(hours),downtime_last_hour(minutes),downtime_last_day(hours),downtime_last_week(hours)
525314c1-5383-4d93-aa12-7dbe50448a34,60,11,68,0,2,40
```
## Solution

### endpoints.py
This file contains the main logic of the report generation and retrieval. It defines the Flask application, including the /trigger_report endpoint to initiate report generation asynchronously and the /get_report endpoint to check the status or download the generated CSV file. The report generation logic calculates uptime and downtime within business hours, handling timezone conversions and extrapolating data based on store status polls.

### create_table.py
Running this script will create the necessary tables required in postgres for the code to run. Ensure to change the database credentials in the code.

### convert_to_pg.py
This script will retrieve the data from the csv files and add it to the tables in postgres.

### index.html
The basic template required to render the website

### styles.css
This file contains the CSS styles for the frontend, defining the visual layout of the website. It includes styling for buttons, text, and containers.

### script.js
Includes the button actions that calls either /trigger_report or /fetch_report api.


## Future Enhancements
1) Could improve the security by adding some sort of encryption if the data needs to be kept private.
2) Add multi-threading to process data faster.
3) Create a cron job that automatically creates reports everyday for the user so that they can view the data anytime without generating.
