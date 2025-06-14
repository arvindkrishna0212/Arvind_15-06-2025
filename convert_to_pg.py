import psycopg2
import csv
import uuid
import re

# identify the data type
def infer_data_type(value):
    if not value or value.lower() in ('null', 'none', ''):
        return 'VARCHAR'  # Default for empty/null values
    try:
        uuid.UUID(value)
        return 'UUID'
    except ValueError:
        pass
    if re.match(r'^\d+$', value):
        return 'INTEGER'
    if re.match(r'^\d{2}:\d{2}:\d{2}$', value):
        return 'TIME'
    if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return 'DATE'
    if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', value):
        return 'TIMESTAMP'
    try:
        float(value)
        return 'FLOAT'
    except ValueError:
        pass
    return 'VARCHAR'

def csv_to_postgres(csv_path, table_name, db_params, sample_rows=5):
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        print("Connected to database:", db_params["dbname"])

        cursor.execute(f"DROP TABLE IF EXISTS public.{table_name};")
        print(f"Dropped table {table_name} if it existed")

        # Retrieves the headers of the csv file
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)  # Get column headers
            print("CSV headers:", headers)

            sample_data = [row for row, _ in zip(reader, range(sample_rows))]
            if not sample_data:
                raise ValueError("CSV file is empty or has no data rows")

            # Identify the data type for each column
            column_types = []
            for col_idx, header in enumerate(headers):
                # Get non-empty values from this column
                values = [row[col_idx] for row in sample_data if col_idx < len(row) and row[col_idx]]
                if not values:
                    column_types.append('VARCHAR')  # Default if all values are empty
                    continue
                inferred_type = infer_data_type(values[0])
                column_types.append(inferred_type)

            # Create table
            columns_def = ', '.join(f'"{header}" {col_type}' for header, col_type in zip(headers, column_types))
            create_table_query = f'CREATE TABLE public.{table_name} ({columns_def});'
            cursor.execute(create_table_query)
            print(f"Created table {table_name} with query: {create_table_query}")

            # Verify table structure
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' AND table_schema = 'public';")
            db_columns = [row[0] for row in cursor.fetchall()]
            print(f"Table columns in database: {db_columns}")

            # Copy CSV data to table
            with open(csv_path, 'r') as f:
                next(f) 
                cursor.copy_from(f, table_name, sep=',', columns=headers)
            print(f"Copied data to {table_name}")

            conn.commit()
            print(f"Data successfully loaded into {table_name}")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()

    finally:
        cursor.close()
        conn.close()
        print("Connection closed")

# Example usage
if __name__ == "__main__":
    db_params = {
        "dbname": "loop",
        "user": "postgres",
        "password": "password",
        "host": "localhost",
        "port": "5432"
    }

    csv_path = r"C:\Users\hoopa\Downloads\store-monitoring-data\menu_hours.csv"
    table_name = "menu_hours"

    csv_to_postgres(csv_path, table_name, db_params)