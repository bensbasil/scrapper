import os
import subprocess
import glob

print("Checking PostgreSQL installation...")

# Common directories
common_dirs = [
    "C:/Program Files/PostgreSQL",
    "C:/Program Files (x86)/PostgreSQL",
]

found_paths = []
for d in common_dirs:
    if os.path.exists(d):
        print(f"Found PostgreSQL folder: {d}")
        # Search for bin/pg_ctl.exe
        pattern = os.path.join(d, "**/bin/pg_ctl.exe")
        for filepath in glob.glob(pattern, recursive=True):
            print(f"Found pg_ctl: {filepath}")
            found_paths.append(filepath)

# Let's check running processes
try:
    tasklist = subprocess.check_output("tasklist", shell=True).decode('utf-8', errors='ignore')
    if "postgres" in tasklist.lower():
        print("postgres.exe process is running!")
    else:
        print("postgres.exe process is NOT running.")
except Exception as e:
    print(f"Failed to check processes: {e}")

# Let's list services containing postgres
try:
    services = subprocess.check_output("sc query type= service state= all", shell=True).decode('utf-8', errors='ignore')
    postgres_services = []
    for line in services.split("\n"):
        if "SERVICE_NAME" in line and "postgre" in line.lower():
            service_name = line.split(":")[-1].strip()
            postgres_services.append(service_name)
            print(f"Found service: {service_name}")
    
    if not postgres_services:
        print("No PostgreSQL service found in 'sc query'.")
    else:
        for svc in postgres_services:
            # Query status of the service
            status = subprocess.check_output(f"sc query {svc}", shell=True).decode('utf-8', errors='ignore')
            print(f"Status of {svc}:\n{status}")
except Exception as e:
    print(f"Failed to check services: {e}")
