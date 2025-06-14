import sys
import os
import traceback # Import traceback

PROJECT_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT_PATH)

app = None

try:
    # execute endpoints.py
    from app.api.endpoints import app 
    print("Successfully imported 'app' from app.api.endpoints")
except ImportError as e:
    print(f"ImportError: Error importing application modules: {e}")
    print("Current sys.path:", sys.path)
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"General Exception during import of app: {e}")
    traceback.print_exc()
    sys.exit(1)

if app is None:
    print("Flask app object was not imported successfully from app.api.endpoints")
    sys.exit(1)


if __name__ == '__main__':

    print("Starting Flask application...")
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Exception occurred while trying to run Flask app: {e}")
        traceback.print_exc()
        sys.exit(1)
